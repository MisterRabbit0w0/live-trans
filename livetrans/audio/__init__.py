"""Audio capture and segmentation; ``get_backend`` picks the current platform."""
from __future__ import annotations

import sys
from functools import lru_cache

from .base import AudioBackend, UnsupportedBackend


@lru_cache(maxsize=1)
def get_backend() -> AudioBackend:
    # Native modules are imported lazily so every platform can import the package.
    if sys.platform == "win32":
        from .windows import WindowsBackend

        return WindowsBackend()
    if sys.platform == "darwin":
        from .macos import MacBackend

        return MacBackend()
    if sys.platform.startswith("linux"):
        from .linux import LinuxBackend

        return LinuxBackend()
    return UnsupportedBackend(sys.platform)
