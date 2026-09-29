"""faster-whisper inside the worker process: loads installed models only, CUDA falls back to CPU.

Imports nothing from the app so an isolated runtime only needs numpy and
faster-whisper.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from .models import select

log = logging.getLogger("livetrans.worker.engine")


def _add_cuda_dll_directories():
    """Let ctranslate2 find cuBLAS/cuDNN from ``nvidia-*-cu12`` wheels on Windows."""
    if sys.platform != "win32":
        return
    for base in {Path(p) for p in sys.path if p.endswith("site-packages")}:
        for directory in base.glob("nvidia/*/bin"):
            try:
                os.add_dll_directory(str(directory))
            except OSError:
                pass
            os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")


class WhisperEngine:
    def __init__(self, model: str = "auto", device: str = "auto", cuda: bool = True,
                 root: Path | None = None):
        """``cuda=False`` never probes the GPU (CPU-only distributions)."""
        _add_cuda_dll_directories()
        from faster_whisper import WhisperModel

        self._whisper = WhisperModel
        path, self.model_name, device, compute = select(model, device, cuda, root)
        # A directory path: faster-whisper never contacts the Hub for it.
        self._path = str(path)
        try:
            self._model = WhisperModel(self._path, device=device, compute_type=compute)
            self.device = device
        except Exception:
            if device != "cuda":
                raise
            log.exception("CUDA 初始化失败，回退到 CPU (int8)")
            self._fallback_to_cpu()

    def _fallback_to_cpu(self):
        self._model = self._whisper(self._path, device="cpu", compute_type="int8")
        self.device = "cpu"

    def transcribe(self, audio, language: str | None = None) -> tuple[str, str]:
        """audio: float32 mono @16kHz. Returns ``(language, text)``."""
        try:
            segments, info = self._model.transcribe(
                audio,
                language=language,
                beam_size=1,
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            text = "".join(s.text for s in segments).strip()
            return info.language or (language or ""), text
        except RuntimeError as e:
            if self.device == "cuda" and ("cuda" in str(e).lower() or "cublas" in str(e).lower()):
                log.warning("CUDA 推理失败，回退 CPU int8: %s", e)
                self._fallback_to_cpu()
                return self.transcribe(audio, language)
            raise
