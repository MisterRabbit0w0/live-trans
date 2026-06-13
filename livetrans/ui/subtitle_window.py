"""置顶透明双语字幕悬浮窗。

- 无边框、半透明圆角背景、始终置顶、不占任务栏
- 每条字幕：原文（灰色小字）+ 译文（白色大字）；原文先出现，译文到达后补上
- 鼠标拖动移动；Ctrl+滚轮调字号
"""
from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..config import SubtitleStyle


class SubtitleWindow(QWidget):
    # 跨线程更新入口（worker 线程 emit，UI 线程执行）
    entry_added = Signal(int, str, str)  # id, original, language
    translation_ready = Signal(int, str)  # id, translation
    status_changed = Signal(str)  # 状态提示（如"正在加载模型…"）

    def __init__(self, style: SubtitleStyle):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._style = style
        self._entries: OrderedDict[int, dict] = OrderedDict()
        self._status = ""
        self._drag_pos = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 12, 18, 12)
        self._layout.setSpacing(6)

        self.entry_added.connect(self._on_entry_added)
        self.translation_ready.connect(self._on_translation_ready)
        self.status_changed.connect(self._on_status)

        self.resize(style.width, 10)
        self._place_default()
        self._rebuild()

    def _place_default(self) -> None:
        screen = self.screen().availableGeometry()
        self.move(
            screen.center().x() - self._style.width // 2,
            screen.bottom() - 220,
        )

    # ---------- 数据更新（UI 线程） ----------

    @Slot(int, str, str)
    def _on_entry_added(self, entry_id: int, original: str, language: str) -> None:
        self._entries[entry_id] = {"original": original, "translation": "", "lang": language}
        while len(self._entries) > self._style.max_lines:
            self._entries.popitem(last=False)
        self._rebuild()

    @Slot(int, str)
    def _on_translation_ready(self, entry_id: int, translation: str) -> None:
        if entry_id in self._entries:
            self._entries[entry_id]["translation"] = translation
            self._rebuild()

    @Slot(str)
    def _on_status(self, text: str) -> None:
        self._status = text
        self._rebuild()

    def clear_entries(self) -> None:
        self._entries.clear()
        self._rebuild()

    # ---------- 渲染 ----------

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        fs = self._style.font_size
        for e in self._entries.values():
            # 源语言与目标语言一致时译文==原文，只显示一行
            same = e["translation"] and e["translation"] == e["original"]
            if self._style.show_original and e["original"] and not same:
                orig = QLabel(e["original"])
                orig.setWordWrap(True)
                orig.setStyleSheet(
                    f"color: rgba(255,255,255,0.55); font-size: {max(int(fs * 0.7), 10)}px;"
                )
                self._layout.addWidget(orig)
            trans = QLabel(e["translation"] or "…")
            trans.setWordWrap(True)
            trans.setStyleSheet(
                f"color: white; font-size: {fs}px; font-weight: 600;"
            )
            self._layout.addWidget(trans)

        if self._status:
            status = QLabel(self._status)
            status.setStyleSheet(
                f"color: rgba(255,220,120,0.9); font-size: {max(int(fs * 0.65), 10)}px;"
            )
            self._layout.addWidget(status)

        if not self._entries and not self._status:
            hint = QLabel("等待声音…")
            hint.setStyleSheet(
                f"color: rgba(255,255,255,0.4); font-size: {max(int(fs * 0.7), 10)}px;"
            )
            self._layout.addWidget(hint)

        self.setFixedWidth(self._style.width)
        self.adjustSize()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect(), 12, 12)
        p.fillPath(path, QColor(0, 0, 0, int(255 * self._style.opacity)))

    # ---------- 交互 ----------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            self._style.font_size = max(10, min(48, self._style.font_size + delta))
            self._rebuild()
