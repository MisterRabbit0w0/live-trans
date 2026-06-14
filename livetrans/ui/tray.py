"""系统托盘：开始/暂停、显示/隐藏字幕、设置、退出。"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def _make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(30, 144, 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 12, 56, 40, 10, 10)
    p.setPen(QColor("white"))
    font = p.font()
    font.setPixelSize(26)
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect().adjusted(0, -4, 0, 0), Qt.AlignmentFlag.AlignCenter, "译")
    p.end()
    return QIcon(pm)


class Tray(QSystemTrayIcon):
    def __init__(
        self,
        on_toggle_pause: Callable[[], bool],  # 返回切换后的暂停状态
        on_toggle_window: Callable[[], bool],  # 返回切换后是否可见
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
        parent=None,
    ):
        super().__init__(_make_icon(), parent)
        self.setToolTip("LiveTrans 直播翻译")
        menu = QMenu()

        self._pause_action = QAction("暂停翻译")
        self._pause_action.triggered.connect(
            lambda: self._pause_action.setText(
                "继续翻译" if on_toggle_pause() else "暂停翻译"
            )
        )
        menu.addAction(self._pause_action)

        self._show_action = QAction("隐藏字幕")
        self._show_action.triggered.connect(
            lambda: self._show_action.setText(
                "隐藏字幕" if on_toggle_window() else "显示字幕"
            )
        )
        menu.addAction(self._show_action)

        menu.addSeparator()
        settings_action = QAction("设置…")
        settings_action.triggered.connect(on_settings)
        menu.addAction(settings_action)

        menu.addSeparator()
        quit_action = QAction("退出")
        quit_action.triggered.connect(on_quit)
        menu.addAction(quit_action)

        self._menu = menu
        self._actions = [self._pause_action, self._show_action, settings_action, quit_action]
        self.setContextMenu(menu)
