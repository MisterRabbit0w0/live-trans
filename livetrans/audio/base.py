"""Platform-neutral audio capture interface.

Every backend delivers float32 mono chunks at 16 kHz through ``on_chunk`` and
exposes ``start()`` / ``stop()`` / ``device_name``. ``stop()`` returns ``False``
while native resources are still shutting down; the owner retries later.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

TARGET_RATE = 16000

ChunkCallback = Callable[[np.ndarray], None]


class Capture(Protocol):
    device_name: str

    def start(self) -> None: ...

    def stop(self) -> bool | None: ...


@dataclass(frozen=True)
class Device:
    id: str  # opaque to the UI; "" selects the platform default
    label: str


@dataclass(frozen=True)
class AudioApp:
    name: str  # what the user saves as ``audio_process_name``
    label: str
    active: bool = False  # currently producing sound, when the platform knows


class AudioBackend(ABC):
    """Discovery and capture for one operating system's audio stack."""

    name = ""
    default_device_label = "默认输出设备"
    system_hint = ""
    app_hint = ""

    @abstractmethod
    def list_devices(self) -> list[Device]:
        """Output devices whose playback can be captured, excluding the default entry."""

    @abstractmethod
    def list_apps(self) -> list[AudioApp]:
        """Applications that currently own an audio stream, active ones first."""

    @abstractmethod
    def open_system(self, on_chunk: ChunkCallback, device: str = "") -> Capture:
        """Everything played on ``device`` (``""`` = default output)."""

    @abstractmethod
    def open_app(self, on_chunk: ChunkCallback, app: str) -> Capture:
        """Only the sound of the named application."""


class UnsupportedBackend(AudioBackend):
    name = "unsupported"

    def __init__(self, platform: str):
        self._platform = platform

    def list_devices(self):
        return []

    def list_apps(self):
        return []

    def open_system(self, on_chunk, device=""):
        raise RuntimeError(f"当前平台 ({self._platform}) 暂不支持音频捕获")

    def open_app(self, on_chunk, app):
        return self.open_system(on_chunk)


def to_mono_16k(buf: np.ndarray, rate: int, channels: int) -> np.ndarray:
    """Downmix interleaved float32 samples and linearly resample to 16 kHz."""
    if channels > 1:
        frames = len(buf) // channels
        buf = buf[: frames * channels].reshape(-1, channels).mean(axis=1)
    if rate != TARGET_RATE:
        n_out = int(round(len(buf) * TARGET_RATE / rate))
        if n_out <= 0:
            return np.empty(0, dtype=np.float32)
        x_old = np.linspace(0.0, 1.0, num=len(buf), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        buf = np.interp(x_new, x_old, buf)
    return np.asarray(buf, dtype=np.float32)
