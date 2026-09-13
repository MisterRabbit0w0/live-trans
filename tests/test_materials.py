"""Native material eligibility and accessibility without changing system settings."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from livetrans.config import AppConfig
from livetrans.ui.materials import Appearance, apply_acrylic
from tests.test_frontend import QT_APP


class MaterialTests(unittest.TestCase):
    def test_unsupported_windows_does_not_touch_window(self):
        window = Mock()
        with patch("livetrans.ui.materials.sys.getwindowsversion",
                   return_value=SimpleNamespace(build=19045), create=True):
            self.assertFalse(apply_acrylic(window, True, False))
        window.winId.assert_not_called()

    def test_dwm_failure_and_explicit_disable_choose_fallback(self):
        calls = []

        def set_attribute(hwnd, key, value, size):
            calls.append((key, value._obj.value))
            return -1 if key == 38 else 0

        dwm = SimpleNamespace(DwmSetWindowAttribute=set_attribute,
                              DwmExtendFrameIntoClientArea=lambda *args: 0)
        window = Mock()
        window.winId.return_value = 123
        with patch("livetrans.ui.materials.sys.platform", "win32"), patch(
            "livetrans.ui.materials.sys.getwindowsversion",
            return_value=SimpleNamespace(build=22621), create=True,
        ), patch("livetrans.ui.materials.ctypes.windll",
                 SimpleNamespace(dwmapi=dwm), create=True):
            self.assertFalse(apply_acrylic(window, True, True))
            self.assertIn((38, 3), calls)
            dwm.DwmSetWindowAttribute = lambda hwnd, key, value, size: 0
            self.assertFalse(apply_acrylic(window, False, False))

    def test_system_preferences_override_effects_and_high_contrast_overrides_theme(self):
        cfg = AppConfig()
        cfg.ui.theme = "light"
        with patch("livetrans.ui.materials.system_preferences",
                   return_value=(True, False, False, True)), patch(
            "livetrans.ui.materials.apply_acrylic",
            side_effect=lambda w, enabled, dark, **kwargs: enabled,
        ):
            appearance = Appearance(cfg)
            appearance.attach(Mock(), Mock())
            self.assertTrue(appearance.dark)
            self.assertTrue(appearance.highContrast)
            self.assertTrue(appearance.reduceMotion)
            self.assertFalse(appearance.mainGlass)
            self.assertFalse(appearance.subtitleGlass)
            appearance.stop()

    def test_user_reductions_and_zero_opacity_disable_material_independently(self):
        self.assertIsNotNone(QT_APP)
        cfg = AppConfig()
        cfg.subtitle.opacity = 0
        with patch("livetrans.ui.materials.system_preferences",
                   return_value=(False, True, True, False)), patch(
            "livetrans.ui.materials.apply_acrylic",
            side_effect=lambda w, enabled, dark, **kwargs: enabled,
        ):
            appearance = Appearance(cfg)
            appearance.attach(Mock(), Mock())
            self.assertTrue(appearance.mainGlass)
            self.assertFalse(appearance.subtitleGlass)
            cfg.ui.reduce_transparency = cfg.ui.reduce_motion = True
            appearance.configure(cfg)
            self.assertFalse(appearance.mainGlass)
            self.assertTrue(appearance.reduceMotion)
            appearance.stop()


if __name__ == "__main__":
    unittest.main()
