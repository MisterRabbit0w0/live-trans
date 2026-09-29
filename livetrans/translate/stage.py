"""Translate utterances on background workers; one instance per translation configuration."""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

from ..config import TranslateConfig
from ..events import Translation, Utterance
from ..languages import target_lang_code
from ..lifecycle import Cleanup
from .openai_compat import OpenAICompatTranslator

log = logging.getLogger(__name__)


def build_translator(cfg: TranslateConfig):
    return OpenAICompatTranslator(cfg.base_url, cfg.api_key, cfg.model, cfg.target_language)


class TranslationStage:
    """``on_translation`` runs on a worker (or the submitting) thread and must not block.

    ``report(stage, status, error=None)`` describes the ``translate`` stage.
    """

    WORKERS = 2
    _STOP_TIMEOUT = 5.0

    def __init__(
        self, cfg: TranslateConfig, on_translation: Callable[[Translation], None],
        report: Callable[..., None], *, translator_factory=build_translator,
    ):
        self._cfg = cfg
        self._on_translation = on_translation
        self._report = report
        self._factory = translator_factory
        self._target_code = target_lang_code(cfg.target_language)
        self._cancel = threading.Event()
        self._queue = queue.Queue(maxsize=64)
        self._threads = []
        self._translator = None
        self._cleanup = Cleanup(self._release, "livetrans-translation-cleanup")

    def start(self):
        self._cleanup.arm()
        self._report("translate", "loading")
        try:
            self._translator = self._factory(self._cfg)
        except Exception as error:
            self._report("translate", "error", type(error).__name__)
            raise
        for index in range(self.WORKERS):
            thread = threading.Thread(
                target=self._worker, name=f"livetrans-translate-{index}", daemon=True,
            )
            self._threads.append(thread)
            thread.start()
        self._report("translate", "ready")

    def submit(self, utterance: Utterance) -> bool:
        """Queue without blocking; False once this stage is stopping."""
        if self._cancel.is_set():
            return False
        # Whisper's zh code carries no script information. Chinese targets
        # must still pass through translation for simplified/traditional conversion.
        if self._target_code and self._target_code != "zh" \
                and utterance.language == self._target_code:
            self._on_translation(Translation(utterance.seq, utterance.text))
            return True
        try:
            self._queue.put_nowait(utterance)
        except queue.Full:
            log.warning("翻译处理不及，丢弃一句")
        return True

    def drain(self) -> list[Utterance]:
        """Take the pending utterances of a stopping stage for its replacement."""
        pending = []
        while True:
            try:
                pending.append(self._queue.get_nowait())
            except queue.Empty:
                return pending

    def stop(self):
        """Bound the caller's wait; only report success after the client is closed."""
        self.request_stop()
        return self.wait_stopped(self._STOP_TIMEOUT)

    def request_stop(self):
        self._cancel.set()
        self._cleanup.request()

    def wait_stopped(self, timeout):
        return self._cleanup.wait(timeout)

    @property
    def stopped(self):
        return self._cleanup.done.is_set()

    def _release(self):
        # A request in flight finishes before its client closes.
        for thread in self._threads:
            thread.join()
        self._threads.clear()
        if self._translator is not None:
            self._translator.close()
            self._translator = None

    def _worker(self):
        while not self._cancel.is_set():
            try:
                utterance = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if self._cancel.is_set():
                break
            try:
                text = self._translator.translate(
                    utterance.text, source_language=utterance.language,
                )
            except Exception as error:
                self._report("translate", "error", type(error).__name__)
                continue
            self._report("translate", "ready")
            self._on_translation(Translation(utterance.seq, text))
