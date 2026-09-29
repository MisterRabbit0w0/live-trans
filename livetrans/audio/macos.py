"""macOS: ScreenCaptureKit audio (macOS 13+), no virtual audio device needed.

The first capture asks for the Screen Recording permission; macOS only grants
it after the user allows LiveTrans in System Settings › Privacy & Security.
ScreenCaptureKit captures per display, so the video stream is kept at the
smallest size and frame rate and its frames are discarded.
"""
from __future__ import annotations

import logging
import threading

import numpy as np

from .base import AudioApp, AudioBackend, ChunkCallback, Device, to_mono_16k

log = logging.getLogger(__name__)

SAMPLE_RATE = 48000  # ScreenCaptureKit supports 8/16/24/48 kHz; 48 kHz is the native mix
AUDIO_OUTPUT = 1  # SCStreamOutputTypeAudio
NON_INTERLEAVED = 1 << 5  # kAudioFormatFlagIsNonInterleaved
TIMEOUT_S = 10


def _frameworks():
    try:
        import CoreMedia
        import objc
        import ScreenCaptureKit
    except ImportError as error:
        raise RuntimeError(
            "缺少 ScreenCaptureKit 绑定，请安装 pyobjc-framework-ScreenCaptureKit"
        ) from error
    return objc, ScreenCaptureKit, CoreMedia


def _await(start, what):
    """Run an async ScreenCaptureKit call and wait for its completion handler."""
    done, box = threading.Event(), {}

    def handler(*args):
        box["args"] = args
        done.set()

    start(handler)
    if not done.wait(TIMEOUT_S):
        raise RuntimeError(f"{what}超时")
    args = box["args"]
    error = args[-1]
    if error is not None:
        raise RuntimeError(f"{what}失败：{error.localizedDescription()}"
                           "（请在 系统设置 › 隐私与安全性 › 屏幕录制 中允许 LiveTrans）")
    return args[0] if len(args) > 1 else None


def _shareable_content():
    _, sck, _ = _frameworks()
    return _await(sck.SCShareableContent.getShareableContentWithCompletionHandler_,
                  "读取可捕获内容")


def _app_names(app) -> set[str]:
    names = {app.applicationName() or "", app.bundleIdentifier() or ""}
    return {n.lower() for n in names if n}


_output_class = None


def _output_type():
    """Define the Objective-C delegate class once per process."""
    global _output_class
    if _output_class is not None:
        return _output_class
    objc, _, cm = _frameworks()
    from Foundation import NSObject

    protocols = [objc.protocolNamed("SCStreamOutput"), objc.protocolNamed("SCStreamDelegate")]

    class LiveTransAudioOutput(NSObject, protocols=protocols):
        def initWithCallback_(self, callback):
            self = objc.super(LiveTransAudioOutput, self).init()
            if self is None:
                return None
            self._callback = callback
            return self

        def stream_didOutputSampleBuffer_ofType_(self, stream, buffer, kind):
            if kind != AUDIO_OUTPUT or not cm.CMSampleBufferIsValid(buffer):
                return
            try:
                self._callback(_samples(cm, buffer))
            except Exception:
                log.exception("处理 ScreenCaptureKit 音频失败")

        def stream_didStopWithError_(self, stream, error):
            log.warning("ScreenCaptureKit 捕获已停止：%s", error.localizedDescription())

    _output_class = LiveTransAudioOutput
    return _output_class


def _samples(cm, buffer) -> np.ndarray:
    description = cm.CMSampleBufferGetFormatDescription(buffer)
    asbd = cm.CMAudioFormatDescriptionGetStreamBasicDescription(description)
    if hasattr(asbd, "pointee"):
        asbd = asbd.pointee
    elif isinstance(asbd, (list, tuple)):
        asbd = asbd[0]
    rate = int(asbd.mSampleRate) or SAMPLE_RATE
    channels = max(1, int(asbd.mChannelsPerFrame))
    block = cm.CMSampleBufferGetDataBuffer(buffer)
    length = cm.CMBlockBufferGetDataLength(block)
    status, data = cm.CMBlockBufferCopyDataBytes(block, 0, length, None)
    if status != 0 or not data:
        return np.empty(0, dtype=np.float32)
    buf = np.frombuffer(bytes(data), dtype=np.float32)
    if channels > 1 and asbd.mFormatFlags & NON_INTERLEAVED:
        # Planar: one contiguous block per channel.
        frames = len(buf) // channels
        return to_mono_16k(buf[: frames * channels].reshape(channels, -1).mean(axis=0),
                           rate, 1)
    return to_mono_16k(buf, rate, channels)


class ScreenCaptureKitCapture:
    def __init__(self, on_chunk: ChunkCallback, *, display: str = "", app: str = ""):
        self._on_chunk = on_chunk
        self._display = display
        self._app = app.strip().lower()
        self.device_name = (f"应用 {app}" if app else "系统声音") + " [ScreenCaptureKit]"
        self._stream = None
        self._output = None
        self._stopped = threading.Event()

    def start(self) -> None:
        if self._stream is not None:
            return
        _, sck, cm = _frameworks()
        content = _shareable_content()
        displays = list(content.displays())
        if not displays:
            raise RuntimeError("没有可捕获的显示器")
        display = next((d for d in displays if str(d.displayID()) == self._display), displays[0])
        if self._app:
            apps = [a for a in content.applications() if self._app in _app_names(a)]
            if not apps:
                raise RuntimeError(f"未找到正在运行的应用 {self._app}")
            content_filter = sck.SCContentFilter.alloc() \
                .initWithDisplay_includingApplications_exceptingWindows_(display, apps, [])
        else:
            content_filter = sck.SCContentFilter.alloc() \
                .initWithDisplay_excludingWindows_(display, [])

        config = sck.SCStreamConfiguration.alloc().init()
        config.setCapturesAudio_(True)
        config.setExcludesCurrentProcessAudio_(True)
        config.setSampleRate_(SAMPLE_RATE)
        config.setChannelCount_(1)
        config.setWidth_(2)
        config.setHeight_(2)
        config.setMinimumFrameInterval_(cm.CMTimeMake(1, 1))
        config.setQueueDepth_(1)

        self._stopped.clear()
        output = _output_type().alloc().initWithCallback_(self._deliver)
        stream = sck.SCStream.alloc().initWithFilter_configuration_delegate_(
            content_filter, config, output)
        ok, error = stream.addStreamOutput_type_sampleHandlerQueue_error_(
            output, AUDIO_OUTPUT, None, None)
        if not ok:
            raise RuntimeError(f"无法添加音频输出：{error.localizedDescription() if error else ''}")
        _await(stream.startCaptureWithCompletionHandler_, "启动 ScreenCaptureKit 捕获")
        self._stream, self._output = stream, output

    def _deliver(self, chunk):
        if len(chunk) and not self._stopped.is_set():
            self._on_chunk(chunk)

    def stop(self, timeout: float = 3.0) -> bool:
        self._stopped.set()
        stream = self._stream
        if stream is None:
            return True
        try:
            _await(stream.stopCaptureWithCompletionHandler_, "停止 ScreenCaptureKit 捕获")
        except RuntimeError as error:
            # A stream that already stopped on its own reports an error; it is gone either way.
            log.warning("%s", error)
        self._stream = self._output = None
        return True


class MacBackend(AudioBackend):
    name = "macos"
    default_device_label = "主显示器的系统声音"
    system_hint = "通过 ScreenCaptureKit 捕获系统声音，需要 macOS 13+ 和屏幕录制权限。"
    app_hint = "从列表选择正在运行的应用，也可直接输入应用名或 Bundle ID。"

    def list_devices(self):
        displays = list(_shareable_content().displays())
        if len(displays) < 2:
            return []
        return [Device(str(d.displayID()), f"显示器 {n + 1}（{d.width()}×{d.height()}）")
                for n, d in enumerate(displays)]

    def list_apps(self):
        apps, seen = [], set()
        for app in _shareable_content().applications():
            name = app.applicationName() or app.bundleIdentifier()
            if name and name not in seen and app.processID() > 0:
                seen.add(name)
                apps.append(AudioApp(name, name))
        return sorted(apps, key=lambda a: a.name.lower())

    def open_system(self, on_chunk, device=""):
        return ScreenCaptureKitCapture(on_chunk, display=device)

    def open_app(self, on_chunk, app):
        return ScreenCaptureKitCapture(on_chunk, app=app)
