"""Documented DWM Acrylic plus accessible, opaque fallbacks."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import Property, QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from ..config import AppConfig


def system_preferences():
    dark = QGuiApplication.styleHints().colorScheme().name == "Dark"
    animation, transparent, high_contrast = True, True, False
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                dark = not bool(winreg.QueryValueEx(key, "AppsUseLightTheme")[0])
                transparent = bool(winreg.QueryValueEx(key, "EnableTransparency")[0])
        except OSError:
            pass

        class HighContrast(ctypes.Structure):
            _fields_ = [("size", wintypes.UINT), ("flags", wintypes.DWORD),
                        ("scheme", wintypes.LPWSTR)]

        contrast = HighContrast()
        contrast.size = ctypes.sizeof(contrast)
        animate = wintypes.BOOL(True)
        spi = ctypes.windll.user32.SystemParametersInfoW
        if spi(0x0042, contrast.size, ctypes.byref(contrast), 0):
            high_contrast = bool(contrast.flags & 1)
        if spi(0x1042, 0, ctypes.byref(animate), 0):
            animation = bool(animate.value)
    return dark, animation, transparent, high_contrast


def apply_acrylic(window, enabled: bool, dark: bool, *, high_contrast: bool = False) -> bool:
    if sys.platform != "win32":
        return False
    build = sys.getwindowsversion().build
    if build < 22000:
        return False

    class Margins(ctypes.Structure):
        _fields_ = [(name, ctypes.c_int) for name in ("left", "right", "top", "bottom")]

    try:
        dwm = ctypes.windll.dwmapi
    except OSError:
        return False
    hwnd = wintypes.HWND(int(window.winId()))

    def attribute(key, value, data_type=ctypes.c_int):
        data = data_type(value)
        return dwm.DwmSetWindowAttribute(hwnd, key, ctypes.byref(data), ctypes.sizeof(data))

    attribute(20, int(dark))  # DWMWA_USE_IMMERSIVE_DARK_MODE
    attribute(33, 2)  # DWMWCP_ROUND
    # Remove DWM's separate outline as well as the legacy resize frame handled
    # by WindowControls. Keep the system outline for high-contrast themes.
    # These frame attributes work on Win11 even without Desktop Acrylic.
    attribute(34, 0xFFFFFFFF if high_contrast else 0xFFFFFFFE, ctypes.c_uint32)
    if build < 22621:
        return False
    attribute(2, 2)  # DWMNCRP_ENABLED
    # The alpha surface still needs a fully extended client area when the
    # backdrop is disabled (for example the subtitle's zero-opacity setting).
    # Opaque fallback colors are drawn by QML; NONE below disables Acrylic.
    margins = Margins(-1, -1, -1, -1)
    extended = dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
    result = attribute(38, 3 if enabled else 1)  # TRANSIENTWINDOW / NONE
    # A successful call requests the system material. DWM can still choose its
    # opaque fallback (for example when desktop effects are unavailable).
    return enabled and extended == 0 and result == 0


class Appearance(QObject):
    changed = Signal()

    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._windows = []
        self._effective = None
        self._main_glass = self._subtitle_glass = False
        self._dark = self._motion = self._contrast = False
        self.refresh()
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def attach(self, main, subtitle):
        self._windows = [main, subtitle]
        for window in self._windows:
            window.visibleChanged.connect(self._visibility_changed)
        self.refresh(force=True)

    def _visibility_changed(self, visible):
        if visible:
            self.refresh(force=True)

    def configure(self, cfg):
        self._cfg = cfg
        self.refresh(force=True)

    def stop(self):
        self._timer.stop()
        self._windows = []

    def refresh(self, force=False):
        dark, animation, transparent, contrast = system_preferences()
        ui = self._cfg.ui
        self._dark = dark if ui.theme == "system" or contrast else ui.theme == "dark"
        self._motion = ui.reduce_motion or not animation or contrast
        self._contrast = contrast
        glass = transparent and not ui.reduce_transparency and not contrast
        effective = (self._dark, self._motion, contrast, glass, self._cfg.subtitle.opacity)
        if effective == self._effective and not force:
            return
        self._effective = effective
        if self._windows:
            self._main_glass = apply_acrylic(
                self._windows[0], glass, self._dark, high_contrast=contrast,
            )
            self._subtitle_glass = apply_acrylic(
                self._windows[1], glass and self._cfg.subtitle.opacity > 0, True,
                high_contrast=contrast,
            )
        self.changed.emit()

    @Property(bool, notify=changed)
    def dark(self):
        return self._dark

    @Property(bool, notify=changed)
    def reduceMotion(self):
        return self._motion

    @Property(bool, notify=changed)
    def highContrast(self):
        return self._contrast

    @Property(bool, notify=changed)
    def mainGlass(self):
        return self._main_glass

    @Property(bool, notify=changed)
    def subtitleGlass(self):
        return self._subtitle_glass
