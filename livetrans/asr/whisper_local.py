"""本地 faster-whisper 后端：模型运行在独立进程中，崩溃或卡死时自动重启。

只加载运行环境中已下载的模型，从不隐式联网；下载由模型管理显式触发。
"""
from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable

import numpy as np

from ..worker.client import WorkerError, WorkerProcess
from .base import AsrEngine, AsrResult

log = logging.getLogger(__name__)

LOAD_TIMEOUT = 5 * 60.0  # a large model from a slow disk; never a download
TRANSCRIBE_TIMEOUT = 120.0  # a CPU fallback on a long segment stays well below this
RESTARTS = 2  # per request; a model that keeps crashing is reported, not looped


def cuda_allowed(runtime: str) -> bool:
    # Frozen releases omit CUDA DLLs. Avoid selecting a GPU model just
    # because a graphics driver is present on the user's machine.
    return bool(runtime) or not getattr(sys, "frozen", False)


class ModelNotDownloaded(RuntimeError):
    """The selected model is not in the runtime environment; ``model`` names it."""

    def __init__(self, model: str):
        super().__init__(f"模型 {model} 尚未下载")
        self.model = model


class LocalWhisper(AsrEngine):
    """``runtime`` selects the worker's Python ("" = the app's own)."""

    def __init__(self, model: str = "auto", device: str = "auto", runtime: str = "",
                 worker_factory: Callable[[str], WorkerProcess] = WorkerProcess):
        self._request = {"op": "load", "model": model, "device": device,
                         "cuda": cuda_allowed(runtime)}
        self._runtime = runtime
        self._factory = worker_factory
        self._lock = threading.Lock()
        self._closed = False
        self._worker = None
        self.model_name = model
        self.device = device
        self._spawn()

    def _spawn(self):
        worker = self._factory(self._runtime)
        self._worker = worker
        worker.start()
        try:
            reply = worker.request(self._request, timeout=LOAD_TIMEOUT)
        except WorkerError as error:
            worker.kill()
            if error.kind == "ModelMissing":
                raise ModelNotDownloaded(str(error)) from None
            raise
        except Exception:
            worker.kill()
            raise
        self.model_name, self.device = reply["model"], reply["device"]
        # A crash after this point restarts with what actually loaded, not "auto".
        self._request.update(model=self.model_name, device=self.device)

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> AsrResult:
        payload = np.ascontiguousarray(audio, dtype=np.float32).tobytes()
        with self._lock:
            for attempt in range(RESTARTS + 1):
                if self._closed:
                    raise WorkerError("识别已停止", "WorkerClosed")
                try:
                    if not self._worker.alive:
                        log.warning("模型进程已退出，正在重启")
                        self._spawn()
                    reply = self._worker.request(
                        {"op": "transcribe", "language": language}, payload,
                        timeout=TRANSCRIBE_TIMEOUT)
                except WorkerError as error:
                    if error.kind not in ("WorkerExited", "WorkerTimeout"):
                        raise
                    # Reap it now; a crashed child can still look alive until waited on.
                    self._worker.kill()
                    if self._closed:
                        raise WorkerError("识别已停止", "WorkerClosed") from error
                    if attempt == RESTARTS:
                        raise
                    continue
                return AsrResult(language=reply.get("language") or (language or ""),
                                 text=(reply.get("text") or "").strip())
        raise AssertionError("unreachable")

    def close(self) -> None:
        self._closed = True
        if self._lock.acquire(blocking=False):
            # Idle: let the worker free its model and exit on its own.
            try:
                if self._worker is not None:
                    self._worker.stop()
                    self._worker = None
            finally:
                self._lock.release()
            return
        # A request is in flight: kill so it returns, then wait for it.
        worker = self._worker
        if worker is not None:
            worker.kill()
        with self._lock:
            if self._worker is not None:
                self._worker.kill()
                self._worker = None
