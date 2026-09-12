"""QML interaction checks using synthetic Qt events and isolated configuration."""
from __future__ import annotations

import tempfile
import unittest
from ctypes import byref, c_ssize_t, windll, wintypes
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QPointF, Qt
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest

from livetrans.config import AppConfig
from livetrans.main import App
from tests.test_frontend import FakeRuntime


class QmlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = FakeRuntime()
        self.discovery = patch(
            "livetrans.ui.controller.AppController._discover",
            lambda c: c._devicesReady.emit([], [{"label": "demo.exe", "value": "demo.exe"}], ""),
        )
        self.discovery.start()
        self.app = App(AppConfig(), Path(self.temp.name) / "config.json", self.runtime)
        self.errors = []
        self.app.engine.warnings.connect(lambda values: self.errors.extend(str(v) for v in values))
        self.window = self.app.main_window
        self.app.show_main()
        QTest.qWait(80)

    def tearDown(self):
        self.app.shutdown()
        self.discovery.stop()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def item(self, name):
        found = next((item for item in self.visual_items(self.window)
                      if item.objectName() == name), None)
        self.assertIsNotNone(found, name)
        return found

    @staticmethod
    def visual_items(window):
        # Repeater delegates are visual children, not necessarily QObject-owned children.
        pending = [window.contentItem()]
        while pending:
            item = pending.pop()
            yield item
            pending.extend(item.childItems())

    def click(self, item):
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton, pos=point)
        QTest.qWait(60)

    def page(self, index):
        self.click(self.item(f"nav{index}"))
        self.assertEqual(self.window.property("currentPage"), index)

    def test_navigation_input_and_cross_page_draft(self):
        self.page(3)
        combo = self.item("translate.target_language")
        self.assertFalse(combo.property("editable"))
        combo.forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key.Key_Down)
        QTest.qWait(30)
        self.assertEqual(self.app.controller.settings.draft["translate"]["target_language"],
                         "繁体中文")
        field = self.item("translate.model")
        field.forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        # A Unicode IME commit follows the same inputMethodEvent path as Windows IME.
        event = QInputMethodEvent()
        event.setCommitString("日本語")
        QCoreApplication.sendEvent(field, event)
        QTest.qWait(20)
        self.assertEqual(self.app.controller.settings.draft["translate"]["model"],
                         "日本語")
        self.page(5)
        self.page(3)
        self.assertEqual(self.item("translate.model").property("text"), "日本語")
        self.assertEqual(self.item("translate.target_language").property("currentValue"),
                         "繁体中文")
        self.assertEqual(self.app.controller.cfg.translate.target_language, "中文")
        self.click(self.item("applySettings"))
        self.assertEqual(self.app.controller.cfg.translate.target_language, "繁体中文")

    def test_resize_keeps_window_position_and_subtitle_updates_keep_user_position(self):
        start = self.window.position()
        for width, height in ((900, 650), (810, 560), (1040, 720)):
            self.window.resize(width, height)
            QTest.qWait(30)
            self.assertEqual(self.window.position(), start)
        overlay = self.app.subtitle_window
        overlay.setPosition(70, 90)
        self.app.controller.start()
        self.runtime.send("started", device="test", paused=False)
        self.runtime.send("entry", id=1, original="hello " * 80, language="en")
        QTest.qWait(40)
        self.app.controller.settings.setValue("subtitle.width", 600)
        self.app.controller.applySettings()
        QTest.qWait(40)
        self.assertEqual((overlay.x(), overlay.y()), (70, 90))

    def test_existing_custom_language_stays_selected(self):
        self.app.controller.settings.setValue("translate.target_language", "粤语")
        self.page(3)
        combo = self.item("translate.target_language")
        self.assertGreaterEqual(combo.property("currentIndex"), 0)
        self.assertEqual(combo.property("currentValue"), "粤语")

    def test_backend_switch_keyboard_and_validation_navigation(self):
        self.page(2)
        combo = self.item("asr.backend")
        combo.forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key.Key_Down)
        QTest.qWait(30)
        self.assertEqual(self.app.controller.settings.draft["asr"]["backend"], "cloud")
        self.assertTrue(self.item("asr.cloud_base_url").isVisible())
        self.assertFalse(self.item("asr.model").isVisible())
        self.app.controller.settings.setValue("asr.cloud_base_url", "invalid")
        self.page(5)
        self.click(self.item("applySettings"))
        self.assertEqual(self.window.property("currentPage"), 2)
        self.assertTrue(self.app.controller.settings.dirty)
        self.assertIn("asr.cloud_base_url", self.app.controller.settings.errors)

    def test_numeric_edit_can_apply_without_leaving_field(self):
        self.page(4)
        field = self.item("subtitle.font_size")
        field.forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(self.window, Qt.Key.Key_3)
        QTest.keyClick(self.window, Qt.Key.Key_0)
        self.assertTrue(self.app.controller.settings.dirty)
        QTest.keyClick(self.window, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        QTest.qWait(30)
        self.assertEqual(self.app.controller.cfg.subtitle.font_size, 30)

    def test_incremental_model_is_visible_in_both_windows_and_long_text_wraps(self):
        self.app.controller.start()
        self.runtime.send("started", device="test", paused=False)
        self.runtime.send("entry", id=1, original="hello " * 80, language="en")
        self.runtime.send("translation", id=1, translation="实时字幕" * 80)
        QTest.qWait(60)
        for window in (self.window, self.app.subtitle_window):
            visible_text = [obj.property("text") for obj in self.visual_items(window)
                            if obj.isVisible() and obj.property("text")]
            self.assertIn("实时字幕" * 80, visible_text)
        screen_height = self.app.subtitle_window.screen().availableGeometry().height()
        self.assertLessEqual(self.app.subtitle_window.height(), screen_height * 0.6 + 1)
        self.app.controller.settings.setValue("subtitle.font_size", 32)
        self.app.controller.applySettings()
        self.assertEqual(len(self.runtime.starts), 1)
        self.assertEqual(self.app.controller.subtitles.rowCount(), 1)

    def test_pages_resize_theme_and_hidden_window_has_no_animation_frames(self):
        for index in range(6):
            self.page(index)
        self.window.resize(800, 540)
        QTest.qWait(40)
        if self.app.qt.platformName() == "windows":
            user = windll.user32
            hwnd = wintypes.HWND(int(self.window.winId()))
            rect = wintypes.RECT()
            user.GetWindowRect(hwnd, byref(rect))
            user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                         wintypes.WPARAM, wintypes.LPARAM]
            user.SendMessageW.restype = c_ssize_t
            x, y = rect.right - 2, (rect.top + rect.bottom) // 2
            hit = user.SendMessageW(hwnd, 0x0084, 0, ((y & 0xFFFF) << 16) | (x & 0xFFFF))
            self.assertEqual(hit, 11)  # HTRIGHT: the native frame actually accepts resizing.
            with patch.object(self.app.window_controls, "showSystemMenu") as show_menu:
                user.PostMessageW(hwnd, 0x0104, 0x20, 1 << 29)  # Alt+Space
                QTest.qWait(30)
                show_menu.assert_called_once()
        self.assertLessEqual(self.item("applySettings").mapToScene(QPointF(0, 0)).y(), 540)
        self.app.controller.settings.setValue("ui.theme", "dark")
        self.app.controller.settings.setValue("ui.reduce_transparency", True)
        self.app.controller.settings.setValue("ui.reduce_motion", True)
        self.app.controller.applySettings()
        self.assertTrue(self.app.appearance.dark)
        self.assertFalse(self.app.appearance.mainGlass)
        self.assertTrue(self.app.appearance.reduceMotion)
        frames = []
        self.window.frameSwapped.connect(lambda: frames.append(True))
        self.window.hide()
        QTest.qWait(100)
        baseline = len(frames)
        QTest.qWait(250)
        self.assertEqual(len(frames), baseline)

    def test_preview_draft_does_not_change_overlay_and_close_preserves_draft(self):
        self.page(4)
        self.app.controller.settings.setValue("subtitle.font_size", 40)
        self.assertEqual(self.app.controller.committed["subtitle"]["font_size"], 22)
        self.window.close()
        QTest.qWait(30)
        self.assertFalse(self.window.isVisible())
        self.app.show_main()
        self.assertEqual(self.app.controller.settings.draft["subtitle"]["font_size"], 40)


if __name__ == "__main__":
    unittest.main()
