"""OpenAI 兼容 chat 翻译客户端。

同一套代码覆盖本地 Ollama（http://localhost:11434/v1）与云端
（DeepSeek/GPT/Gemini/通义等），只需改 base_url + api_key + model。
"""
from __future__ import annotations

import httpx

from .base import Translator

SYSTEM_PROMPT = (
    "你是直播同传翻译。把用户给出的直播语音识别文本翻译成{target}。\n"
    "要求：\n"
    "- 口语化、简洁自然，符合直播语境\n"
    "- 人名、游戏术语、专有名词保留原文或用通用译名\n"
    "- 识别文本可能有少量错字，按上下文合理理解\n"
    "- 只输出译文本身，不要任何解释、注音或括号备注\n"
    "- 不要思考过程，直接给出译文"
)


class OpenAICompatTranslator(Translator):
    def __init__(self, base_url: str, api_key: str, model: str, target_language: str = "中文"):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._system = SYSTEM_PROMPT.format(target=target_language)
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"}, timeout=30.0
        )
        # 混合推理模型（qwen3/deepseek 等）会随机触发思考拖慢翻译，
        # SiliconFlow/Ollama 等支持 enable_thinking 关闭；不支持的端点
        # （如 OpenAI 官方）会返回 400，此时去掉该参数重试并不再发送。
        self._extra_body: dict = {"enable_thinking": False}

    def translate(self, text: str, source_language: str = "") -> str:
        user = f"[{source_language}] {text}" if source_language else text
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": 512,
            "stream": False,
            **self._extra_body,
        }
        resp = self._client.post(self._url, json=body)
        if resp.status_code == 400 and self._extra_body:
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
