"""Desktop integration helpers for the headless core."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def open_directory(path: Path) -> bool:
    """Reveal ``path`` in the platform file manager; False when that fails."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        log.warning("无法打开文件夹 %s", path, exc_info=True)
        return False
    return True
