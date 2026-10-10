"""Copy the committed application icon into the build metadata directory.

The multi-size ICO is rendered once from ``livetrans/assets/livetrans.svg`` and
committed to ``desktop/src-tauri/icons/``; build machines no longer need a Qt
SVG renderer just to reproduce it.
"""
from __future__ import annotations

import shutil
from pathlib import Path


def write_icon(ico_path: Path) -> None:
    icons_dir = Path(__file__).resolve().parents[1] / "desktop" / "src-tauri" / "icons"
    source = icons_dir / "icon.ico"
    if not source.is_file():
        raise SystemExit(f"Committed application icon missing: {source}")
    shutil.copyfile(source, ico_path)
