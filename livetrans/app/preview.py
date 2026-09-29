"""Simulated session for ``--preview``; never touches audio, models or network.

``PreviewPipeline`` is a drop-in session factory with the same signature as
``Session``: ``factory(cfg, emit, cancel, **context)``. ``PreviewBackend``
replaces real device/app discovery while previewing.
"""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass

SAMPLES = (
    ("en", "The next session starts in five minutes.", "下一场将在五分钟后开始。"),
    ("ja", "次の議題に移りましょう。", "让我们进入下一个议题。"),
    ("en", "Sales grew twelve percent year over year.", "销售额同比增长了百分之十二。"),
    ("ja", "この機能は来週リリース予定です。", "该功能预计下周发布。"),
)

INTERVAL_S = 2.5


@dataclass(frozen=True)
class _Device:
    id: str
    label: str


@dataclass(frozen=True)
class _App:
    name: str
    label: str
    active: bool = False


class PreviewBackend:
    """Discovery stand-in so ``--preview`` never queries real audio devices."""

    name = "preview"
    default_device_label = "默认输出设备（模拟数据）"
    system_hint = "预览模式不采集声音，以下为模拟数据。"
    app_hint = "预览模式不采集声音，以下为模拟数据。"

    def list_devices(self):
        return [_Device("preview-device", "预览扬声器（模拟数据）")]

    def list_apps(self):
        return [_App("preview.exe", "预览进程", True)]


class PreviewPipeline:
    def __init__(self, cfg, emit, cancel, **context):
        self._emit, self._cancel = emit, cancel
        self._ids = context.get("ids") or itertools.count(1)
        self._paused = threading.Event()
        self._index = 0

    def start(self, paused=False):
        if paused:
            self._paused.set()
        self._emit({"kind": "started", "device": "预览音频（模拟数据）", "paused": paused})
        threading.Thread(target=self._produce, name="livetrans-preview", daemon=True).start()

    def _produce(self):
        while not self._cancel.wait(INTERVAL_S):
            if self._paused.is_set():
                continue
            language, original, translation = SAMPLES[self._index % len(SAMPLES)]
            self._index += 1
            entry = next(self._ids)
            self._emit({"kind": "entry", "id": entry, "original": original,
                        "language": language})
            self._emit({"kind": "translation", "id": entry, "translation": translation})

    def stop(self):
        self._cancel.set()

    def set_paused(self, paused):
        if paused:
            self._paused.set()
        else:
            self._paused.clear()

    def reconfigure(self, cfg):
        pass
