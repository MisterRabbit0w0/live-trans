"""Cross-platform process-level single-instance guard."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QLockFile


class SingleInstance:
    """Keep one LiveTrans process alive for a given user configuration directory."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = QLockFile(str(self.path))
        # A crashed process must not permanently block a later launch, while a
        # running process keeps the lock fresh and remains protected.
        self._lock.setStaleLockTime(30_000)

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return self._lock.tryLock(0)

    def release(self) -> None:
        if self._lock.isLocked():
            self._lock.unlock()
