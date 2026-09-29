"""Render the application SVG into a multi-size Windows icon at build time.

Kept under packaging/ because it needs PySide6's SVG renderer, which only
exists in the build environment (see packaging/requirements-build.in).
"""
from __future__ import annotations

import io
import shutil
from pathlib import Path


def write_icon(svg_path: Path, ico_path: Path) -> None:
    icons_dir = Path(__file__).resolve().parents[1] / "desktop" / "src-tauri" / "icons"
    fallback_ico = icons_dir / "icon.ico"
    try:
        from PIL import Image
        from PySide6.QtCore import QBuffer, QIODevice, Qt
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer

        renderer = QSvgRenderer(str(svg_path))
        if not renderer.isValid():
            raise SystemExit("Invalid application SVG")
        image = QImage(256, 256, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        Image.open(io.BytesIO(bytes(buffer.data()))).save(
            ico_path, sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)],
        )
    except Exception:
        if fallback_ico.is_file():
            shutil.copyfile(fallback_ico, ico_path)
        else:
            raise
