"""AI 会议纪要与内容总结服务。

基于用户配置的翻译/大模型端点（兼容 OpenAI 规范的本地 Ollama、DeepSeek、Qwen 等），
对录制的声音与翻译记录生成结构化会议纪要、待办事项（Action Items）及要点摘要。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from ..config import TranslateConfig

log = logging.getLogger(__name__)

# 纪要缓存版本：提示词或输入格式变化时递增，旧缓存按失效重新生成
PROMPT_VERSION = 2
# 纪要请求超时（秒）；快照随任务固定，不随后续设置编辑漂移
SUMMARY_TIMEOUT_S = 60.0
# cfg.record.summary_max_chars 缺失或非法时的回退值
DEFAULT_MAX_INPUT_CHARS = 120_000


@dataclass(frozen=True)
class SummaryService:
    """提交纪要任务时从当前已应用设置拷贝的不可变服务快照。

    在途任务持有此快照，之后编辑/应用设置不会改变已发出的请求。
    api_key 仅用于请求头，绝不进入通知、日志或缓存键。
    """

    base_url: str
    model: str
    api_key: str
    timeout: float = SUMMARY_TIMEOUT_S
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS

    @classmethod
    def from_config(cls, translate: TranslateConfig, max_input_chars=None) -> SummaryService:
        budget = max_input_chars
        if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
            budget = DEFAULT_MAX_INPUT_CHARS
        return cls(base_url=str(translate.base_url), model=str(translate.model),
                   api_key=str(translate.api_key), max_input_chars=budget)


def service_identity(base_url: str) -> str:
    """无凭据的服务身份：scheme://host:port/base_path，用于缓存键。"""
    try:
        parsed = urlsplit(str(base_url).strip())
    except ValueError:
        return str(base_url).strip()
    scheme = (parsed.scheme or "http").lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80
    path = parsed.path.rstrip("/")
    return f"{scheme}://{host}:{port}{path}"


def summary_cache_key(source_bytes: bytes, mode: str, service: SummaryService) -> str:
    """缓存有效性键：源内容哈希 + 模式 + 模型 + 服务身份 + 提示词版本。"""
    digest = hashlib.sha256(source_bytes).hexdigest()
    return "|".join([f"v{PROMPT_VERSION}", digest, mode, service.model,
                     service_identity(service.base_url)])


MINUTES_SYSTEM_PROMPT = """你是一个专业的会议纪要与对话总结专家。
请根据以下多语言实时语音识别与翻译的逐句记录，整理出一份条理清晰、层次分明的高质量会议纪要与总结。

请严格按以下 Markdown 格式结构输出：
### 📌 主题与核心主旨
（用 2~3 句话简要概括本场录制/会议的核心主题、主旨背景与关键讨论范围）

### 📝 重点内容与讨论议题
- **[议题一 / 讨论点 1]**：详细说明讨论过程、核心论点及具体内容。
- **[议题二 / 讨论点 2]**：详细说明讨论过程、核心论点及具体内容。
（根据实际内容分点归纳，条理清晰）

### 💡 关键结论与达成共识
- 总结形成的明确结论、决定、共识或核心观点。

### ✅ 待办事项与行动项 (Action Items)
- [ ] **[责任人/角色]** 待办事项描述
（若内容中无明确待办事项，请注明“无明确待办事项”）

要求：语言专业精炼、重点突出、如实反映记录内容。直接输出 Markdown 正文，不要输出无关寒暄。"""

CONCISE_SYSTEM_PROMPT = """你是一个专业的摘要速记专家。
请用一段精炼流畅的文字（200 字以内），提炼出以下语音记录的核心内容、核心事件与关键结论。
直接输出摘要正文，不要输出无关解释。"""

def session_origin(meta: dict, entries: list[dict]) -> float:
    """会内时间原点：会话起点 meta["t"]；旧文件缺元数据时回退到最早发言。"""
    starts = [float(e.get("start", 0.0)) for e in entries]
    t = meta.get("t")
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return float(t)
    return min(starts) if starts else 0.0


def format_relative_time(seconds: float) -> str:
    """会内相对秒 → ``MM:SS``（不足一小时）或 ``H:MM:SS``。"""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_transcript_text(entries: list[dict], origin: float = 0.0) -> str:
    """将逐句记录格式化为适合大模型理解的带有时间与对照的文本。

    ``start`` 是绝对 Unix 时间，统一减去会话原点 ``origin`` 显示为会内时间。
    """
    lines = []
    for e in entries:
        start_s = float(e.get("start", 0.0)) - origin
        time_tag = f"[{format_relative_time(start_s)}]"

        orig = str(e.get("text", "")).strip()
        trans = str(e.get("translation", "")).strip()

        if trans and orig and trans != orig:
            lines.append(f"{time_tag} 原文: {orig}\n       译文: {trans}")
        elif trans:
            lines.append(f"{time_tag} {trans}")
        elif orig:
            lines.append(f"{time_tag} {orig}")
    return "\n".join(lines)


def generate_summary(
    entries: list[dict],
    service: SummaryService,
    mode: str = "minutes",
    meta: dict | None = None,
) -> dict:
    """调用快照指定的服务生成总结。

    mode: 'minutes' (会议纪要与行动项) | 'concise' (极简摘要)
    输入超过 service.max_input_chars、输出被截断或为空时抛出异常，不产生缓存。
    """
    if not entries:
        raise ValueError("记录内容为空，无法生成总结")

    origin = session_origin(meta or {}, entries)
    transcript_text = format_transcript_text(entries, origin)
    if not transcript_text.strip():
        raise ValueError("记录中无有效语音文本")
    if len(transcript_text) > service.max_input_chars:
        raise ValueError(
            f"记录文本过长（{len(transcript_text)} 字符），"
            f"超过单次纪要上限 {service.max_input_chars} 字符，已取消请求"
        )

    system_prompt = (
        MINUTES_SYSTEM_PROMPT if mode == "minutes" else CONCISE_SYSTEM_PROMPT
    )
    summary_hint = "结构化会议纪要" if mode == "minutes" else "极简摘要"
    user_content = (
        f"以下是完整的实时语音识别与翻译记录：\n\n{transcript_text}\n\n"
        f"请为以上记录生成{summary_hint}。"
    )

    url = service.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {service.api_key}"}

    extra_body = {"enable_thinking": False}
    body = {
        "model": service.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 2048 if mode == "minutes" else 512,
        "stream": False,
        **extra_body,
    }

    with httpx.Client(headers=headers, timeout=service.timeout) as client:
        resp = client.post(url, json=body)
        if resp.status_code == 400 and "enable_thinking" in body:
            # 兼容不支持 enable_thinking 参数的端点
            body.pop("enable_thinking", None)
            resp = client.post(url, json=body)

        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("大模型服务未返回有效内容")

    choice = choices[0]
    content = str(choice.get("message", {}).get("content") or "").strip()
    # finish_reason == "length" 或空内容都不能当作完整纪要
    if choice.get("finish_reason") == "length":
        raise RuntimeError("纪要被截断：模型输出达到长度上限，请缩短记录或调整后重试")
    if not content:
        raise RuntimeError("纪要内容为空：服务未返回有效文本")
    return {
        "content": content,
        "mode": mode,
        "model": service.model,
        "created_at": time.time(),
        "utterance_count": len(entries),
    }


def summary_file_path(record_path: Path) -> Path:
    return record_path.with_suffix(".summary.json")


def load_summary(record_path: Path) -> dict | None:
    path = summary_file_path(record_path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_summary(record_path: Path, summary_data: dict) -> None:
    """原子写入缓存：先写临时文件并 fsync，再 os.replace；失败抛 OSError。"""
    path = summary_file_path(record_path)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(summary_data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def format_markdown_export(record_data: dict, summary_data: dict | None) -> str:
    """导出为格式化 Markdown 文本。"""
    meta = record_data.get("meta", {})
    entries = record_data.get("entries", [])
    session_t = meta.get("t")
    if isinstance(session_t, (int, float)) and not isinstance(session_t, bool):
        session_time = datetime.fromtimestamp(session_t).strftime("%Y-%m-%d %H:%M:%S")
    else:
        session_time = ""
    source = meta.get("source", "")
    lines = [
        "# LiveTrans 语音与翻译记录导出",
        "",
        f"- **记录时间**：{session_time or '未知'}",
        f"- **声音来源**：{source or '未知'}",
        f"- **总句数**：{len(entries)} 句",
        f"- **导出时间**：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    if summary_data and summary_data.get("content"):
        lines.extend([
            "---",
            "",
            f"## 🤖 AI 智能总结与纪要（模型：{summary_data.get('model', '未知')}）",
            "",
            summary_data["content"],
            "",
            "---",
            "",
        ])

    lines.extend([
        "## 💬 逐句对话记录",
        "",
    ])
    origin = session_origin(meta, entries)
    for e in entries:
        start_s = float(e.get("start", 0.0)) - origin
        time_tag = f"`{format_relative_time(start_s)}`"
        orig = str(e.get("text", "")).strip()
        trans = str(e.get("translation", "")).strip()

        if trans and orig and trans != orig:
            lines.append(f"- {time_tag} **{orig}**")
            lines.append(f"  - 译文：{trans}")
        elif trans:
            lines.append(f"- {time_tag} {trans}")
        elif orig:
            lines.append(f"- {time_tag} {orig}")

    return "\n".join(lines) + "\n"

