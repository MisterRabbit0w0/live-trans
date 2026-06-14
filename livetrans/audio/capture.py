"""WASAPI 环回捕获系统音频，输出 16kHz 单声道 float32 块。

任何应用播放的声音（浏览器、直播客户端）都会被默认输出设备的
loopback 设备捕获，无需虚拟声卡。
"""
from __future__ import annotations

import threading
from collections.abc import Callable

import numpy as np
import pyaudiowpatch as pyaudio

TARGET_RATE = 16000


def list_loopback_devices() -> list[dict]:
    """返回所有可用环回设备列表，每项含 index / name / defaultSampleRate。"""
    pa = pyaudio.PyAudio()
    try:
        devices = list(pa.get_loopback_device_info_generator())
    finally:
        pa.terminate()
    return devices


class LoopbackCapture:
    """捕获扬声器环回音频，重采样后回调 on_chunk(float32 mono @16k)。

    device_index=-1 表示自动选默认输出设备对应的环回设备。
    """

    def __init__(
        self,
        on_chunk: Callable[[np.ndarray], None],
        chunk_ms: int = 100,
        device_index: int = -1,
    ):
        self._on_chunk = on_chunk
        self._chunk_ms = chunk_ms
        self._device_index = device_index
        self._pa: pyaudio.PyAudio | None = None
        self._stream = None
        self._lock = threading.Lock()
        self.device_name = ""

    def _find_loopback_device(self, pa: pyaudio.PyAudio) -> dict:
        # 指定了具体设备 index，直接用（需要是 loopback 设备）
        if self._device_index >= 0:
            dev = pa.get_device_info_by_index(self._device_index)
            return dev

        # 自动：找默认输出设备对应的环回
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if speakers.get("isLoopbackDevice"):
            return speakers
        for loopback in pa.get_loopback_device_info_generator():
            if speakers["name"] in loopback["name"]:
                return loopback
        raise RuntimeError("未找到默认输出设备的环回(loopback)设备")

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._pa = pyaudio.PyAudio()
            dev = self._find_loopback_device(self._pa)
            self.device_name = dev["name"]
            src_rate = int(dev["defaultSampleRate"])
            channels = max(1, int(dev["maxInputChannels"]))
            frames = int(src_rate * self._chunk_ms / 1000)

            def callback(in_data, frame_count, time_info, status):
                buf = np.frombuffer(in_data, dtype=np.float32)
                if channels > 1:
                    buf = buf.reshape(-1, channels).mean(axis=1)
                if src_rate != TARGET_RATE:
                    n_out = int(round(len(buf) * TARGET_RATE / src_rate))
                    if n_out > 0:
                        x_old = np.linspace(0.0, 1.0, num=len(buf), endpoint=False)
                        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                        buf = np.interp(x_new, x_old, buf).astype(np.float32)
                    else:
                        buf = np.empty(0, dtype=np.float32)
                if len(buf):
                    self._on_chunk(buf)
                return (None, pyaudio.paContinue)

            self._stream = self._pa.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=src_rate,
                frames_per_buffer=frames,
                input=True,
                input_device_index=dev["index"],
                stream_callback=callback,
            )

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                finally:
                    self._stream = None
            if self._pa is not None:
                self._pa.terminate()
                self._pa = None
