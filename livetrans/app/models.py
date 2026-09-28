"""Explicit model management; every attribute is mutated on the loop thread.

Each operation starts its own short-lived worker in the chosen runtime, so
models always land in the environment that will run them, and a download
never competes with a running session for the recognition worker.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from ..asr.whisper_local import cuda_allowed
from ..worker.client import WorkerError, WorkerProcess
from . import system

log = logging.getLogger(__name__)

LIST_TIMEOUT = 60.0
FRAME_TIMEOUT = 5 * 60.0  # no progress for this long means the download is stuck


def size_label(size: float) -> str:
    if size >= 1 << 30:
        return f"{size / (1 << 30):.1f} GB"
    return f"{max(size, 0) / (1 << 20):.0f} MB"


class ModelManager:
    def __init__(self, loop, worker_factory: Callable[[str], WorkerProcess] = WorkerProcess,
                 on_change=lambda: None):
        self.on_change = on_change
        self._loop = loop
        self._factory = worker_factory
        self._state = "idle"  # idle | loading | downloading | deleting
        self._runtime = ""
        self._listing: dict = {}
        self._error = ""
        self._target = ""
        self._done = self._total = 0.0
        self._worker = None
        self._cancelled = False

    @property
    def state(self):
        return self._state

    @property
    def busy(self):
        return self._state != "idle"

    @property
    def error(self):
        return self._error

    @property
    def directory(self):
        return self._listing.get("dir", "")

    @property
    def writable(self):
        return self._listing.get("writable", True)

    @property
    def recommended(self):
        return self._listing.get("recommended", "")

    @property
    def autoModel(self):
        return self._listing.get("auto", "")

    @property
    def installed(self):
        return [{"name": m["name"], "size": size_label(m["size"])}
                for m in self._listing.get("installed", [])]

    @property
    def target(self):
        return self._target

    @property
    def progress(self):
        """0–1, or -1 while the total size is unknown."""
        return min(1.0, self._done / self._total) if self._total else -1.0

    @property
    def progressText(self):
        if self._state != "downloading":
            return ""
        if self._total:
            return f"{size_label(self._done)} / {size_label(self._total)}"
        return size_label(self._done)

    def snapshot(self) -> dict:
        return {
            "state": self._state,
            "busy": self.busy,
            "error": self._error,
            "directory": self.directory,
            "writable": self.writable,
            "recommended": self.recommended,
            "autoModel": self.autoModel,
            "installed": self.installed,
            "installedNames": [m["name"] for m in self._listing.get("installed", [])],
            "target": self._target,
            "progress": self.progress,
            "progressText": self.progressText,
        }

    def isInstalled(self, name):
        return any(m["name"] == name for m in self._listing.get("installed", []))

    def refresh(self, runtime):
        if self.busy:
            return
        self._begin("loading", runtime, "")
        self._run("models", {"op": "models", "cuda": cuda_allowed(runtime)}, LIST_TIMEOUT)

    def download(self, runtime, name):
        name = name.strip()
        if self.busy or not name:
            return
        self._begin("downloading", runtime, name)
        self._run("download", {"op": "download", "model": name}, FRAME_TIMEOUT)

    def remove(self, runtime, name):
        if self.busy:
            return
        self._begin("deleting", runtime, name)
        self._run("delete", {"op": "delete", "model": name}, LIST_TIMEOUT)

    def cancel(self):
        """Stop a download; the partial files stay so the next attempt resumes."""
        worker = self._worker
        if self._state == "downloading" and worker is not None:
            self._cancelled = True
            worker.kill()

    def openDirectory(self):
        if self.directory:
            system.open_directory(self.directory)

    def close(self):
        self.cancel()

    def _begin(self, state, runtime, target):
        if runtime != self._runtime:
            self._listing = {}
        self._state, self._runtime, self._target = state, runtime, target
        self._error, self._done, self._total, self._cancelled = "", 0.0, 0.0, False
        self.on_change()

    def _run(self, operation, request, timeout):
        runtime = self._runtime

        def work():
            worker = self._factory(runtime)
            self._worker = worker
            result, message = None, ""
            try:
                worker.start()
                result = worker.request(request, timeout=timeout, on_progress=(
                    lambda done, total: self._loop.post(self._on_progress,
                                                        float(done), float(total))))
                if operation != "models":
                    # Show the environment's contents after every change.
                    result = worker.request({"op": "models", "cuda": cuda_allowed(runtime)},
                                            timeout=LIST_TIMEOUT)
            except (WorkerError, OSError) as error:
                log.warning("模型操作 %s 失败 (%s)", operation, type(error).__name__)
                message = str(error) or type(error).__name__
            finally:
                self._worker = None
                worker.stop()
            self._loop.post(self._on_finished, operation, result, message)

        threading.Thread(target=work, name=f"livetrans-models-{operation}", daemon=True).start()

    def _on_progress(self, done, total):
        self._done, self._total = done, total
        self.on_change()

    def _on_finished(self, operation, result, message):
        if result is not None:
            self._listing = result
        if self._cancelled:
            message = "下载已取消，下次会从中断处继续。"
        elif message:
            message = {"download": "下载失败：", "delete": "删除失败：",
                       "models": "无法读取模型："}[operation] + message
        self._state, self._error = "idle", message
        self.on_change()
