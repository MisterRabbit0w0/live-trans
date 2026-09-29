"""AI 会议纪要与内容总结服务。

基于用户配置的翻译/大模型端点（兼容 OpenAI 规范的本地 Ollama、DeepSeek、Qwen 等），
对录制的声音与翻译记录生成结构化会议纪要、待办事项（Action Items）及要点摘要。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from ..config import TranslateConfig

log = logging.getLogger(__name__)

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

def format_transcript_text(entries: list[dict]) -> str:
    """将逐句记录格式化为适合大模型理解的带有时间与对照的文本。"""
    lines = []
    for e in entries:
        start_s = e.get("start", 0.0)
        minutes = int(start_s // 60)
        seconds = int(start_s % 60)
        time_tag = f"[{minutes:02d}:{seconds:02d}]"

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
    cfg: TranslateConfig,
    mode: str = "minutes",
) -> dict:
    """调用配置的大模型服务生成总结。

    mode: 'minutes' (会议纪要与行动项) | 'concise' (极简摘要)
    """
    if not entries:
        raise ValueError("记录内容为空，无法生成总结")

    transcript_text = format_transcript_text(entries)
    if not transcript_text.strip():
        raise ValueError("记录中无有效语音文本")

    system_prompt = (
        MINUTES_SYSTEM_PROMPT if mode == "minutes" else CONCISE_SYSTEM_PROMPT
    )
    summary_hint = "结构化会议纪要" if mode == "minutes" else "极简摘要"
    user_content = (
        f"以下是完整的实时语音识别与翻译记录：\n\n{transcript_text}\n\n"
        f"请为以上记录生成{summary_hint}。"
    )

    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}"}

    extra_body = {"enable_thinking": False}
    body = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 2048 if mode == "minutes" else 512,
        "stream": False,
        **extra_body,
    }

    with httpx.Client(headers=headers, timeout=60.0) as client:
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

    content = choices[0].get("message", {}).get("content", "").strip()
    return {
        "content": content,
        "mode": mode,
        "model": cfg.model,
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
    path = summary_file_path(record_path)
    try:
        path.write_text(json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as error:
        log.warning("保存总结缓存失败 (%s)", error)


def format_markdown_export(record_data: dict, summary_data: dict | None) -> str:
    """导出为格式化 Markdown 文本。"""
    meta = record_data.get("meta", {})
    entries = record_data.get("entries", [])
    session_time = meta.get("source", "")
    lines = [
        "# LiveTrans 语音与翻译记录导出",
        "",
        f"- **记录时间**：{session_time or '未知'}",
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
    for e in entries:
        start_s = e.get("start", 0.0)
        minutes = int(start_s // 60)
        seconds = int(start_s % 60)
        time_tag = f"`{minutes:02d}:{seconds:02d}`"
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
