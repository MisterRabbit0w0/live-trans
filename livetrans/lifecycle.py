"""Bounded waits for resource cleanup that may block on native devices or requests."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)


class Cleanup:
    """A single daemon owns cleanup even across repeated stop/retry requests.

    Callers only wait a bounded time. A failed attempt keeps the remaining
    resources reachable so an explicit retry resumes from the first one left.
    """

    def __init__(self, work: Callable[[], None], name: str):
        self._work = work
        self._name = name
        self._lock = threading.Lock()
        self._thread = None
        self._armed = False
        self.done = threading.Event()

    def arm(self):
        """Mark resources as acquired; refuse while a previous cleanup is pending."""
        with self._lock:
            if self._armed and not self.done.is_set():
                raise RuntimeError("上一次会话仍在清理，请稍后重试")
            self._armed = True
            self.done.clear()

    def request(self):
        with self._lock:
            if self.done.is_set():
                return
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
                self._thread.start()

    def wait(self, timeout: float) -> bool:
        return self.done.wait(timeout)

    def _run(self):
        try:
            self._work()
        except Exception as error:
            log.warning("%s 清理失败 (%s)，保留资源等待重试", self._name, type(error).__name__)
            return
        self.done.set()
