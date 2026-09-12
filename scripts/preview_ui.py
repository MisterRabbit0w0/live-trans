"""Isolated UI preview/visual checks; never captures audio or calls a real service.

Run: python scripts/preview_ui.py --capture .cache/ui --theme light --scale 1.5
Omit --capture to interact with a preview backed by simulated subtitle events.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PreviewPipeline:
    def __init__(self, cfg, emit, cancel):
        self.emit, self.cancel = emit, cancel

    def start(self, paused=False):
        if not self.cancel.wait(0.15):
            self.emit({"kind": "started", "device": "预览音频（模拟数据）", "paused": paused})
            self.emit({"kind": "entry", "id": 1,
                       "original": "The next session starts in five minutes.", "language": "en"})
            self.emit({"kind": "translation", "id": 1, "translation": "下一场将在五分钟后开始。"})

    def stop(self):
        self.cancel.set()

    def set_paused(self, paused):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--theme", choices=("light", "dark", "system"), default="light")
    parser.add_argument("--scale", choices=("1", "1.5", "2"))
    parser.add_argument("--opaque", action="store_true")
    parser.add_argument(
        "--desktop", action="store_true",
        help="Capture the desktop region including DWM; keep the preview unobstructed",
    )
    parser.add_argument(
        "--backdrop", action="store_true", help="Show colored native backdrop for QA",
    )
    args = parser.parse_args()
    if args.scale:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = args.scale
        os.environ["QT_SCREEN_SCALE_FACTORS"] = "1"
    from PySide6.QtCore import Qt, QTimer

    from livetrans.config import AppConfig
    from livetrans.main import App
    from livetrans.ui.runtime import RuntimeCoordinator

    cfg = AppConfig()
    cfg.ui.theme = args.theme
    cfg.ui.reduce_transparency = args.opaque
    with tempfile.TemporaryDirectory(prefix="livetrans-preview-") as directory:
        app = App(cfg, Path(directory) / "config.json", RuntimeCoordinator(PreviewPipeline))
        app.main_window.setTitle("LiveTrans · 界面预览（模拟数据）")
        backdrop = None
        if args.backdrop:
            from PySide6.QtWidgets import QHBoxLayout, QWidget

            backdrop = QWidget()
            if args.desktop:
                # Keep the diagnostic stripes behind the preview even if a
                # different application becomes active during capture.
                backdrop.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
                app.main_window.setFlag(Qt.WindowType.WindowStaysOnTopHint)
            backdrop.setWindowTitle("LiveTrans 材质测试背景")
            layout = QHBoxLayout(backdrop)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            for color in ("#e95471", "#e8be4f", "#448fda", "#8b56cf"):
                stripe = QWidget()
                stripe.setStyleSheet(f"background: {color}")
                layout.addWidget(stripe)
            window = app.main_window
            backdrop.setGeometry(window.x() - 20, window.y() - 20,
                                 window.width() + 40, window.height() + 40)
            backdrop.show()
        errors = []
        app.engine.warnings.connect(lambda items: errors.extend(e.toString() for e in items))
        if args.capture:
            args.capture.mkdir(parents=True, exist_ok=True)
            app.controller.refreshDevices = lambda: None
            page = [0]

            def capture():
                index = page[0]
                if index < 6:
                    output = args.capture / f"{index}.png"
                    window = app.main_window
                    shot = window.screen().grabWindow(
                        0, window.x(), window.y(), window.width(), window.height(),
                    ) if args.desktop else window.grabWindow()
                    if not shot.save(str(output)):
                        errors.append(f"Cannot capture page {index}")
                    page[0] += 1
                    if page[0] < 6:
                        app.main_window.setProperty("currentPage", page[0])
                        QTimer.singleShot(400, capture)
                    else:
                        if backdrop is not None:
                            # Inspect the overlay against the same known colors,
                            # not an unrelated part of the user's desktop.
                            app.main_window.hide()
                            overlay = app.subtitle_window
                            app.subtitle_window.setPosition(
                                backdrop.x() + (backdrop.width() - overlay.width()) // 2,
                                backdrop.y() + backdrop.height() // 2,
                            )
                        app.controller.start()
                        QTimer.singleShot(450, capture)
                else:
                    window = app.subtitle_window
                    shot = window.screen().grabWindow(
                        0, window.x(), window.y(), window.width(), window.height(),
                    ) if args.desktop else window.grabWindow()
                    shot.save(str(args.capture / "subtitle.png"))
                    report = {
                        "qml_errors": errors,
                        "main_glass": app.appearance.mainGlass,
                        "subtitle_glass": app.appearance.subtitleGlass,
                        "size": [app.main_window.width(), app.main_window.height()],
                        "dpr": app.main_window.devicePixelRatio(),
                    }
                    print(json.dumps(report, ensure_ascii=False))
                    app.qt.quit()

            QTimer.singleShot(600, capture)
        return app.run()


if __name__ == "__main__":
    sys.exit(main())
