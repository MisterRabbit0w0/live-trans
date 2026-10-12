"""OpenAI 兼容 chat 翻译客户端。

同一套代码覆盖本地 Ollama（http://localhost:11434/v1）与云端
（DeepSeek/GPT/Gemini/通义等），只需改 base_url + api_key + model。
"""

from __future__ import annotations

import threading

import httpx

from .base import TranslationHistory, Translator

SYSTEM_PROMPT = (
    "你是直播同传翻译。把用户给出的直播语音识别文本翻译成{target}。\n"
    "要求：\n"
    "- 口语化、简洁自然，符合直播语境；译文长度与原文相当，不要扩写\n"
    "- 人名、游戏/直播术语、专有名词保留原文或沿用上文译法，前后保持一致\n"
    '- 识别文本可能有错字、重复字词（如"这个这个"）或半截句子：\n'
    "  按上下文理解后输出通顺译文，不要逐字硬翻；不要脑补补全未说完的内容\n"
    "- 只输出译文本身，不要任何解释、注音或括号备注\n"
    "- 不要思考过程，直接给出译文"
)


class OpenAICompatTranslator(Translator):
    def __init__(self, base_url: str, api_key: str, model: str, target_language: str = "中文"):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        # Keep legacy JSON values while making the UI's Chinese script explicit.
        target_language = {
            "中文": "简体中文",
            "中文（简体）": "简体中文",
            "中文（繁体）": "繁体中文",
        }.get(target_language, target_language)
        self._system = SYSTEM_PROMPT.format(target=target_language)
        self._client = httpx.Client(headers={"Authorization": f"Bearer {api_key}"}, timeout=30.0)
        # 混合推理模型（qwen3/deepseek 等）会随机触发思考拖慢翻译，
        # SiliconFlow/Ollama 等支持 enable_thinking 关闭；不支持的端点
        # （如 OpenAI 官方）会返回 400，此时去掉该参数重试并不再发送。
        self._extra_body: dict = {"enable_thinking": False}
        self._options_lock = threading.Lock()

    def translate(
        self,
        text: str,
        source_language: str = "",
        history: TranslationHistory | None = None,
    ) -> str:
        user = f"[{source_language}] {text}" if source_language else text
        messages: list[dict] = [{"role": "system", "content": self._system}]
        # 上下文：把最近几句的原文/译文作为对话历史，帮助模型处理
        # 代词指代、术语一致性和被 VAD 切碎的半截句子。
        for hist_lang, hist_src, hist_dst in (history or [])[-3:]:
            hist_user = f"[{hist_lang}] {hist_src}" if hist_lang else hist_src
            messages.append({"role": "user", "content": hist_user})
            messages.append({"role": "assistant", "content": hist_dst})
        messages.append({"role": "user", "content": user})
        with self._options_lock:
            extra_body = self._extra_body.copy()
        body = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 512,
            "stream": False,
            **extra_body,
        }
        resp = self._client.post(self._url, json=body)
        if resp.status_code == 400 and "enable_thinking" in body:
            # Retry this request even if another worker has already disabled the
            # option for future requests. Never serialize the network calls.
            with self._options_lock:
                self._extra_body = {}
            body.pop("enable_thinking", None)
            resp = self._client.post(self._url, json=body)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        content = msg.get("content") or ""
        # 兼容思考型模型可能输出的 <think> 块
        if "</think>" in content:
            content = content.split("</think>", 1)[1]
        return content.strip()

    def close(self) -> None:
        self._client.close()
