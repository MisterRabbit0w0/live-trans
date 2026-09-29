"""Serial, cancellable lifecycle operations with generation-tagged events.

``on_event(generation, event)`` is invoked from the executor thread; the
owner is responsible for handing events to the loop thread (the controller
wires it as ``lambda g, e: loop.post(controller._runtime_event, g, e)``).
"""
from __future__ import annotations

import itertools
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from ..record.transcript import Recorder
from ..session import Session


class RuntimeCoordinator:
    def __init__(self, factory=Session, recorder=None,
                 on_event: Callable[[int, dict], None] = lambda g, e: None):
        self.on_event = on_event
        self._factory = factory
        # Shared by the sessions of one user start, so restarts keep one record.
        self._recorder = recorder if recorder is not None else Recorder()
        self._ids = itertools.count(1)
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

    def start(self, cfg, paused=False, resume=False):
        """``resume`` continues the current record after an engine restart."""
        generation, cancel = self._next()
        self._executor.submit(self._start, generation, cancel, deepcopy(cfg), paused, resume)
        return generation

    def _stop_current(self):
        if self._pipeline is not None:
            if self._pipeline.stop() is False:
                return False
            self._pipeline = None
        return True

    def _start(self, generation, cancel, cfg, paused, resume):
        try:
            if not self._stop_current():
                self.on_event(generation, {"kind": "failed", "reason": "shutdown_pending"})
                return
            if not resume:
                self._recorder.close()
                self._ids = itertools.count(1)
            if cancel.is_set():
                return
            self._pipeline = self._factory(cfg, lambda e: self.on_event(generation, e), cancel,
                                           ids=self._ids, recorder=self._recorder)
            self._pipeline.start(paused=paused)
        except Exception as error:
            self.on_event(generation, {"kind": "failed", "error": type(error).__name__})

    def stop(self):
        generation, _ = self._next()
        self._executor.submit(self._stop, generation)
        return generation

    def _stop(self, generation):
        try:
            stopped = self._stop_current()
            # A cancelled session writes nothing more, even while it is still stopping.
            self._recorder.close()
            if not stopped:
                self.on_event(generation, {"kind": "failed", "reason": "shutdown_pending"})
                return
        except Exception as error:
            self.on_event(generation, {"kind": "failed", "error": type(error).__name__})
        else:
            self.on_event(generation, {"kind": "stopped"})

    def pause(self, paused):
        if self._pipeline is not None:
            self._pipeline.set_paused(paused)

    def reconfigure(self, cfg):
        """Hand downstream changes to the running session without a restart."""
        generation = self.generation
        self._executor.submit(self._reconfigure, generation, self._cancel, deepcopy(cfg))
        return generation

    def _reconfigure(self, generation, cancel, cfg):
        # A later start or stop owns the session and already has the new settings.
        if generation != self.generation or cancel.is_set() or self._pipeline is None:
            return
        try:
            self._pipeline.reconfigure(cfg)
        except Exception as error:
            # Never leave a session running behind a reported failure.
            cancel.set()
            self._stop_current()
            self.on_event(generation, {"kind": "failed", "error": type(error).__name__})

    def close(self):
        if not self._closed:
            self._closed = True
            self._cancel.set()
            self._executor.submit(self._stop_current)
            self._executor.submit(self._recorder.close)
            self._executor.shutdown(wait=True)
