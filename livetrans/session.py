"""One session: a transcriber whose speech fans out to translation and recording.

Lifecycle methods run on the runtime coordinator, never on the GUI thread.
Stages exchange ``Utterance``/``Translation`` objects; only this class
speaks the structured dict events the UI consumes.
"""
from __future__ import annotations

import itertools
import logging
import threading
import time
from collections.abc import Callable, Iterator

from .asr.base import AsrResult
from .audio.vad import VadSegmenter
from .config import AppConfig
from .events import Translation, Utterance
from .record.transcript import Recorder
from .transcriber import Transcriber, build_asr, build_capture
from .translate.stage import TranslationStage, build_translator

log = logging.getLogger(__name__)


class Session:
    _STOP_TIMEOUT = 5.0

    def __init__(
        self, cfg: AppConfig, emit: Callable[[dict], None],
        cancel: threading.Event | None = None, *, ids: Iterator[int] | None = None,
        recorder: Recorder | None = None,
        asr_factory=build_asr, translator_factory=build_translator,
        capture_factory=build_capture, vad_factory=VadSegmenter,
    ):
        self._cfg = cfg
        self._emit_callback = emit
        self._cancel = cancel if cancel is not None else threading.Event()
        # Numbering and the recorder outlive this session across engine restarts.
        self._ids = ids if ids is not None else itertools.count(1)
        self._recorder = recorder
        self._translator_factory = translator_factory
        self._transcriber = Transcriber(
            cfg, self._on_speech, self._report, self._cancel,
            asr_factory=asr_factory, capture_factory=capture_factory, vad_factory=vad_factory,
        )
        self._translation: TranslationStage | None = None
        self._retired: list[TranslationStage] = []

    def _emit(self, kind, **data):
        if not self._cancel.is_set():
            self._emit_callback(dict(kind=kind, **data))

    def _report(self, stage, status, error=None):
        if error is None:
            self._emit("stage", stage=stage, status=status)
            return
        # Exception text can contain endpoint credentials; expose only its type.
        log.warning("%s 失败 (%s)", stage, error)
        self._emit("stage", stage=stage, status=status, error=error)

    def start(self, paused=False):
        try:
            if self._cancel.is_set():
                return
            self._configure_record(self._cfg)
            # Translation exists before the first utterance can arrive.
            self._translation = self._start_translation(self._cfg)
            self._transcriber.start(paused)
            if self._cancel.is_set():
                return
            self._record("mark", "started", device=self._transcriber.device_name,
                         model=self._transcriber.model_name, paused=paused)
            self._emit("started", device=self._transcriber.device_name,
                       model=self._transcriber.model_name, paused=paused)
        except Exception:
            self._cancel.set()
            raise
        finally:
            if self._cancel.is_set():
                self.stop()

    def stop(self):
        """Bound the caller's wait; only report success after every stage stops."""
        self._cancel.set()
        stages = [self._transcriber, *self._retired]
        if self._translation is not None:
            stages.append(self._translation)
        for stage in stages:
            stage.request_stop()
        deadline = time.monotonic() + self._STOP_TIMEOUT
        return all([stage.wait_stopped(max(0.0, deadline - time.monotonic()))
                    for stage in stages])

    def reconfigure(self, cfg: AppConfig):
        """Apply downstream changes in place; recognition keeps running."""
        if self._cancel.is_set():
            return
        previous, self._cfg = self._cfg, cfg
        if cfg.translate != previous.translate:
            self._replace_translation(cfg)
        if cfg.record != previous.record:
            self._configure_record(cfg)

    def _replace_translation(self, cfg: AppConfig):
        old = self._translation
        if not getattr(cfg.translate, "enabled", True):
            new = None
            self._report("translate", "off")
        else:
            try:
                new = self._start_translation(cfg)
            except Exception:
                # Already reported as a translation error; text keeps arriving untranslated.
                new = None
        self._translation = new
        if old is not None:
            old.request_stop()
            self._retired = [stage for stage in self._retired if not stage.stopped] + [old]
            if new is not None:
                for utterance in old.drain():
                    new.submit(utterance)
    def set_paused(self, paused):
        if paused != self._transcriber.paused:
            self._record("mark", "paused" if paused else "resumed")
        self._transcriber.set_paused(paused)

    @property
    def paused(self):
        return self._transcriber.paused

    def _start_translation(self, cfg: AppConfig) -> TranslationStage | None:
        if not getattr(cfg.translate, "enabled", True):
            self._report("translate", "off")
            return None
        stage = TranslationStage(cfg.translate, self._on_translation, self._report,
                                 translator_factory=self._translator_factory)
        stage.start()
        return stage
    def _configure_record(self, cfg: AppConfig):
        recorder = self._recorder
        if recorder is None:
            return
        if not cfg.record.enabled:
            recorder.close()
            self._report("record", "off")
            return
        a = cfg.asr
        meta = dict(
            source=cfg.audio_process_name if cfg.audio_source_mode == "process" else "system",
            asr=a.cloud_model if a.backend == "cloud" else a.model, source_language=a.language,
            target_language=cfg.translate.target_language, translate_model=cfg.translate.model,
        )
        try:
            recorder.open(meta)
        except OSError as error:
            # Recording is optional: report it and keep translating.
            self._report("record", "error", type(error).__name__)
        else:
            self._report("record", "ready")

    def _record(self, method, *args, **data):
        recorder = self._recorder
        if recorder is None or not recorder.active or self._cancel.is_set():
            return
        try:
            getattr(recorder, method)(*args, **data)
        except OSError as error:
            self._report("record", "error", type(error).__name__)

    def _on_speech(self, result: AsrResult, started_at: float, ended_at: float):
        utterance = Utterance(next(self._ids), result.text, result.language, started_at, ended_at)
        self._record("utterance", utterance)
        self._emit("entry", id=utterance.seq, original=utterance.text,
                   language=utterance.language)
        stage = self._translation
        if stage is not None and not stage.submit(utterance):
            # Replaced between the read and the submit; its successor takes it.
            stage = self._translation
            if stage is not None:
                stage.submit(utterance)

    def _on_translation(self, translation: Translation):
        self._record("translation", translation)
        self._emit("translation", id=translation.seq, translation=translation.text)
