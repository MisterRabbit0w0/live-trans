"""本地 faster-whisper 后端：显存检测自动选档，CUDA 失败回退 CPU。"""
from __future__ import annotations

import logging
import subprocess

import numpy as np

from .base import AsrEngine, AsrResult

log = logging.getLogger(__name__)


def detect_free_vram_mb() -> int:
    """通过 nvidia-smi 查询空闲显存(MB)，无 NVIDIA 显卡返回 0。"""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if out.returncode != 0:
            return 0
        return max(int(line) for line in out.stdout.split() if line.strip().isdigit())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0


def pick_model(free_vram_mb: int) -> tuple[str, str, str]:
    """根据空闲显存选 (model, device, compute_type)。

    注意：Blackwell (RTX 50xx) 等新架构显卡上 int8_float16 可能触发
    cuBLAS 兼容性错误，统一使用 float16 更安全。
    """
    if free_vram_mb >= 5_000:
        return "large-v3-turbo", "cuda", "float16"
    if free_vram_mb >= 2_000:
        return "small", "cuda", "float16"
    return "small", "cpu", "int8"


class LocalWhisper(AsrEngine):
    def __init__(self, model: str = "auto", device: str = "auto"):
        from faster_whisper import WhisperModel

        if model == "auto" or device == "auto":
            vram = detect_free_vram_mb()
            auto_model, auto_device, compute = pick_model(vram)
            model = auto_model if model == "auto" else model
            device = auto_device if device == "auto" else device
            log.info("空闲显存 %d MB → 模型 %s @ %s (%s)", vram, model, device, compute)
        else:
            compute = "float16" if device == "cuda" else "int8"

        self.model_name = model
        try:
            self._model = WhisperModel(model, device=device, compute_type=compute)
            self.device = device
        except Exception:
            if device == "cuda":
                log.exception("CUDA 初始化失败，回退到 CPU (int8)")
                self._model = WhisperModel(model, device="cpu", compute_type="int8")
                self.device = "cpu"
            else:
                raise

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> AsrResult:
        try:
            segments, info = self._model.transcribe(
                audio,
                language=language,
                beam_size=1,
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            text = "".join(s.text for s in segments).strip()
            return AsrResult(language=info.language or (language or ""), text=text)
        except RuntimeError as e:
            if "cuda" in str(e).lower() or "cublas" in str(e).lower():
                log.warning("CUDA 推理失败，回退 CPU int8: %s", e)
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                self.device = "cpu"
                return self.transcribe(audio, language)
            raise
