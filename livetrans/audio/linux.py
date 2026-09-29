"""Linux: PulseAudio / PipeWire (pipewire-pulse) through ``pactl`` and ``parec``.

System sound records a sink's monitor source. An application is captured
with ``parec --monitor-stream``, which taps one playback stream without
rerouting it, so the user keeps hearing it. Streams come and go as players
pause or switch tracks; the capture follows the application by name.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass

import numpy as np

from .base import TARGET_RATE, AudioApp, AudioBackend, ChunkCallback, Device

log = logging.getLogger(__name__)

CHUNK_BYTES = TARGET_RATE // 10 * 4  # 100 ms of float32 mono
RESCAN_S = 1.0


def _command(name):
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(
            f"未找到 {name}，请安装 pulseaudio-utils（PipeWire 需启用 pipewire-pulse）")
    return path


def _pactl(*args) -> str:
    # pactl localizes its text output; the parser relies on the C locale.
    env = dict(os.environ, LC_ALL="C", LANG="C")
    out = subprocess.run([_command("pactl"), *args], capture_output=True, text=True,
                         timeout=5, env=env, check=True)
    return out.stdout


_BLOCK = re.compile(r"^(?:Sink|Sink Input) #(\d+)\s*$", re.M)
_FIELD = re.compile(r"^\s+([A-Za-z ]+):\s*(.*)$")
_PROPERTY = re.compile(r'^\s+([\w.]+) = "(.*)"$')


def parse_blocks(text: str) -> list[dict]:
    """Parse ``pactl list sinks|sink-inputs`` into dicts with ``index``, fields and properties."""
    blocks = []
    starts = list(_BLOCK.finditer(text))
    for n, match in enumerate(starts):
        end = starts[n + 1].start() if n + 1 < len(starts) else len(text)
        block = {"index": int(match.group(1)), "properties": {}}
        for line in text[match.end():end].splitlines():
            prop = _PROPERTY.match(line)
            if prop:
                block["properties"][prop.group(1)] = prop.group(2)
                continue
            field = _FIELD.match(line)
            if field:
                block.setdefault(field.group(1).strip().lower(), field.group(2).strip())
        blocks.append(block)
    return blocks


@dataclass(frozen=True)
class _Stream:
    index: int
    names: frozenset[str]
    label: str
    active: bool


def _normalize(name: str) -> str:
    name = name.strip().lower()
    return name[:-4] if name.endswith(".exe") else name


def _streams() -> list[_Stream]:
    streams = []
    for block in parse_blocks(_pactl("list", "sink-inputs")):
        props = block["properties"]
        names = {props.get("application.process.binary", ""),
                 props.get("application.name", ""), props.get("application.id", "")}
        names = frozenset(_normalize(n) for n in names if n)
        if not names:
            continue
        label = props.get("application.process.binary") or props.get("application.name")
        streams.append(_Stream(block["index"], names, label,
                               block.get("corked", "no") == "no"))
    return streams


class ParecCapture:
    """Pipe raw float32 mono 16 kHz from ``parec``; re-resolves app streams on the fly."""

    def __init__(self, on_chunk: ChunkCallback, *, device: str = "", app: str = ""):
        self._on_chunk = on_chunk
        self._device = device
        self._app = _normalize(app)
        self.device_name = f"应用 {app} [PulseAudio]" if app else (
            f"{device} [PulseAudio]" if device else "默认输出设备 [PulseAudio]")
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        _command("parec")
        if self._app and self._pick_stream() is None:
            # Waiting is fine later, but the first start must match something real.
            raise RuntimeError(f"未找到正在播放的应用 {self._app}，请先让它发出声音")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="livetrans-parec", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> bool:
        self._stop.set()
        self._terminate()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                return False
            self._thread = None
        return True

    def _pick_stream(self) -> int | None:
        matches = [s for s in _streams() if self._app in s.names]
        matches.sort(key=lambda s: (not s.active, -s.index))  # playing, then newest
        return matches[0].index if matches else None

    def _args(self, stream: int | None):
        args = [_command("parec"), "--raw", "--format=float32le", f"--rate={TARGET_RATE}",
                "--channels=1", "--latency-msec=50", "--client-name=LiveTrans"]
        if stream is not None:
            args.append(f"--monitor-stream={stream}")
        else:
            monitor = f"{self._device}.monitor" if self._device else "@DEFAULT_MONITOR@"
            args.append(f"--device={monitor}")
        return args

    def _run(self):
        while not self._stop.is_set():
            stream = None
            if self._app:
                try:
                    stream = self._pick_stream()
                except (OSError, subprocess.SubprocessError, RuntimeError):
                    log.warning("无法列出播放流", exc_info=True)
                if stream is None:
                    self._stop.wait(RESCAN_S)
                    continue
            self._pump(stream)
            self._stop.wait(0.2)  # parec exited: the stream ended or the server restarted

    def _pump(self, stream):
        try:
            process = subprocess.Popen(self._args(stream), stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        except OSError:
            log.warning("parec 启动失败", exc_info=True)
            self._stop.wait(RESCAN_S)
            return
        with self._lock:
            self._process = process
        if self._stop.is_set():
            self._terminate()
        watcher = None
        if stream is not None:
            watcher = threading.Thread(target=self._watch, args=(stream,), daemon=True,
                                       name="livetrans-parec-watch")
            watcher.start()
        pending = b""
        while True:
            data = process.stdout.read1(CHUNK_BYTES)
            if not data:
                break
            pending += data
            usable = len(pending) - len(pending) % 4
            if usable and not self._stop.is_set():
                self._on_chunk(np.frombuffer(pending[:usable], dtype=np.float32).copy())
            pending = pending[usable:]
        process.wait()
        with self._lock:
            self._process = None
        if watcher is not None:
            watcher.join()

    def _watch(self, stream):
        """Switch when a newer stream of the app starts playing; parec cannot see that."""
        while not self._stop.wait(RESCAN_S):
            with self._lock:
                if self._process is None or self._process.poll() is not None:
                    return
            try:
                best = self._pick_stream()
            except (OSError, subprocess.SubprocessError, RuntimeError):
                continue
            if best != stream:
                self._terminate()
                return

    def _terminate(self):
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()


class LinuxBackend(AudioBackend):
    name = "linux"
    system_hint = "录制该输出设备的监听源（PulseAudio / PipeWire），不需要虚拟声卡。"
    app_hint = "先让软件播放声音再刷新，也可直接输入 firefox 等程序名。"

    def list_devices(self):
        devices = []
        for block in parse_blocks(_pactl("list", "sinks")):
            name = block.get("name")
            if name:
                devices.append(Device(name, block.get("description") or name))
        return devices

    def list_apps(self):
        apps, seen = [], set()
        for stream in sorted(_streams(), key=lambda s: not s.active):
            key = _normalize(stream.label)
            if key not in seen:
                seen.add(key)
                apps.append(AudioApp(stream.label, stream.label, stream.active))
        return apps

    def open_system(self, on_chunk, device=""):
        return ParecCapture(on_chunk, device=device)

    def open_app(self, on_chunk, app):
        return ParecCapture(on_chunk, app=app)
