"""Explicit model management for the settings page; every property lives on the GUI thread.

Each operation starts its own short-lived worker in the chosen runtime, so
models always land in the environment that will run them, and a download
never competes with a running session for the recognition worker.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from ..asr.whisper_local import cuda_allowed
from ..worker.client import WorkerError, WorkerProcess

log = logging.getLogger(__name__)

LIST_TIMEOUT = 60.0
FRAME_TIMEOUT = 5 * 60.0  # no progress for this long means the download is stuck


def size_label(size: float) -> str:
    if size >= 1 << 30:
        return f"{size / (1 << 30):.1f} GB"
    return f"{max(size, 0) / (1 << 20):.0f} MB"


class ModelManager(QObject):
    changed = Signal()
    _finished = Signal(str, object, str)  # operation, result, error message
    _progressed = Signal(float, float)

    def __init__(self, worker_factory: Callable[[str], WorkerProcess] = WorkerProcess,
                 parent=None):
        super().__init__(parent)
        self._factory = worker_factory
        self._state = "idle"  # idle | loading | downloading | deleting
        self._runtime = ""
        self._listing: dict = {}
        self._error = ""
        self._target = ""
        self._done = self._total = 0.0
        self._worker = None
        self._cancelled = False
        self._finished.connect(self._on_finished)
        self._progressed.connect(self._on_progress)

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(bool, notify=changed)
    def busy(self):
        return self._state != "idle"

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(str, notify=changed)
    def directory(self):
        return self._listing.get("dir", "")

    @Property(bool, notify=changed)
    def writable(self):
        return self._listing.get("writable", True)

    @Property(str, notify=changed)
    def recommended(self):
        return self._listing.get("recommended", "")

    @Property(str, notify=changed)
    def autoModel(self):
        return self._listing.get("auto", "")

    @Property("QVariantList", notify=changed)
    def installed(self):
        return [{"name": m["name"], "size": size_label(m["size"])}
                for m in self._listing.get("installed", [])]

    @Property(str, notify=changed)
    def target(self):
        return self._target

    @Property(float, notify=changed)
    def progress(self):
        """0–1, or -1 while the total size is unknown."""
        return min(1.0, self._done / self._total) if self._total else -1.0

    @Property(str, notify=changed)
    def progressText(self):
        if self._state != "downloading":
            return ""
        if self._total:
            return f"{size_label(self._done)} / {size_label(self._total)}"
        return size_label(self._done)

    @Slot(str, result=bool)
    def isInstalled(self, name):
        return any(m["name"] == name for m in self._listing.get("installed", []))

    @Slot(str)
    def refresh(self, runtime):
        if self.busy:
            return
        self._begin("loading", runtime, "")
        self._run("models", {"op": "models", "cuda": cuda_allowed(runtime)}, LIST_TIMEOUT)

    @Slot(str, str)
    def download(self, runtime, name):
        name = name.strip()
        if self.busy or not name:
            return
        self._begin("downloading", runtime, name)
        self._run("download", {"op": "download", "model": name}, FRAME_TIMEOUT)

    @Slot(str, str)
    def remove(self, runtime, name):
        if self.busy:
            return
        self._begin("deleting", runtime, name)
        self._run("delete", {"op": "delete", "model": name}, LIST_TIMEOUT)

    @Slot()
    def cancel(self):
        """Stop a download; the partial files stay so the next attempt resumes."""
        worker = self._worker
        if self._state == "downloading" and worker is not None:
            self._cancelled = True
            worker.kill()

    @Slot()
    def openDirectory(self):
        if self.directory:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.directory))

    def close(self):
        self.cancel()

    def _begin(self, state, runtime, target):
        if runtime != self._runtime:
            self._listing = {}
        self._state, self._runtime, self._target = state, runtime, target
        self._error, self._done, self._total, self._cancelled = "", 0.0, 0.0, False
        self.changed.emit()

    def _run(self, operation, request, timeout):
        runtime = self._runtime

        def work():
            worker = self._factory(runtime)
            self._worker = worker
            result, message = None, ""
            try:
                worker.start()
                result = worker.request(request, timeout=timeout, on_progress=(
                    lambda done, total: self._progressed.emit(float(done), float(total))))
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
            self._finished.emit(operation, result, message)

        threading.Thread(target=work, name=f"livetrans-models-{operation}", daemon=True).start()

    @Slot(float, float)
    def _on_progress(self, done, total):
        self._done, self._total = done, total
        self.changed.emit()

    @Slot(str, object, str)
    def _on_finished(self, operation, result, message):
        if result is not None:
            self._listing = result
        if self._cancelled:
            message = "下载已取消，下次会从中断处继续。"
        elif message:
            message = {"download": "下载失败：", "delete": "删除失败：",
                       "models": "无法读取模型："}[operation] + message
        self._state, self._error = "idle", message
        self.changed.emit()
