"""Keep Win32 resize / system-menu behavior with a custom QML title bar."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import (
    Property,
    QAbstractNativeEventFilter,
    QCoreApplication,
    QObject,
    Qt,
    QTimer,
    Slot,
)
from PySide6.QtGui import QGuiApplication, QWindow


class _NativeFrame(QAbstractNativeEventFilter):
    def __init__(self, controls):
        super().__init__()
        self.controls = controls

    def nativeEventFilter(self, event_type, message):
        c = self.controls
        if c.window is None or event_type != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.hWnd != c.hwnd:
            return False, 0
        if msg.message == 0x0083:  # WM_NCCALCSIZE
            # Keep a regular, non-layered HWND for DWM / DirectComposition,
            # but make the client area fill the window. Handle both forms:
            # FALSE supplies a RECT; TRUE supplies NCCALCSIZE_PARAMS whose
            # first field is that RECT. Default processing would inset it.
            if msg.wParam and ctypes.windll.user32.IsZoomed(wintypes.HWND(c.hwnd)):
                c._fit_maximized_client(msg.lParam)
            return True, 0
        if msg.message in (0x00AE, 0x00AF):  # WM_NCUAHDRAWCAPTION / WM_NCUAHDRAWFRAME
            # Legacy theme painting can redraw the resize frame over QML even
            # after NCCALCSIZE removes it. Leave WM_NCPAINT to DWM for shadows.
            return True, 0
        if msg.message == 0x0014:  # WM_ERASEBKGND
            c._clear_backing(wintypes.HDC(msg.wParam))
            return True, 1
        if msg.message == 0x000F:  # WM_PAINT
            # Qt draws into a DirectComposition surface and skips clearing the
            # HWND's GDI backing. Its opaque pixels otherwise hide the backdrop.
            # Clear only on native paint, then let Qt handle exposure normally.
            c._backing_dirty = True
            return False, 0
        if msg.message == 0x0086:  # WM_NCACTIVATE
            if ctypes.windll.user32.IsIconic(wintypes.HWND(c.hwnd)):
                return False, 0
            # The subtitle is a persistent overlay, usually over an active
            # player. Keep its *frame appearance* active without moving focus.
            # Main-window activation follows Windows normally. In both cases,
            # lParam=-1 prevents DefWindowProc repainting the native resize
            # frame over our client area. WM_ACTIVATE still goes through Qt.
            proc = ctypes.windll.user32.DefWindowProcW
            proc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            proc.restype = ctypes.c_ssize_t
            active = 1 if c.persistent_material else msg.wParam
            return True, proc(wintypes.HWND(c.hwnd), msg.message, active, -1)
        if msg.message == 0x0104 and msg.wParam == 0x20:  # WM_SYSKEYDOWN, Alt+Space
            QTimer.singleShot(0, c.showSystemMenu)
            return True, 0
        if (msg.message != 0x0084 or not c.resizable
                or c.window.visibility() == QWindow.Visibility.Maximized):
            return False, 0
        # Native hit testing keeps resize cursors and non-client mouse gestures
        # working even when the input lands on DWM's outer border.
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(wintypes.HWND(c.hwnd), ctypes.byref(rect))
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        border = max(6, round(6 * c.window.devicePixelRatio()))
        left, right = x < rect.left + border, x >= rect.right - border
        top, bottom = y < rect.top + border, y >= rect.bottom - border
        hit = (13 if left else 14 if right else 12) if top else (
            (16 if left else 17 if right else 15) if bottom else 10 if left else 11 if right else 0
        )
        return (True, hit) if hit else (False, 0)


class WindowControls(QObject):
    def __init__(self, parent=None, *, resizable=True, persistent_material=False):
        super().__init__(parent)
        self.resizable = resizable
        self.persistent_material = persistent_material
        self.window = None
        self.hwnd = None
        self._filter = None
        self._backing_dirty = True

    @Property(bool, constant=True)
    def nativeFrame(self):
        return sys.platform == "win32" and QGuiApplication.platformName() == "windows"

    def attach(self, window):
        self.window = window
        if self.nativeFrame:
            self.hwnd = int(window.winId())
            self._filter = _NativeFrame(self)
            QCoreApplication.instance().installNativeEventFilter(self._filter)
            # Recalculate the client area once, after installing WM_NCCALCSIZE.
            ctypes.windll.user32.SetWindowPos(
                wintypes.HWND(self.hwnd), None, 0, 0, 0, 0, 0x0037,
            )
            window.visibleChanged.connect(
                self._visibility_changed,
            )
            window.frameSwapped.connect(self._frame_presented, Qt.ConnectionType.QueuedConnection)

    def _visibility_changed(self, visible):
        if visible:
            self._backing_dirty = True
            if self.persistent_material:
                ctypes.windll.user32.PostMessageW(wintypes.HWND(self.hwnd), 0x0086, 1, -1)

    @Slot()
    def _frame_presented(self):
        # The HWND backing is allocated on the first present. Clearing before
        # that is too early; subsequent native invalidations need the same fix.
        if self._backing_dirty:
            self._clear_backing()
            self._backing_dirty = False

    def detach(self):
        if self._filter is not None:
            QCoreApplication.instance().removeNativeEventFilter(self._filter)
            self._filter = None
        self.window = None

    def _clear_backing(self, dc=None):
        if self.window is None:
            return
        user = ctypes.windll.user32
        gdi = ctypes.windll.gdi32
        hwnd = wintypes.HWND(self.hwnd)
        user.GetDC.argtypes = [wintypes.HWND]
        user.GetDC.restype = wintypes.HDC
        user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
        gdi.GetStockObject.argtypes = [ctypes.c_int]
        gdi.GetStockObject.restype = wintypes.HBRUSH
        own_dc = dc is None
        dc = user.GetDC(hwnd) if own_dc else dc
        if not dc:
            return
        try:
            rect = wintypes.RECT()
            user.GetClientRect(hwnd, ctypes.byref(rect))
            user.FillRect(dc, ctypes.byref(rect), gdi.GetStockObject(4))  # BLACK_BRUSH: alpha 0
            gdi.GdiFlush()
        finally:
            if own_dc:
                user.ReleaseDC(hwnd, dc)

    def _fit_maximized_client(self, address):
        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD)]

        user = ctypes.windll.user32
        user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user.MonitorFromWindow.restype = wintypes.HANDLE
        user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        monitor = user.MonitorFromWindow(wintypes.HWND(self.hwnd), 2)
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        if user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            # The first member of NCCALCSIZE_PARAMS is the new client RECT.
            rect = wintypes.RECT.from_address(address)
            rect.left, rect.top = info.work.left, info.work.top
            rect.right, rect.bottom = info.work.right, info.work.bottom

    @Slot()
    def showSystemMenu(self):
        if not self.nativeFrame or self.window is None:
            return
        user = ctypes.windll.user32
        hwnd = wintypes.HWND(int(self.window.winId()))
        user.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
        user.GetSystemMenu.restype = wintypes.HMENU
        menu = wintypes.HMENU(user.GetSystemMenu(hwnd, False))
        rect = wintypes.RECT()
        user.GetWindowRect(hwnd, ctypes.byref(rect))
        maximized = self.window.visibility() == QWindow.Visibility.Maximized
        for command, enabled in ((0xF120, maximized), (0xF030, not maximized),
                                 (0xF000, not maximized), (0xF010, not maximized)):
            user.EnableMenuItem(menu, command, 0 if enabled else 1)
        scale = self.window.devicePixelRatio()
        command = user.TrackPopupMenu(menu, 0x0102, rect.left + round(16 * scale),
                                     rect.top + round(44 * scale), 0, hwnd, None)
        if command:
            user.PostMessageW(hwnd, 0x0112, command, 0)  # WM_SYSCOMMAND
