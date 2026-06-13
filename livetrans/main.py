"""LiveTrans 入口：装配配置、字幕窗、管线与托盘。"""
from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .config import AppConfig, config_dir
from .pipeline import Pipeline
from .ui.settings_dialog import SettingsDialog
from .ui.subtitle_window import SubtitleWindow
from .ui.tray import Tray


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config_dir() / "livetrans.log", encoding="utf-8"),
        ],
    )


class App:
    def __init__(self):
        self.qt = QApplication(sys.argv)
        self.qt.setQuitOnLastWindowClosed(False)
        self.cfg = AppConfig.load()
        self.window = SubtitleWindow(self.cfg.subtitle)
        self.pipeline = Pipeline(self.cfg, self.window)
        self.tray = Tray(
            on_toggle_pause=self._toggle_pause,
            on_toggle_window=self._toggle_window,
            on_settings=self._open_settings,
            on_quit=self._quit,
        )

    def run(self) -> int:
        self.tray.show()
        self.window.show()
        try:
            self.pipeline.start()
        except Exception as e:
            logging.exception("启动音频捕获失败")
            QMessageBox.critical(None, "LiveTrans", f"启动音频捕获失败：{e}")
            return 1
        return self.qt.exec()

    def _toggle_pause(self) -> bool:
        self.pipeline.set_paused(not self.pipeline.paused)
        return self.pipeline.paused

    def _toggle_window(self) -> bool:
        self.window.setVisible(not self.window.isVisible())
        return self.window.isVisible()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, on_saved=self._apply_settings)
        dlg.exec()

    def _apply_settings(self) -> None:
        # 引擎类配置需要重建管线；字幕样式即时生效
        self.pipeline.stop()
        self.window.clear_entries()
        self.pipeline = Pipeline(self.cfg, self.window)
        try:
            self.pipeline.start()
        except Exception as e:
            logging.exception("应用设置后启动管线失败")
            QMessageBox.warning(
                None, "LiveTrans",
                f"启动捕获失败：{e}\n\n"
                "若使用'指定软件'模式，请先让该软件播放声音，再重新保存设置。",
            )

    def _quit(self) -> None:
        self.pipeline.stop()
        self.cfg.save()
        self.qt.quit()


def main() -> int:
    setup_logging()
    return App().run()


if __name__ == "__main__":
    sys.exit(main())
