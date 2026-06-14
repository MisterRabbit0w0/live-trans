"""云端转写后端：OpenAI 兼容 /audio/transcriptions（OpenAI/Groq/SiliconFlow 等）。"""
from __future__ import annotations

import io
import wave

import httpx
import numpy as np

from .base import AsrEngine, AsrResult


def _to_wav_bytes(audio: np.ndarray, rate: int = 16000) -> bytes:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class CloudWhisper(AsrEngine):
    def __init__(self, base_url: str, api_key: str, model: str):
        self._url = base_url.rstrip("/") + "/audio/transcriptions"
        self._model = model
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"}, timeout=30.0
        )

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> AsrResult:
        data = {"model": self._model, "response_format": "json"}
        if language:
            data["language"] = language
        resp = self._client.post(
            self._url,
            data=data,
            files={"file": ("audio.wav", _to_wav_bytes(audio), "audio/wav")},
        )
        resp.raise_for_status()
        body = resp.json()
        return AsrResult(
            language=body.get("language", language or ""),
            text=(body.get("text") or "").strip(),
        )

    def close(self) -> None:
        self._client.close()
