"""Serial, cancellable lifecycle operations with generation-tagged UI events."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from PySide6.QtCore import QObject, Signal

from ..pipeline import Pipeline


class RuntimeCoordinator(QObject):
    event = Signal(int, object)

    def __init__(self, factory=Pipeline, parent=None):
        super().__init__(parent)
        self._factory = factory
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="livetrans-lifecycle")
        self._pipeline = None
        self._cancel = threading.Event()
        self.generation = 0
        self._closed = False

    def _next(self):
        self._cancel.set()
        self.generation += 1
        self._cancel = threading.Event()
        return self.generation, self._cancel

    def start(self, cfg, paused=False):
        generation, cancel = self._next()
        self._executor.submit(self._start, generation, cancel, deepcopy(cfg), paused)
        return generation

    def _stop_current(self):
        if self._pipeline is not None:
            if self._pipeline.stop() is False:
                return False
            self._pipeline = None
        return True

    def _start(self, generation, cancel, cfg, paused):
        try:
            if not self._stop_current():
                raise RuntimeError("上一会话仍在停止，请稍后重试")
            if cancel.is_set():
                return
            self._pipeline = self._factory(cfg, lambda e: self.event.emit(generation, e), cancel)
            self._pipeline.start(paused=paused)
        except Exception as error:
            self.event.emit(generation, {"kind": "failed", "error": type(error).__name__})

    def stop(self):
        generation, _ = self._next()
        self._executor.submit(self._stop, generation)
        return generation

    def _stop(self, generation):
        try:
            if not self._stop_current():
                raise RuntimeError("当前会话仍在停止，请稍后重试")
        except Exception as error:
            self.event.emit(generation, {"kind": "failed", "error": type(error).__name__})
        else:
            self.event.emit(generation, {"kind": "stopped"})

    def pause(self, paused):
        if self._pipeline is not None:
            self._pipeline.set_paused(paused)

    def close(self):
        if not self._closed:
            self._closed = True
            self._cancel.set()
            self._executor.submit(self._stop_current)
            self._executor.shutdown(wait=True)
