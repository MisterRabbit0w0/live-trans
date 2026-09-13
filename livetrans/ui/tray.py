"""The tray mirrors application state instead of keeping its own toggle state."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def _make_icon() -> QIcon:
    return QIcon(str(Path(__file__).resolve().parents[1] / "assets" / "livetrans.svg"))


class Tray(QSystemTrayIcon):
    def __init__(self, controller, parent=None):
        super().__init__(_make_icon(), parent)
        self._controller = controller
        self._menu = QMenu()
        self._open = self._action("打开控制中心", controller.showControlCenter)
        self._menu.setDefaultAction(self._open)
        self._menu.addSeparator()
        self._pause = self._action("开始翻译", controller.togglePause)
        self._stop = self._action("停止翻译", controller.stop)
        self._show = self._action("显示字幕", controller.toggleSubtitles)
        self._menu.addSeparator()
        self._action("退出 LiveTrans", controller.requestQuit)
        self.setContextMenu(self._menu)
        self.activated.connect(self._activated)
        controller.changed.connect(self._sync)
        controller.notification.connect(self._notify)
        self._sync()

    def _action(self, label, callback):
        action = QAction(label, self._menu)
        action.triggered.connect(callback)
        self._menu.addAction(action)
        return action

    def _sync(self):
        c = self._controller
        self.setToolTip(f"LiveTrans · {c.statusTitle}")
        self._pause.setText(
            "暂停翻译" if c.state == "running"
            else "继续翻译" if c.state == "paused" else "开始翻译"
        )
        self._pause.setEnabled(not c.busy)
        self._stop.setEnabled(c.state in ("starting", "running", "paused", "error"))
        self._show.setText("隐藏字幕" if c.subtitleVisible else "显示字幕")

    def _activated(self, reason):
        if reason in (self.ActivationReason.Trigger, self.ActivationReason.DoubleClick):
            self._controller.showControlCenter()

    def _notify(self, message):
        self.showMessage("LiveTrans", message, self.MessageIcon.Warning, 6000)
