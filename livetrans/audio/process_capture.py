"""按进程捕获音频（Windows Process Loopback API）。

只捕获指定进程（及其子进程树）播放的声音，避免混入其他软件。
需要 Windows 10 2004+ / Windows 11。

参考 Windows ApplicationLoopback 官方示例：通过
ActivateAudioInterfaceAsync 激活 VAD\\Process_Loopback 虚拟设备。
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import POINTER, Structure, Union, byref, wintypes
from typing import Callable

import comtypes
import numpy as np
from comtypes import COMMETHOD, GUID, HRESULT, COMObject, IUnknown

log = logging.getLogger(__name__)

TARGET_RATE = 16000

# ---------- Win32 / WASAPI 常量与结构 ----------

VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK = "VAD\\Process_Loopback"
AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0
AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_PCM = 1
WAVE_FORMAT_IEEE_FLOAT = 3
VT_BLOB = 65
REFERENCE_TIME = ctypes.c_longlong


class AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS(Structure):
    _fields_ = [
        ("TargetProcessId", wintypes.DWORD),
        ("ProcessLoopbackMode", wintypes.DWORD),
    ]


class _ActivationUnion(Union):
    _fields_ = [("ProcessLoopbackParams", AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS)]


class AUDIOCLIENT_ACTIVATION_PARAMS(Structure):
    _fields_ = [("ActivationType", wintypes.DWORD), ("u", _ActivationUnion)]


class BLOB(Structure):
    _fields_ = [("cbSize", wintypes.ULONG), ("pBlobData", ctypes.c_void_p)]


class PROPVARIANT(Structure):
    class _U(Union):
        _fields_ = [("blob", BLOB)]

    _anonymous_ = ("u",)
    _fields_ = [
        ("vt", wintypes.USHORT),
        ("wReserved1", wintypes.USHORT),
        ("wReserved2", wintypes.USHORT),
        ("wReserved3", wintypes.USHORT),
        ("u", _U),
    ]


class WAVEFORMATEX(Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


# ---------- COM 接口定义 ----------

class IAudioClient(IUnknown):
    _iid_ = GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
    _methods_ = [
        COMMETHOD([], HRESULT, "Initialize",
                  (["in"], wintypes.DWORD, "ShareMode"),
                  (["in"], wintypes.DWORD, "StreamFlags"),
                  (["in"], REFERENCE_TIME, "hnsBufferDuration"),
                  (["in"], REFERENCE_TIME, "hnsPeriodicity"),
                  (["in"], POINTER(WAVEFORMATEX), "pFormat"),
                  (["in"], POINTER(GUID), "AudioSessionGuid")),
        COMMETHOD([], HRESULT, "GetBufferSize",
                  (["out"], POINTER(ctypes.c_uint32), "pNumBufferFrames")),
        COMMETHOD([], HRESULT, "GetStreamLatency",
                  (["out"], POINTER(REFERENCE_TIME), "phnsLatency")),
        COMMETHOD([], HRESULT, "GetCurrentPadding",
                  (["out"], POINTER(ctypes.c_uint32), "pNumPaddingFrames")),
        COMMETHOD([], HRESULT, "IsFormatSupported",
                  (["in"], wintypes.DWORD, "ShareMode"),
                  (["in"], POINTER(WAVEFORMATEX), "pFormat"),
                  (["out"], POINTER(POINTER(WAVEFORMATEX)), "ppClosestMatch")),
        COMMETHOD([], HRESULT, "GetMixFormat",
                  (["out"], POINTER(POINTER(WAVEFORMATEX)), "ppDeviceFormat")),
        COMMETHOD([], HRESULT, "GetDevicePeriod",
                  (["out"], POINTER(REFERENCE_TIME), "phnsDefaultDevicePeriod"),
                  (["out"], POINTER(REFERENCE_TIME), "phnsMinimumDevicePeriod")),
        COMMETHOD([], HRESULT, "Start"),
        COMMETHOD([], HRESULT, "Stop"),
        COMMETHOD([], HRESULT, "Reset"),
        COMMETHOD([], HRESULT, "SetEventHandle",
                  (["in"], wintypes.HANDLE, "eventHandle")),
        COMMETHOD([], HRESULT, "GetService",
                  (["in"], POINTER(GUID), "riid"),
                  (["out"], POINTER(POINTER(IUnknown)), "ppv")),
    ]


class IAudioCaptureClient(IUnknown):
    _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetBuffer",
                  (["out"], POINTER(POINTER(ctypes.c_ubyte)), "ppData"),
                  (["out"], POINTER(ctypes.c_uint32), "pNumFramesToRead"),
                  (["out"], POINTER(wintypes.DWORD), "pdwFlags"),
                  (["out"], POINTER(ctypes.c_uint64), "pu64DevicePosition"),
                  (["out"], POINTER(ctypes.c_uint64), "pu64QPCPosition")),
        COMMETHOD([], HRESULT, "ReleaseBuffer",
                  (["in"], ctypes.c_uint32, "NumFramesRead")),
        COMMETHOD([], HRESULT, "GetNextPacketSize",
                  (["out"], POINTER(ctypes.c_uint32), "pNumFramesInNextPacket")),
    ]


class IActivateAudioInterfaceAsyncOperation(IUnknown):
    _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetActivateResult",
                  (["out"], POINTER(HRESULT), "activateResult"),
                  (["out"], POINTER(POINTER(IUnknown)), "activatedInterface")),
    ]


class IActivateAudioInterfaceCompletionHandler(IUnknown):
    _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
    _methods_ = [
        COMMETHOD([], HRESULT, "ActivateCompleted",
                  (["in"], POINTER(IActivateAudioInterfaceAsyncOperation), "activateOperation")),
    ]


class IAgileObject(IUnknown):
    """标记接口：声明 handler 可跨 COM 套间调用（ActivateAudioInterfaceAsync 必需）。"""
    _iid_ = GUID("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}")
    _methods_ = []


class _CompletionHandler(COMObject):
    _com_interfaces_ = [IActivateAudioInterfaceCompletionHandler, IAgileObject]

    def __init__(self):
        super().__init__()
        self.done = threading.Event()

    def ActivateCompleted(self, activateOperation):
        self.done.set()
        return 0


_mmdevapi = ctypes.WinDLL("Mmdevapi")
_ActivateAudioInterfaceAsync = _mmdevapi.ActivateAudioInterfaceAsync
_ActivateAudioInterfaceAsync.restype = ctypes.c_long
_ActivateAudioInterfaceAsync.argtypes = [
    wintypes.LPCWSTR,
    POINTER(GUID),
    POINTER(PROPVARIANT),
    POINTER(IActivateAudioInterfaceCompletionHandler),
    POINTER(POINTER(IActivateAudioInterfaceAsyncOperation)),
]

_kernel32 = ctypes.WinDLL("kernel32")


# ---------- 进程枚举 ----------

def list_audio_processes() -> list[tuple[int, str, bool]]:
    """列出有音频会话的进程 (pid, 进程名, 是否活跃)。

    会话列表包含已过期条目（进程可能已停止发声甚至退出），
    is_active=True 表示当前正在发声。
    """
    from pycaw.pycaw import AudioUtilities

    result = []
    seen = set()
    for session in AudioUtilities.GetAllSessions():
        proc = session.Process
        if proc is None:
            continue
        try:
            name = proc.name()
            active = session.State == 1  # AudioSessionStateActive
        except Exception:
            continue
        if (proc.pid, name) not in seen:
            seen.add((proc.pid, name))
            result.append((proc.pid, name, active))
    return result


def find_pid_by_name(process_name: str) -> int:
    """按进程名解析要捕获的 PID（不区分大小写）。找不到抛 RuntimeError。

    返回同名进程树的根进程 PID：多进程软件（浏览器等）的声音由
    子进程播放且该子进程会随播放停止而退出重建，绑定根进程后
    include-tree 模式始终能覆盖到新产生的音频子进程。
    """
    import psutil

    target = process_name.lower()
    if not target.endswith(".exe"):
        target += ".exe"
    matches = [
        (pid, active) for pid, name, active in list_audio_processes()
        if name.lower() == target
    ]
    # 活跃会话优先；其次任意会话
    matches.sort(key=lambda m: not m[1])
    for pid, _active in matches:
        try:
            p = psutil.Process(pid)
            while True:
                parent = p.parent()
                if parent is not None and parent.name().lower() == target:
                    p = parent
                else:
                    break
            log.info("进程 %s: 会话 PID %d → 根进程 PID %d", target, pid, p.pid)
            return p.pid
        except psutil.Error:
            continue  # 会话残留的已退出进程，试下一个
    # 音频会话里没有，退而求其次：在所有进程里找同名根进程
    roots = [
        p for p in psutil.process_iter(["name", "ppid"])
        if (p.info["name"] or "").lower() == target
    ]
    for p in roots:
        try:
            if p.parent() is None or p.parent().name().lower() != target:
                log.info("进程 %s 无音频会话，使用根进程 PID %d", target, p.pid)
                return p.pid
        except psutil.Error:
            continue
    raise RuntimeError(f"未找到进程 {process_name}，请确认该软件正在运行")


# ---------- 捕获实现 ----------

class ProcessLoopbackCapture:
    """捕获指定进程树的音频，回调 on_chunk(float32 mono @16k)。

    与 LoopbackCapture 同接口：start() / stop() / device_name。
    """

    # 依次尝试的捕获格式 (tag, rate, channels, bits)
    _FORMATS = [
        (WAVE_FORMAT_IEEE_FLOAT, 16000, 1, 32),
        (WAVE_FORMAT_PCM, 48000, 2, 16),
    ]

    def __init__(self, on_chunk: Callable[[np.ndarray], None], pid: int, process_name: str = ""):
        self._on_chunk = on_chunk
        self._pid = pid
        self.device_name = f"进程 {process_name or pid} [Process Loopback]"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._init_done = threading.Event()
        self._init_error: Exception | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._init_done.clear()
        self._init_error = None
        self._thread = threading.Thread(
            target=self._run, name="livetrans-proc-capture", daemon=True
        )
        self._thread.start()
        if not self._init_done.wait(timeout=10):
            self._stop_event.set()
            raise RuntimeError("按进程音频捕获初始化超时")
        if self._init_error is not None:
            self._thread = None
            raise self._init_error

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    # ---- 捕获线程 ----

    def _run(self) -> None:
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass
        event_handle = None
        client = None
        try:
            client, fmt = self._activate_and_init()
            capture = client.GetService(byref(IAudioCaptureClient._iid_)).QueryInterface(
                IAudioCaptureClient
            )
            event_handle = _kernel32.CreateEventW(None, False, False, None)
            client.SetEventHandle(event_handle)
            client.Start()
            self._init_done.set()
            self._capture_loop(capture, fmt, event_handle)
        except Exception as e:
            log.exception("按进程捕获失败")
            self._init_error = e if isinstance(e, RuntimeError) else RuntimeError(str(e))
            self._init_done.set()
        finally:
            if client is not None:
                try:
                    client.Stop()
                except Exception:
                    pass
            if event_handle:
                _kernel32.CloseHandle(event_handle)
            comtypes.CoUninitialize()

    def _activate_and_init(self):
        params = AUDIOCLIENT_ACTIVATION_PARAMS()
        params.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK
        params.u.ProcessLoopbackParams.TargetProcessId = self._pid
        params.u.ProcessLoopbackParams.ProcessLoopbackMode = (
            PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE
        )

        prop = PROPVARIANT()
        prop.vt = VT_BLOB
        prop.blob.cbSize = ctypes.sizeof(params)
        prop.blob.pBlobData = ctypes.cast(byref(params), ctypes.c_void_p)

        handler = _CompletionHandler()
        handler_ptr = handler.QueryInterface(IActivateAudioInterfaceCompletionHandler)
        op = POINTER(IActivateAudioInterfaceAsyncOperation)()
        hr = _ActivateAudioInterfaceAsync(
            VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
            byref(IAudioClient._iid_),
            byref(prop),
            handler_ptr,
            byref(op),
        )
        if hr < 0:
            raise RuntimeError(f"ActivateAudioInterfaceAsync 失败 (hr=0x{hr & 0xFFFFFFFF:08X})")
        if not handler.done.wait(timeout=5):
            raise RuntimeError("音频接口激活超时")
        activate_hr, unk = op.GetActivateResult()
        if activate_hr < 0:
            raise RuntimeError(
                f"进程环回激活失败 (hr=0x{activate_hr & 0xFFFFFFFF:08X})，"
                "需要 Windows 10 2004+ 且目标进程存在"
            )
        client = unk.QueryInterface(IAudioClient)

        last_error: Exception | None = None
        for tag, rate, channels, bits in self._FORMATS:
            fmt = WAVEFORMATEX(
                wFormatTag=tag,
                nChannels=channels,
                nSamplesPerSec=rate,
                nAvgBytesPerSec=rate * channels * bits // 8,
                nBlockAlign=channels * bits // 8,
                wBitsPerSample=bits,
                cbSize=0,
            )
            try:
                client.Initialize(
                    AUDCLNT_SHAREMODE_SHARED,
                    AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK,
                    2_000_000,  # 200ms 缓冲
                    0,
                    byref(fmt),
                    None,
                )
                return client, (tag, rate, channels, bits)
            except Exception as e:
                last_error = e
        raise RuntimeError(f"音频客户端 Initialize 失败: {last_error}")

    def _capture_loop(self, capture, fmt, event_handle) -> None:
        tag, rate, channels, bits = fmt
        block_align = channels * bits // 8
        while not self._stop_event.is_set():
            _kernel32.WaitForSingleObject(event_handle, 100)
            while True:
                packet = capture.GetNextPacketSize()
                if packet == 0:
                    break
                data_ptr, frames, flags, _pos, _qpc = capture.GetBuffer()
                try:
                    if frames == 0:
                        continue
                    if flags & AUDCLNT_BUFFERFLAGS_SILENT:
                        buf = np.zeros(frames * channels, dtype=np.float32)
                    else:
                        raw = ctypes.string_at(data_ptr, frames * block_align)
                        if tag == WAVE_FORMAT_IEEE_FLOAT:
                            buf = np.frombuffer(raw, dtype=np.float32).copy()
                        else:
                            buf = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
                    if channels > 1:
                        buf = buf.reshape(-1, channels).mean(axis=1)
                    if rate != TARGET_RATE:
                        n_out = int(round(len(buf) * TARGET_RATE / rate))
                        if n_out > 0:
                            x_old = np.linspace(0.0, 1.0, num=len(buf), endpoint=False)
                            x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                            buf = np.interp(x_new, x_old, buf).astype(np.float32)
                        else:
                            buf = np.empty(0, dtype=np.float32)
                    if len(buf):
                        self._on_chunk(buf)
                finally:
                    capture.ReleaseBuffer(frames)
