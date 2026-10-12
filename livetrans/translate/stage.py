"""Translate utterances on background workers; one instance per translation configuration."""

from __future__ import annotations

import collections
import logging
import queue
import threading
import time
from collections.abc import Callable

from ..config import TranslateConfig
from ..events import Translation, Utterance
from ..languages import target_lang_code
from ..lifecycle import Cleanup
from .base import TranslationHistory
from .openai_compat import OpenAICompatTranslator

log = logging.getLogger(__name__)


def build_translator(cfg: TranslateConfig):
    return OpenAICompatTranslator(cfg.base_url, cfg.api_key, cfg.model, cfg.target_language)


class TranslationStage:
    """``on_translation`` runs on a worker (or the submitting) thread and must not block.

    ``report(stage, status, error=None)`` describes the ``translate`` stage.
    """

    WORKERS = 2
    _DRAIN_TIMEOUT = 5.0
    _STOP_TIMEOUT = 5.0
    _HISTORY_LEN = 3
    _RETRY_DELAY = 0.5

    def __init__(
        self,
        cfg: TranslateConfig,
        on_translation: Callable[[Translation], None],
        report: Callable[..., None],
        *,
        translator_factory=build_translator,
    ):
        self._cfg = cfg
        self._on_translation = on_translation
        self._report = report
        self._factory = translator_factory
        self._target_code = target_lang_code(cfg.target_language)
        self._cancel = threading.Event()
        self._drain = threading.Event()
        self._queue = queue.Queue(maxsize=64)
        self._threads = []
        self._translator = None
        self._cleanup = Cleanup(self._release, "livetrans-translation-cleanup")
        # 最近翻译的 (源语言, 原文, 译文)，用作上下文；写多读多，加锁保护。
        self._history: collections.deque = collections.deque(maxlen=self._HISTORY_LEN)
        self._history_lock = threading.Lock()

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
                target=self._worker,
                name=f"livetrans-translate-{index}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()
        self._report("translate", "ready")

    def submit(self, utterance: Utterance) -> bool:
        """Queue without blocking; False once this stage is stopping."""
        if self._cancel.is_set() or self._drain.is_set():
            return False
        # Whisper's zh code carries no script information. Chinese targets
        # must still pass through translation for simplified/traditional conversion.
        if (
            self._target_code
            and self._target_code != "zh"
            and utterance.language == self._target_code
        ):
            self._remember(utterance.language, utterance.text, utterance.text)
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
        """正常停止：预算内处理完已入队的句子，超时转为中止。"""
        self.request_drain()
        if self.wait_stopped(self._DRAIN_TIMEOUT):
            return True
        log.warning("翻译排空超时，中止剩余在途工作")
        self.request_stop()
        return self.wait_stopped(self._STOP_TIMEOUT)

    def request_drain(self):
        """正常停止：不再接收新句，处理完已收到的句子。"""
        self._drain.set()
        self._cleanup.request()

    def request_stop(self):
        """中止路径：立即丢弃一切仍在途的工作。"""
        self._drain.set()
        self._cancel.set()
        self._cleanup.request()

    def wait_stopped(self, timeout):
        return self._cleanup.wait(timeout)

    def _history_snapshot(self) -> TranslationHistory:
        with self._history_lock:
            return list(self._history)

    def _remember(self, source_language: str, source_text: str, text: str) -> None:
        with self._history_lock:
            self._history.append((source_language, source_text, text))

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
            if self._drain.is_set() and self._queue.empty():
                return
            try:
                utterance = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if self._cancel.is_set():
                break
            history = self._history_snapshot()
            text = None
            for attempt in range(2):
                try:
                    text = self._translator.translate(
                        utterance.text,
                        source_language=utterance.language,
                        history=history,
                    )
                    break
                except Exception as error:
                    if attempt == 0 and not self._cancel.is_set():
                        # 瞬时网络抖动常见，快速重试一次；仍失败则丢弃本句。
                        time.sleep(self._RETRY_DELAY)
                        continue
                    self._report("translate", "error", type(error).__name__)
            if text is None:
                continue
            self._remember(utterance.language, utterance.text, text)
            self._report("translate", "ready")
            self._on_translation(Translation(utterance.seq, text))
