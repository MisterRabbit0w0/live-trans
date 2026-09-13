"""Assemble the QML windows, shared controller, native materials and tray."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMessageBox
from shiboken6 import delete

from .config import AppConfig, config_dir
from .instance import SingleInstance
from .ui.controller import AppController
from .ui.materials import Appearance
from .ui.tray import Tray, _make_icon
from .ui.window_controls import WindowControls


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config_dir() / "livetrans.log", encoding="utf-8"),
        ],
    )


class App:
    def __init__(self, cfg=None, config_file=None, runtime=None):
        QQuickWindow.setDefaultAlphaBuffer(True)
        if QQuickStyle.name() != "Basic":
            QQuickStyle.setStyle("Basic")
        self.qt = QApplication.instance() or QApplication(sys.argv)
        self.qt.setApplicationName("LiveTrans")
        self.qt.setOrganizationName("LiveTrans")
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setWindowIcon(_make_icon())
        self.controller = AppController(
            cfg if cfg is not None else AppConfig.load(), config_file, runtime,
        )
        self.appearance = Appearance(self.controller.cfg)
        self.window_controls = WindowControls()
        self.subtitle_controls = WindowControls(resizable=False, persistent_material=True)
        self.engine = QQmlApplicationEngine()
        self.engine.warnings.connect(self._qml_warnings)
        context = self.engine.rootContext()
        for name, obj in (
            ("appController", self.controller), ("preferences", self.controller.settings),
            ("subtitleModel", self.controller.subtitles), ("appearance", self.appearance),
            ("windowControls", self.window_controls),
            ("subtitleControls", self.subtitle_controls),
        ):
            context.setContextProperty(name, obj)
        qml = Path(__file__).parent / "ui" / "qml"
        self.engine.load(QUrl.fromLocalFile(str(qml / "Main.qml")))
        self.engine.load(QUrl.fromLocalFile(str(qml / "SubtitleWindow.qml")))
        windows = {window.objectName(): window for window in self.engine.rootObjects()}
        if "controlCenter" not in windows or "subtitleWindow" not in windows:
            self.controller.close()
            raise RuntimeError("无法加载 LiveTrans 界面，请检查安装中的 QML 资源")
        self.main_window = windows["controlCenter"]
        self.subtitle_window = windows["subtitleWindow"]
        self.subtitle_window.setTransientParent(None)
        self.window_controls.attach(self.main_window)
        self.subtitle_controls.attach(self.subtitle_window)
        # Place windows once. Binding x/y to width/height recenters the HWND
        # during native resizing and fights both the mouse and Windows snapping.
        area = self.main_window.screen().availableGeometry()
        width, height = min(1040, round(area.width() * .92)), min(720, round(area.height() * .92))
        self.main_window.setGeometry(
            area.x() + (area.width() - width) // 2,
            area.y() + (area.height() - height) // 2, width, height,
        )
        self.subtitle_window.setPosition(
            area.x() + (area.width() - self.subtitle_window.width()) // 2,
            max(area.y(), area.bottom() - self.subtitle_window.height() - 100),
        )
        self.appearance.attach(self.main_window, self.subtitle_window)
        self.controller.configApplied.connect(self.appearance.configure)
        self.controller.showRequested.connect(self.show_main)
        self.controller.quitReady.connect(self.qt.quit)
        self.tray = Tray(self.controller)
        self.qt.aboutToQuit.connect(self.shutdown)
        self._closed = False

    @staticmethod
    def _qml_warnings(errors):
        for error in errors:
            logging.warning("QML: %s", error.toString())

    def show_main(self):
        if self.main_window.visibility() == QWindow.Visibility.Minimized:
            self.main_window.showNormal()
        else:
            self.main_window.show()
        self.main_window.raise_()
        self.main_window.requestActivate()

    def run(self):
        self.tray.show()
        QTimer.singleShot(0, self.controller.startup)
        return self.qt.exec()

    def shutdown(self):
        if not self._closed:
            self._closed = True
            self.tray.hide()
            self.controller.close()
            self.appearance.stop()
            self.window_controls.detach()
            self.subtitle_controls.detach()
            # Destroy bindings before their Python context objects are finalized.
            delete(self.engine)


def main():
    instance = SingleInstance(config_dir() / "instance.lock")
    if not instance.acquire():
        # This path intentionally initializes only the light Qt widgets needed
        # for a useful duplicate-launch message, never the QML engine/audio.
        qt = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.information(qt.activeWindow(), "LiveTrans", "LiveTrans 已经在运行中。")
        return 0
    try:
        setup_logging()
        app = App()
        return app.run()
    finally:
        instance.release()


if __name__ == "__main__":
    sys.exit(main())
