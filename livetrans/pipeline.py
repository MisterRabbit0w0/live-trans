"""管线编排：capture → vad → asr → translate → ui。

各环节独立线程，队列衔接；翻译不阻塞识别（原文先上屏，译文后补）。
"""
from __future__ import annotations

import itertools
import logging
import queue
import threading

import numpy as np

from .asr.base import AsrEngine
from .asr.whisper_cloud import CloudWhisper
from .asr.whisper_local import LocalWhisper
from .audio.capture import LoopbackCapture
from .audio.vad import VadSegmenter
from .config import AppConfig
from .translate.base import Translator
from .translate.openai_compat import OpenAICompatTranslator
from .ui.subtitle_window import SubtitleWindow

log = logging.getLogger(__name__)
_SENTINEL = None

# 目标语言文本 → whisper 语言代码（用于源语言==目标语言时跳过翻译）
_TARGET_LANG_CODES = {
    "中": "zh", "英": "en", "日": "ja", "韩": "ko",
    "俄": "ru", "法": "fr", "德": "de", "西": "es",
}


def target_lang_code(target_language: str) -> str:
    t = target_language.strip()
    if not t:
        return ""
    low = t.lower()
    if low.startswith("eng"):
        return "en"
    if low.startswith("chin"):
        return "zh"
    return _TARGET_LANG_CODES.get(t[0], "")


def build_asr(cfg: AppConfig) -> AsrEngine:
    if cfg.asr.backend == "cloud":
        return CloudWhisper(cfg.asr.cloud_base_url, cfg.asr.cloud_api_key, cfg.asr.cloud_model)
    return LocalWhisper(cfg.asr.model, cfg.asr.device)


def build_translator(cfg: AppConfig) -> Translator:
    t = cfg.translate
    return OpenAICompatTranslator(t.base_url, t.api_key, t.model, t.target_language)


class Pipeline:
    def __init__(self, cfg: AppConfig, window: SubtitleWindow):
        self._cfg = cfg
        self._window = window
        self._running = False
        self._paused = False
        self._ids = itertools.count(1)
        self._audio_q: queue.Queue = queue.Queue(maxsize=256)
        self._asr_q: queue.Queue = queue.Queue(maxsize=16)
        self._trans_q: queue.Queue = queue.Queue(maxsize=64)
        self._threads: list[threading.Thread] = []
        self._capture = None  # LoopbackCapture | ProcessLoopbackCapture
        self._translator: Translator | None = None
        self._trans_warned = False

    # ---------- 生命周期 ----------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._paused = False
        # 翻译起 2 个 worker：云端 API 延迟抖动大，并发避免队列积压
        self._translator = build_translator(self._cfg)
        for target, name in (
            (self._vad_worker, "vad"),
            (self._asr_worker, "asr"),
            (self._translate_worker, "translate-0"),
            (self._translate_worker, "translate-1"),
        ):
            t = threading.Thread(target=target, name=f"livetrans-{name}", daemon=True)
            t.start()
            self._threads.append(t)
        if self._cfg.audio_source_mode == "process" and self._cfg.audio_process_name:
            from .audio.process_capture import ProcessLoopbackCapture, find_pid_by_name

            pid = find_pid_by_name(self._cfg.audio_process_name)
            self._capture = ProcessLoopbackCapture(
                self._on_audio_chunk, pid=pid, process_name=self._cfg.audio_process_name
            )
        else:
            self._capture = LoopbackCapture(
                self._on_audio_chunk, device_index=self._cfg.audio_device_index
            )
        self._capture.start()
        log.info("捕获设备: %s", self._capture.device_name)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._capture:
            self._capture.stop()
            self._capture = None
        for q, n in ((self._audio_q, 1), (self._asr_q, 1), (self._trans_q, 2)):
            for _ in range(n):  # 每个 worker 一个哨兵
                try:
                    q.put_nowait(_SENTINEL)
                except queue.Full:
                    pass
        self._threads.clear()
        if self._translator is not None:
            self._translator.close()
            self._translator = None

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._window.status_changed.emit("已暂停" if paused else "")

    @property
    def paused(self) -> bool:
        return self._paused

    # ---------- 各环节 ----------

    def _on_audio_chunk(self, chunk: np.ndarray) -> None:
        if self._paused or not self._running:
            return
        try:
            self._audio_q.put_nowait(chunk)
        except queue.Full:
            pass  # 下游堵塞时丢弃最新音频，避免内存暴涨

    def _vad_worker(self) -> None:
        seg = VadSegmenter(
            on_segment=self._on_segment,
            silence_ms=self._cfg.vad_silence_ms,
            max_segment_s=self._cfg.vad_max_segment_s,
            min_speech_ms=self._cfg.vad_min_speech_ms,
        )
        while self._running:
            chunk = self._audio_q.get()
            if chunk is _SENTINEL:
                break
            seg.feed(chunk)

    def _on_segment(self, audio: np.ndarray) -> None:
        try:
            self._asr_q.put_nowait(audio)
        except queue.Full:
            log.warning("识别不及音频产生速度，丢弃一句")

    def _asr_worker(self) -> None:
        self._window.status_changed.emit("正在加载识别模型…")
        try:
            engine = build_asr(self._cfg)
        except Exception as e:
            log.exception("ASR 初始化失败")
            self._window.status_changed.emit(f"识别模型加载失败: {e}")
            return
        self._window.status_changed.emit("")
        lang_cfg = self._cfg.asr.language
        target_code = target_lang_code(self._cfg.translate.target_language)
        while self._running:
            audio = self._asr_q.get()
            if audio is _SENTINEL:
                break
            try:
                lang = None if lang_cfg == "auto" else lang_cfg
                result = engine.transcribe(audio, language=lang)
            except Exception as e:
                log.exception("识别失败")
                self._window.status_changed.emit(f"识别出错: {e}")
                continue
            if not result.text:
                continue
            entry_id = next(self._ids)
            self._window.entry_added.emit(entry_id, result.text, result.language)
            if target_code and result.language == target_code:
                # 源语言已是目标语言，跳过翻译直接回填（UI 只显示一行）
                self._window.translation_ready.emit(entry_id, result.text)
                continue
            try:
                self._trans_q.put_nowait((entry_id, result.text, result.language))
            except queue.Full:
                pass
        engine.close()

    def _translate_worker(self) -> None:
        translator = self._translator
        while self._running:
            item = self._trans_q.get()
            if item is _SENTINEL or translator is None:
                break
            entry_id, text, lang = item
            try:
                translation = translator.translate(text, source_language=lang)
                if self._trans_warned:
                    self._trans_warned = False
                    self._window.status_changed.emit("")
            except Exception as e:
                log.exception("翻译失败")
                if not self._trans_warned:
                    self._trans_warned = True
                    self._window.status_changed.emit(
                        f"翻译不可用（检查 Ollama 是否启动 / API 配置）: {type(e).__name__}"
                    )
                continue
            self._window.translation_ready.emit(entry_id, translation)
