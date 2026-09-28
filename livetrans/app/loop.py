"""Single-threaded task dispatcher replacing the Qt queued-signal event loop.

All controller, settings and model state lives on the loop thread: worker
threads never touch it directly, they ``post`` callables here instead.
"""
from __future__ import annotations

import logging
import queue
from collections.abc import Callable

log = logging.getLogger(__name__)

_WAKE = object()


class Loop:
    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._stopping = False

    def post(self, fn: Callable, *args) -> None:
        """Thread-safe: schedule ``fn(*args)`` to run on the loop thread."""
        self._queue.put((fn, args))

    def stop(self) -> None:
        self._stopping = True
        self._queue.put(_WAKE)

    def run(self) -> None:
        """Run tasks until ``stop()`` is called from any thread."""
        while not self._stopping:
            self.process_pending(None)

    def process_pending(self, timeout: float | None = 0.0) -> int:
        """Run queued tasks, waiting up to ``timeout`` for the first one.

        ``timeout=None`` waits indefinitely. Returns the number of tasks run;
        a failing task is logged and never kills the loop.
        """
        try:
            item = self._queue.get() if timeout is None else self._queue.get(timeout=timeout)
        except queue.Empty:
            return 0
        ran = 0
        while True:
            if item is not _WAKE:
                fn, args = item
                try:
                    fn(*args)
                except Exception:
                    log.exception("livetrans task failed")
                ran += 1
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return ran
