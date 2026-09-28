"""Windows: WASAPI loopback for devices, Process Loopback API for applications."""
from __future__ import annotations

from ..base import AudioApp, AudioBackend, Device


class WindowsBackend(AudioBackend):
    name = "windows"
    system_hint = "捕获此设备正在播放的声音，不需要虚拟声卡。"
    app_hint = "先让软件播放声音再刷新，也可直接输入 chrome.exe 等进程名。需要 Windows 11。"

    def list_devices(self):
        from .loopback import list_loopback_devices

        return [Device(str(int(d["index"])), d["name"]) for d in list_loopback_devices()]

    def list_apps(self):
        import comtypes

        from .process_loopback import list_audio_processes

        comtypes.CoInitialize()
        try:
            rows = sorted(list_audio_processes(), key=lambda row: not row[2])
        finally:
            comtypes.CoUninitialize()
        apps, seen = [], set()
        for _, name, active in rows:
            if name not in seen:
                seen.add(name)
                apps.append(AudioApp(name, name, active))
        return apps

    def open_system(self, on_chunk, device=""):
        from .loopback import LoopbackCapture

        return LoopbackCapture(on_chunk, device_index=int(device) if device else -1)

    def open_app(self, on_chunk, app):
        import comtypes

        from .process_loopback import ProcessLoopbackCapture, find_pid_by_name

        comtypes.CoInitialize()
        try:
            pid = find_pid_by_name(app)
        finally:
            comtypes.CoUninitialize()
        return ProcessLoopbackCapture(on_chunk, pid=pid, process_name=app)
