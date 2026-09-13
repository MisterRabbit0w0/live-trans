"""Offline regression checks for configuration, presentation and lifecycle contracts."""
from __future__ import annotations

import errno
import json
import tempfile
import threading
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import numpy as np
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from livetrans.asr.base import AsrResult
from livetrans.config import AppConfig
from livetrans.instance import SingleInstance
from livetrans.languages import target_lang_code
from livetrans.pipeline import Pipeline
from livetrans.translate.openai_compat import OpenAICompatTranslator
from livetrans.ui.controller import AppController
from livetrans.ui.runtime import RuntimeCoordinator
from livetrans.ui.settings import SettingsStore, engine_config, validate_config
from livetrans.ui.subtitle_model import SubtitleModel

QT_APP = QApplication.instance() or QApplication([])


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QT_APP.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Timed out waiting for lifecycle event")


class FakeRuntime(QObject):
    event = Signal(int, object)

    def __init__(self):
        super().__init__()
        self.generation = 0
        self.starts = []
        self.stops = 0
        self.pauses = []

    def start(self, cfg, paused=False):
        self.generation += 1
        self.starts.append((asdict(cfg), paused))
        return self.generation

    def stop(self):
        self.generation += 1
        self.stops += 1
        return self.generation

    def pause(self, paused):
        self.pauses.append(paused)

    def close(self):
        pass

    def send(self, kind, **kwargs):
        self.event.emit(self.generation, dict(kind=kind, **kwargs))


class ConfigTests(unittest.TestCase):
    def test_legacy_config_and_missing_ui_defaults(self):
        cfg = AppConfig.from_dict({"translate": {"model": "custom", "api_key": "test-only"},
                                   "subtitle": {"font_size": 31}, "vad_max_segment_s": 9})
        self.assertEqual(cfg.translate.model, "custom")
        self.assertEqual(cfg.subtitle.font_size, 31)
        self.assertEqual(cfg.vad_max_segment_s, 9)
        self.assertFalse(cfg.ui.silent_start)
        self.assertFalse(cfg.ui.auto_translate)

    def test_bad_json_shapes_do_not_crash(self):
        for value in ([], None, "bad", {"subtitle": None}, {"ui": {"theme": 99}}):
            self.assertIsInstance(AppConfig.from_dict(value), AppConfig)

    def test_atomic_save_failure_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            cfg = AppConfig()
            cfg.save(path)
            original = path.read_bytes()
            cfg.subtitle.font_size = 33
            with patch("livetrans.config.os.replace", side_effect=PermissionError):
                with self.assertRaises(PermissionError):
                    cfg.save(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(tmp).iterdir()), [path])


class InstanceTests(unittest.TestCase):
    def test_only_one_process_owns_the_instance_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "instance.lock"
            first = SingleInstance(path)
            second = SingleInstance(path)
            self.assertTrue(first.acquire())
            try:
                self.assertFalse(second.acquire())
            finally:
                first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            cfg = AppConfig()
            cfg.ui.silent_start = True
            cfg.ui.theme = "dark"
            cfg.save(path)
            self.assertEqual(asdict(AppConfig.load(path)), asdict(cfg))

    def test_only_active_fields_are_validated(self):
        cfg = AppConfig()
        cfg.asr.cloud_base_url = "invalid"
        cfg.asr.cloud_model = ""
        self.assertFalse(validate_config(cfg))
        cfg.asr.backend = "cloud"
        self.assertIn("asr.cloud_base_url", validate_config(cfg))
        self.assertIn("asr.cloud_model", validate_config(cfg))

    def test_credentials_in_url_and_empty_process_rejected(self):
        cfg = AppConfig()
        cfg.translate.base_url = "https://example-user:example-password@example.invalid/v1"
        cfg.audio_source_mode = "process"
        errors = validate_config(cfg)
        self.assertIn("translate.base_url", errors)
        self.assertIn("audio_process_name", errors)

    def test_inactive_backend_change_is_not_engine_change(self):
        cfg = AppConfig()
        before = engine_config(cfg)
        cfg.asr.cloud_model = "unused"
        cfg.audio_process_name = "unused.exe"
        cfg.ui.theme = "dark"
        cfg.subtitle.font_size = 35
        self.assertEqual(engine_config(cfg), before)
        cfg.asr.model = "base"
        self.assertNotEqual(engine_config(cfg), before)


class DraftTests(unittest.TestCase):
    def test_cross_page_draft_and_discard(self):
        cfg = AppConfig()
        store = SettingsStore(cfg)
        store.setValue("asr.model", "base")
        store.setValue("subtitle.font_size", 30)
        self.assertTrue(store.dirty)
        self.assertEqual(cfg.asr.model, "auto")
        self.assertEqual(store.draft["subtitle"]["font_size"], 30)
        store.discard()
        self.assertFalse(store.dirty)
        self.assertEqual(store.draft, asdict(cfg))

    def test_invalid_values_preserve_draft_and_errors(self):
        store = SettingsStore(AppConfig())
        store.setValue("translate.base_url", "wrong")
        self.assertIsNone(store.candidate())
        self.assertIn("translate.base_url", store.errors)
        self.assertEqual(store.draft["translate"]["base_url"], "wrong")
        store.setValue("translate.base_url", "http://localhost:11434/v1")
        self.assertNotIn("translate.base_url", store.errors)

    def test_integer_setting_rejects_fractional_input(self):
        store = SettingsStore(AppConfig())
        store.setValue("subtitle.font_size", 22.5)
        self.assertEqual(store.draft["subtitle"]["font_size"], 22)
        self.assertTrue(store.dirty)
        self.assertIn("subtitle.font_size", store.errors)
        self.assertIsNone(store.candidate())

    def test_shortcut_updates_font_without_discarding_other_drafts(self):
        store = SettingsStore(AppConfig())
        store.setValue("translate.model", "custom")
        store.sync_font(28)
        store.discard()
        self.assertEqual(store.draft["subtitle"]["font_size"], 28)
        self.assertEqual(store.draft["translate"]["model"], AppConfig().translate.model)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"
        self.runtime = FakeRuntime()
        self.c = AppController(AppConfig(), self.path, self.runtime)

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def running(self):
        self.c.start()
        self.runtime.send("started", device="test", paused=False)

    def test_start_pause_resume_stop(self):
        self.running()
        self.assertEqual(self.c.state, "running")
        self.c.togglePause()
        self.assertEqual(self.c.state, "paused")
        self.c.togglePause()
        self.assertEqual(self.runtime.pauses, [True, False])
        self.c.stop()
        self.assertEqual(self.c.state, "stopping")
        self.runtime.send("stopped")
        self.assertEqual(self.c.state, "idle")
        self.assertFalse(self.c.subtitleVisible)

    def test_style_apply_keeps_session_and_subtitles(self):
        self.running()
        self.runtime.send("entry", id=1, original="hello", language="en")
        self.c.settings.setValue("subtitle.font_size", 30)
        self.c.applySettings()
        self.assertEqual(len(self.runtime.starts), 1)
        self.assertEqual(self.c.subtitles.rowCount(), 1)
        self.assertEqual(self.c.cfg.subtitle.font_size, 30)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["subtitle"]["font_size"], 30)

    def test_engine_apply_restarts_once_and_preserves_pause(self):
        self.running()
        self.c.togglePause()
        self.c.settings.setValue("translate.model", "custom")
        self.c.applySettings()
        self.c.applySettings()
        self.assertEqual(len(self.runtime.starts), 2)
        self.assertTrue(self.runtime.starts[-1][1])
        self.runtime.send("started", paused=True)
        self.assertEqual(self.c.state, "paused")

    def test_late_events_from_previous_session_are_ignored(self):
        self.running()
        generation = self.runtime.generation
        self.c.settings.setValue("asr.model", "base")
        self.c.applySettings()
        self.runtime.event.emit(generation, {"kind": "entry", "id": 1,
                                             "original": "old", "language": "en"})
        self.runtime.event.emit(generation, {"kind": "failed"})
        self.assertEqual(self.c.subtitles.rowCount(), 0)
        self.assertEqual(self.c.state, "starting")

    def test_failed_save_does_not_change_committed_or_restart(self):
        self.running()
        self.c.settings.setValue("asr.model", "base")
        with patch.object(AppConfig, "save", side_effect=PermissionError):
            self.c.applySettings()
        self.assertEqual(self.c.cfg.asr.model, "auto")
        self.assertTrue(self.c.settings.dirty)
        self.assertTrue(self.c.noticeIsError)
        self.assertEqual(len(self.runtime.starts), 1)

    def test_restart_failure_and_retry(self):
        self.running()
        self.c.settings.setValue("asr.model", "base")
        self.c.applySettings()
        self.runtime.send("failed", error="RuntimeError")
        self.assertIn("设置已保存，启动失败", self.c.notice)
        self.assertEqual(self.c.cfg.asr.model, "base")
        self.c.start()
        self.runtime.send("started", paused=False)
        self.assertEqual(self.c.state, "running")
        self.assertEqual(self.c.notice, "")

    def test_save_error_reason_and_selected_runtime_model(self):
        self.c.start()
        self.runtime.send("started", model="small", device="test", paused=False)
        self.assertEqual(self.c.modelLabel, "本地 · small")
        self.assertEqual(self.c.sourceLanguageLabel, "自动检测")
        self.assertEqual(self.c.translationModelLabel, "qwen2.5:7b-instruct")
        self.assertEqual(self.c.targetLanguageLabel, "中文")
        self.c.settings.setValue("subtitle.font_size", 30)
        with patch.object(AppConfig, "save", side_effect=OSError(errno.ENOSPC, "full")):
            self.c.applySettings()
        self.assertIn("磁盘空间不足", self.c.notice)
        self.assertTrue(self.c.settings.dirty)
        self.assertEqual(self.c.cfg.subtitle.font_size, 22)

    def test_font_shortcut_save_failure_keeps_dirty_draft(self):
        with patch.object(AppConfig, "save", side_effect=PermissionError):
            self.c.adjustFont(4)
        self.assertEqual(self.c.cfg.subtitle.font_size, 26)
        self.assertEqual(self.c.settings.draft["subtitle"]["font_size"], 26)
        self.assertTrue(self.c.settings.dirty)
        self.c.discardSettings()
        self.assertEqual(self.c.cfg.subtitle.font_size, 22)
        self.assertFalse(self.c.settings.dirty)

    def test_successful_font_save_clears_previous_failure_recovery(self):
        with patch.object(AppConfig, "save", side_effect=PermissionError):
            self.c.adjustFont(4)
        self.c.adjustFont(4)
        self.c.settings.setValue("ui.theme", "dark")
        self.c.discardSettings()
        self.assertEqual(self.c.cfg.subtitle.font_size, 30)

    def test_stage_recovery_does_not_clear_another_stage_error(self):
        self.running()
        self.c.togglePause()
        self.runtime.send("stage", stage="asr", status="error")
        self.runtime.send("stage", stage="translate", status="ready")
        self.assertIn("识别异常", self.c.statusDetail)
        self.assertEqual(self.c.state, "paused")

    def test_all_four_startup_modes(self):
        for silent in (False, True):
            for auto in (False, True):
                cfg = AppConfig()
                cfg.ui.silent_start, cfg.ui.auto_translate = silent, auto
                runtime = FakeRuntime()
                c = AppController(cfg, self.path, runtime)
                shown, notifications = [], []
                c.showRequested.connect(lambda shown=shown: shown.append(True))
                c.notification.connect(notifications.append)
                c.startup()
                self.assertEqual(bool(shown), not silent)
                self.assertEqual(bool(runtime.starts), auto)
                self.assertEqual(c.subtitleVisible, auto)
                if auto:
                    runtime.send("failed")
                    self.assertEqual(len(notifications), 1)
                c.close()

    def test_quit_draft_confirmation_then_serial_stop(self):
        confirm, finished = [], []
        self.c.quitConfirmationRequested.connect(lambda: confirm.append(True))
        self.c.quitReady.connect(lambda: finished.append(True))
        self.c.settings.setValue("ui.theme", "dark")
        self.c.requestQuit()
        self.assertTrue(confirm)
        self.assertEqual(self.runtime.stops, 0)
        self.c.confirmQuit()
        self.runtime.send("stopped")
        self.assertTrue(finished)
        self.assertFalse(self.path.exists())


class SubtitleTests(unittest.TestCase):
    def test_incremental_translation_and_eviction(self):
        model = SubtitleModel(2)
        changed, resets = [], []
        model.dataChanged.connect(lambda *args: changed.append(True))
        model.modelReset.connect(lambda: resets.append(True))
        model.add(1, "one", "en")
        model.translate(1, "一")
        self.assertEqual(model.data(model.index(0), Qt.ItemDataRole.UserRole + 2), "一")
        self.assertEqual(len(changed), 1)
        self.assertFalse(resets)
        model.add(2, "two", "en")
        model.add(3, "three", "en")
        model.translate(1, "late")
        self.assertEqual(model.rowCount(), 2)
        self.assertEqual(len(changed), 1)


class TranslationTests(unittest.TestCase):
    def test_chinese_request_specifies_target_script(self):
        for target, script in (("中文", "简体中文"), ("繁体中文", "繁体中文")):
            with self.subTest(target=target), patch("httpx.Client") as client:
                client.return_value.post.return_value = httpx.Response(
                    200, json={"choices": [{"message": {"content": "example-result"}}]},
                    request=httpx.Request("POST", "https://example.invalid/v1"),
                )
                translator = OpenAICompatTranslator("https://example.invalid/v1", "", "fake",
                                                    target)
                try:
                    translator.translate("example-input", source_language="zh")
                    body = client.return_value.post.call_args.kwargs["json"]
                    self.assertIn(script, body["messages"][0]["content"])
                finally:
                    translator.close()

    def test_concurrent_unsupported_thinking_option_retries_per_request(self):
        first_options_seen = threading.Barrier(2)
        retry_done = threading.Event()

        class Client:
            def post(self, url, json):
                if "enable_thinking" in json:
                    first_options_seen.wait(2)
                    if threading.current_thread().name == "second":
                        retry_done.wait(2)
                    return httpx.Response(400, request=httpx.Request("POST", url))
                retry_done.set()
                return httpx.Response(
                    200, json={"choices": [{"message": {"content": "ok"}}]},
                    request=httpx.Request("POST", url),
                )

        translator = OpenAICompatTranslator("https://example.invalid/v1", "", "fake")
        translator._client.close()
        translator._client = Client()
        results = {}

        def translate():
            try:
                results[threading.current_thread().name] = translator.translate("hello")
            except Exception as error:
                results[threading.current_thread().name] = type(error).__name__

        threads = [threading.Thread(target=translate, name=name) for name in ("first", "second")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
        self.assertEqual(results, {"first": "ok", "second": "ok"})


class LifecycleTests(unittest.TestCase):
    def test_chinese_scripts_are_translated_and_other_matching_languages_bypass(self):
        cases = (
            ("繁体中文", "zh", "简体汉字", True),
            ("中文", "zh", "繁體漢字", True),
            ("英语", "en", "hello", False),
            ("葡萄牙语", "pt", "olá", False),
        )
        for target, language, original, needs_translation in cases:
            with self.subTest(target=target):
                cfg = AppConfig()
                cfg.translate.target_language = target
                events = []
                pipeline = Pipeline(cfg, events.append)
                pipeline._engine = Mock()
                pipeline._engine.transcribe.return_value = AsrResult(language, original)
                with patch.object(pipeline, "_items", return_value=iter([np.ones(1600)])):
                    pipeline._asr_worker()
                translations = [e["translation"] for e in events if e["kind"] == "translation"]
                if needs_translation:
                    self.assertEqual(pipeline._trans_q.get_nowait(), (1, original, language))
                    self.assertEqual(translations, [])
                else:
                    self.assertTrue(pipeline._trans_q.empty())
                    self.assertEqual(translations, [original])

    def test_target_languages_have_exact_codes(self):
        for value in ("中文", "繁体中文", "英语", "葡萄牙语", "印地语", "印度尼西亚语", "波兰语"):
            self.assertTrue(target_lang_code(value), value)

    def test_capture_stop_failure_blocks_until_capture_finishes(self):
        class Capture:
            def __init__(self):
                self.allow_stop = threading.Event()

            def stop(self):
                return self.allow_stop.is_set()

        capture = Capture()
        pipeline = Pipeline(AppConfig(), lambda event: None)
        pipeline._capture = capture
        pipeline._session_started = True
        pipeline._STOP_TIMEOUT = 0.05
        self.assertFalse(pipeline.stop())
        self.assertIs(pipeline._capture, capture)
        with self.assertRaises(RuntimeError):
            pipeline.start()
        capture.allow_stop.set()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and not pipeline.stop():
            time.sleep(0.01)
        self.assertTrue(pipeline._cleanup_done.is_set())

    def test_restart_waits_for_cancelled_initialization_cleanup(self):
        entered, cleaned, release = threading.Event(), threading.Event(), threading.Event()
        observations = []

        class Session:
            def __init__(self, cfg, emit, cancel):
                self.emit, self.cancel = emit, cancel
                self.number = len(observations)
                observations.append("construct")
                if self.number:
                    assert cleaned.is_set()

            def start(self, paused=False):
                if not self.number:
                    entered.set()
                    release.wait(3)
                self.emit({"kind": "started", "paused": paused})

            def stop(self):
                self.cancel.set()
                cleaned.set()

            def set_paused(self, paused):
                pass

        runtime = RuntimeCoordinator(Session)
        try:
            first = runtime.start(AppConfig())
            self.assertTrue(entered.wait(1))
            second = runtime.start(AppConfig(), paused=True)
            self.assertGreater(second, first)
            self.assertEqual(len(observations), 1)
            release.set()
            wait_until(lambda: len(observations) == 2)
            self.assertTrue(cleaned.is_set())
        finally:
            release.set()
            runtime.close()

    def make_pipeline(self, capture_fails=False, translate_delay=None, translated=None):
        events, closed = [], []

        class ASR:
            def transcribe(self, audio, language=None):
                return AsrResult("en", "hello")

            def close(self):
                closed.append("asr")

        class Translator:
            def translate(self, text, source_language=""):
                if translated:
                    translated.set()
                if translate_delay:
                    translate_delay.wait(3)
                return "你好"

            def close(self):
                closed.append("translator")

        class VAD:
            def __init__(self, on_segment, **kwargs):
                self.callback = on_segment

            def feed(self, audio):
                self.callback(audio)

        class Capture:
            device_name = "fake"

            def start(self):
                if capture_fails:
                    raise RuntimeError("fake failure")

            def stop(self):
                closed.append("capture")

        pipeline = Pipeline(AppConfig(), events.append, asr_factory=lambda cfg: ASR(),
                            translator_factory=lambda cfg: Translator(),
                            capture_factory=lambda cfg, cb: Capture(), vad_factory=VAD)
        return pipeline, events, closed

    def test_capture_initialization_failure_cleans_all_resources(self):
        pipeline, events, closed = self.make_pipeline(capture_fails=True)
        with self.assertRaises(RuntimeError):
            pipeline.start()
        self.assertEqual(sorted(closed), ["asr", "capture", "translator"])
        self.assertFalse(pipeline._threads)
        pipeline.stop()
        self.assertEqual(len(closed), 3)

    def test_audio_to_translation_and_pause(self):
        pipeline, events, closed = self.make_pipeline()
        try:
            pipeline.start(paused=True)
            pipeline._on_audio_chunk(np.ones(1600, dtype=np.float32))
            time.sleep(0.15)
            self.assertFalse(any(e["kind"] == "entry" for e in events))
            pipeline.set_paused(False)
            pipeline._on_audio_chunk(np.ones(1600, dtype=np.float32))
            wait_until(lambda: any(e["kind"] == "translation" for e in events))
            self.assertEqual([e["kind"] for e in events if e["kind"] in ("entry", "translation")],
                             ["entry", "translation"])
        finally:
            pipeline.stop()
        self.assertEqual(len(closed), 3)

    def test_stop_waits_for_request_before_closing_client_and_drops_reply(self):
        release, entered = threading.Event(), threading.Event()
        pipeline, events, closed = self.make_pipeline(translate_delay=release, translated=entered)
        pipeline.start()
        pipeline._on_audio_chunk(np.ones(1600, dtype=np.float32))
        self.assertTrue(entered.wait(1))
        stop_thread = threading.Thread(target=pipeline.stop)
        stop_thread.start()
        try:
            time.sleep(0.05)
            self.assertNotIn("translator", closed)
            release.set()
            stop_thread.join(2)
            self.assertFalse(stop_thread.is_alive())
            self.assertNotIn("translation", [e["kind"] for e in events])
        finally:
            release.set()
            stop_thread.join(3)


if __name__ == "__main__":
    unittest.main()
