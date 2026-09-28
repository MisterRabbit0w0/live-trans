"""Audio → VAD → speech recognition, independent of what consumes the text.

Lifecycle methods run on the runtime coordinator, never on the GUI thread.
Recognized speech leaves only through ``on_speech``; translation and
recording subscribe in the session, never here.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

import numpy as np

from .asr.base import AsrEngine, AsrResult
from .asr.whisper_cloud import CloudWhisper
from .asr.whisper_local import LocalWhisper
from .audio.capture import LoopbackCapture
from .audio.vad import SAMPLE_RATE, VadSegmenter
from .config import AppConfig
from .lifecycle import Cleanup

log = logging.getLogger(__name__)


def build_asr(cfg: AppConfig) -> AsrEngine:
    if cfg.asr.backend == "cloud":
        return CloudWhisper(cfg.asr.cloud_base_url, cfg.asr.cloud_api_key, cfg.asr.cloud_model)
    return LocalWhisper(cfg.asr.model, cfg.asr.device)


def build_capture(cfg, callback):
    if cfg.audio_source_mode == "process":
        import comtypes

        from .audio.process_capture import ProcessLoopbackCapture, find_pid_by_name

        comtypes.CoInitialize()
        try:
            pid = find_pid_by_name(cfg.audio_process_name)
        finally:
            comtypes.CoUninitialize()
        return ProcessLoopbackCapture(callback, pid=pid, process_name=cfg.audio_process_name)
    return LoopbackCapture(callback, device_index=cfg.audio_device_index)


class Transcriber:
    """Reads only the audio, recognition and VAD settings of ``cfg``.

    ``on_speech(result, started_at, ended_at)`` runs on the recognition thread
    and must not block. ``report(stage, status, error=None)`` describes the
    ``audio`` and ``asr`` stages. After a failed ``start`` the owner calls ``stop``.
    """

    _STOP_TIMEOUT = 5.0
    _CAPTURE_RETRY_DELAY = 0.1

    def __init__(
        self, cfg: AppConfig, on_speech: Callable[[AsrResult, float, float], None],
        report: Callable[..., None], cancel: threading.Event | None = None, *,
        asr_factory=build_asr, capture_factory=build_capture, vad_factory=VadSegmenter,
    ):
        self._cfg = cfg
        self._on_speech = on_speech
        self._report = report
        self._cancel = cancel if cancel is not None else threading.Event()
        self._paused = False
        self._audio_q = queue.Queue(maxsize=256)
        self._asr_q = queue.Queue(maxsize=16)
        self._threads = []
        self._capture = None
        self._engine = None
        self._vad = None
        self._asr_factory = asr_factory
        self._capture_factory = capture_factory
        self._vad_factory = vad_factory
        self._cleanup = Cleanup(self._release, "livetrans-transcriber-cleanup")

    @property
    def device_name(self):
        return self._capture.device_name if self._capture is not None else ""

    @property
    def model_name(self):
        a = self._cfg.asr
        return getattr(self._engine, "model_name",
                       a.cloud_model if a.backend == "cloud" else a.model)

    def start(self, paused=False):
        self._cleanup.arm()
        self._paused = paused
        stage = "asr"
        try:
            self._report(stage, "loading")
            if self._cancel.is_set():
                return
            self._engine = self._asr_factory(self._cfg)
            self._report(stage, "ready")
            if self._cancel.is_set():
                return
            stage = "audio"
            self._report(stage, "loading")
            self._vad = self._vad_factory(
                on_segment=self._on_segment, silence_ms=self._cfg.vad_silence_ms,
                max_segment_s=self._cfg.vad_max_segment_s,
                min_speech_ms=self._cfg.vad_min_speech_ms,
            )
            self._capture = self._capture_factory(self._cfg, self._on_audio_chunk)
            if self._cancel.is_set():
                return
            for target, name in ((self._vad_worker, "vad"), (self._asr_worker, "asr")):
                thread = threading.Thread(target=target, name=f"livetrans-{name}", daemon=True)
                self._threads.append(thread)
                thread.start()
            self._capture.start()
            self._report(stage, "ready")
        except Exception as error:
            self._report(stage, "error", type(error).__name__)
            raise

    def stop(self):
        """Bound the caller's wait; only report success after all resources stop."""
        self.request_stop()
        return self.wait_stopped(self._STOP_TIMEOUT)

    def request_stop(self):
        self._cancel.set()
        self._cleanup.request()

    def wait_stopped(self, timeout):
        return self._cleanup.wait(timeout)

    def _release(self):
        # Keep native capture and clients reachable until they confirm completion.
        while self._capture is not None:
            if self._capture.stop() is False:
                time.sleep(self._CAPTURE_RETRY_DELAY)
                continue
            self._capture = None
        for thread in self._threads:
            thread.join()
        self._threads.clear()
        if self._engine is not None:
            self._engine.close()
            self._engine = None

    def set_paused(self, paused):
        self._paused = paused

    @property
    def paused(self):
        return self._paused

    def _on_audio_chunk(self, chunk: np.ndarray):
        if not self._paused and not self._cancel.is_set():
            self._put(self._audio_q, chunk)

    def _on_segment(self, audio):
        # The VAD cuts a segment right after it ends; the queue delay before is small.
        ended_at = time.time()
        self._put(self._asr_q, (audio, ended_at - len(audio) / SAMPLE_RATE, ended_at))

    def _put(self, target, value):
        if not self._cancel.is_set():
            try:
                target.put_nowait(value)
            except queue.Full:
                log.warning("处理不及音频产生速度，丢弃一段")

    def _items(self, source):
        while not self._cancel.is_set():
            try:
                value = source.get(timeout=0.1)
            except queue.Empty:
                continue
            if not self._cancel.is_set():
                yield value

    def _vad_worker(self):
        for chunk in self._items(self._audio_q):
            try:
                self._vad.feed(chunk)
            except Exception as error:
                self._report("audio", "error", type(error).__name__)
            else:
                self._report("audio", "ready")

    def _asr_worker(self):
        language = None if self._cfg.asr.language == "auto" else self._cfg.asr.language
        for audio, started_at, ended_at in self._items(self._asr_q):
            try:
                result = self._engine.transcribe(audio, language=language)
            except Exception as error:
                self._report("asr", "error", type(error).__name__)
                continue
            self._report("asr", "ready")
            if result.text:
                self._on_speech(result, started_at, ended_at)
