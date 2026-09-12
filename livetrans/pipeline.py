"""Audio → VAD → recognition → translation, independent of any window.

Lifecycle methods run on the runtime coordinator, never on the GUI thread.
Each session owns its engines, queues and cancellation event.
"""
from __future__ import annotations

import itertools
import logging
import queue
import threading
import time
from collections.abc import Callable

import numpy as np

from .asr.base import AsrEngine
from .asr.whisper_cloud import CloudWhisper
from .asr.whisper_local import LocalWhisper
from .audio.capture import LoopbackCapture
from .audio.vad import VadSegmenter
from .config import AppConfig
from .translate.openai_compat import OpenAICompatTranslator

log = logging.getLogger(__name__)
_TARGET_LANG_CODES = {
    "中": "zh", "英": "en", "日": "ja", "韩": "ko",
    "俄": "ru", "法": "fr", "德": "de", "西": "es",
}


def target_lang_code(target_language: str) -> str:
    t = target_language.strip()
    if not t:
        return ""
    if t.lower().startswith("eng"):
        return "en"
    if t.lower().startswith("chin"):
        return "zh"
    return _TARGET_LANG_CODES.get(t[0], "")


def build_asr(cfg: AppConfig) -> AsrEngine:
    if cfg.asr.backend == "cloud":
        return CloudWhisper(cfg.asr.cloud_base_url, cfg.asr.cloud_api_key, cfg.asr.cloud_model)
    return LocalWhisper(cfg.asr.model, cfg.asr.device)


def build_translator(cfg: AppConfig):
    t = cfg.translate
    return OpenAICompatTranslator(t.base_url, t.api_key, t.model, t.target_language)


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


class Pipeline:
    _CAPTURE_STOP_TIMEOUT = 3.0
    _WORKER_STOP_TIMEOUT = 5.0

    def __init__(
        self, cfg: AppConfig, emit: Callable[[dict], None],
        cancel: threading.Event | None = None, *,
        asr_factory=build_asr, translator_factory=build_translator,
        capture_factory=build_capture, vad_factory=VadSegmenter,
    ):
        self._cfg = cfg
        self._emit_callback = emit
        self._cancel = cancel if cancel is not None else threading.Event()
        self._paused = False
        self._ids = itertools.count(1)
        self._audio_q = queue.Queue(maxsize=256)
        self._asr_q = queue.Queue(maxsize=16)
        self._trans_q = queue.Queue(maxsize=64)
        self._threads = []
        self._capture = None
        self._engine = None
        self._translator = None
        self._vad = None
        self._asr_factory = asr_factory
        self._translator_factory = translator_factory
        self._capture_factory = capture_factory
        self._vad_factory = vad_factory
        self._stop_lock = threading.Lock()
        self._cleanup_pending = False

    def _emit(self, kind, **data):
        if not self._cancel.is_set():
            self._emit_callback(dict(kind=kind, **data))

    def start(self, paused=False):
        self._paused = paused
        stage = "asr"
        try:
            self._emit("stage", stage="asr", status="loading")
            if self._cancel.is_set():
                return
            self._engine = self._asr_factory(self._cfg)
            self._emit("stage", stage="asr", status="ready")
            if self._cancel.is_set():
                return
            stage = "translate"
            self._emit("stage", stage=stage, status="loading")
            self._translator = self._translator_factory(self._cfg)
            self._emit("stage", stage=stage, status="ready")
            stage = "audio"
            self._emit("stage", stage=stage, status="loading")
            self._vad = self._vad_factory(
                on_segment=self._on_segment, silence_ms=self._cfg.vad_silence_ms,
                max_segment_s=self._cfg.vad_max_segment_s,
                min_speech_ms=self._cfg.vad_min_speech_ms,
            )
            self._capture = self._capture_factory(self._cfg, self._on_audio_chunk)
            if self._cancel.is_set():
                return
            for target, name in (
                (self._vad_worker, "vad"), (self._asr_worker, "asr"),
                (self._translate_worker, "translate-0"),
                (self._translate_worker, "translate-1"),
            ):
                thread = threading.Thread(target=target, name=f"livetrans-{name}", daemon=True)
                self._threads.append(thread)
                thread.start()
            self._capture.start()
            self._emit("stage", stage="audio", status="ready")
            model = getattr(self._engine, "model_name", self._cfg.asr.cloud_model
                            if self._cfg.asr.backend == "cloud" else self._cfg.asr.model)
            self._emit("started", device=self._capture.device_name, model=model, paused=paused)
        except Exception as error:
            self._error(stage, error)
            self.stop()
            raise
        finally:
            if self._cancel.is_set():
                self.stop()

    def stop(self):
        with self._stop_lock:
            if self._cleanup_pending:
                return
            self._cancel.set()
            capture = self._capture
            self._capture = None
            threads = self._threads
            self._threads = []

            if capture is not None:
                self._stop_capture(capture)

            deadline = time.monotonic() + self._WORKER_STOP_TIMEOUT
            alive = []
            for thread in threads:
                thread.join(timeout=max(0.0, deadline - time.monotonic()))
                if thread.is_alive():
                    alive.append(thread)
            if alive:
                # Never close a shared client while a worker may still be using it.
                # A daemon cleanup watcher closes resources once the abandoned
                # session has observed cancellation and returned.
                self._cleanup_pending = True
                log.warning("%d 个管线线程未能在 %.1f 秒内停止，将后台清理",
                            len(alive), self._WORKER_STOP_TIMEOUT)
                threading.Thread(
                    target=self._finish_deferred_cleanup,
                    args=(alive,),
                    name="livetrans-stop-cleanup",
                    daemon=True,
                ).start()
                return
            self._close_resources()

    def _stop_capture(self, capture):
        """Stop capture without letting a stalled native API block the coordinator."""
        finished = threading.Event()

        def stop_capture():
            try:
                capture.stop()
            except Exception as error:
                log.warning("音频捕获停止失败 (%s)", type(error).__name__)
            finally:
                finished.set()

        threading.Thread(target=stop_capture, name="livetrans-capture-stop", daemon=True).start()
        if not finished.wait(self._CAPTURE_STOP_TIMEOUT):
            log.warning("音频捕获未能在 %.1f 秒内停止，将放弃等待", self._CAPTURE_STOP_TIMEOUT)

    def _finish_deferred_cleanup(self, threads):
        for thread in threads:
            thread.join()
        self._close_resources()
        with self._stop_lock:
            self._cleanup_pending = False

    def _close_resources(self):
        # This is called only after workers are done, so shared clients are safe to close.
        translator, self._translator = self._translator, None
        engine, self._engine = self._engine, None
        try:
            if translator is not None:
                translator.close()
        except Exception as error:
            log.warning("翻译客户端关闭失败 (%s)", type(error).__name__)
        finally:
            try:
                if engine is not None:
                    engine.close()
            except Exception as error:
                log.warning("识别引擎关闭失败 (%s)", type(error).__name__)

    def set_paused(self, paused):
        self._paused = paused

    @property
    def paused(self):
        return self._paused

    def _on_audio_chunk(self, chunk: np.ndarray):
        if not self._paused and not self._cancel.is_set():
            self._put(self._audio_q, chunk)

    def _on_segment(self, audio):
        self._put(self._asr_q, audio)

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

    def _error(self, stage, exception):
        # Exception text can contain endpoint credentials; expose only its type.
        log.warning("%s 失败 (%s)", stage, type(exception).__name__)
        self._emit("stage", stage=stage, status="error", error=type(exception).__name__)

    def _vad_worker(self):
        for chunk in self._items(self._audio_q):
            try:
                self._vad.feed(chunk)
            except Exception as error:
                self._error("audio", error)
            else:
                self._emit("stage", stage="audio", status="ready")

    def _asr_worker(self):
        target_code = target_lang_code(self._cfg.translate.target_language)
        language = None if self._cfg.asr.language == "auto" else self._cfg.asr.language
        for audio in self._items(self._asr_q):
            try:
                result = self._engine.transcribe(audio, language=language)
            except Exception as error:
                self._error("asr", error)
                continue
            self._emit("stage", stage="asr", status="ready")
            if not result.text:
                continue
            entry_id = next(self._ids)
            self._emit("entry", id=entry_id, original=result.text, language=result.language)
            if target_code and result.language == target_code:
                self._emit("translation", id=entry_id, translation=result.text)
            else:
                self._put(self._trans_q, (entry_id, result.text, result.language))

    def _translate_worker(self):
        for entry_id, text, language in self._items(self._trans_q):
            try:
                translation = self._translator.translate(text, source_language=language)
            except Exception as error:
                self._error("translate", error)
                continue
            self._emit("stage", stage="translate", status="ready")
            self._emit("translation", id=entry_id, translation=translation)
