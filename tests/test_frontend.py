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
from livetrans.events import Translation, Utterance
from livetrans.instance import SingleInstance
from livetrans.languages import target_lang_code
from livetrans.record.transcript import Recorder, load_transcript
from livetrans.session import Session
from livetrans.transcriber import Transcriber
from livetrans.translate.openai_compat import OpenAICompatTranslator
from livetrans.translate.stage import TranslationStage
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
        self.reconfigured = []
        self.resumes = []

    def start(self, cfg, paused=False, resume=False):
        self.generation += 1
        self.starts.append((asdict(cfg), paused))
        self.resumes.append(resume)
        return self.generation

    def stop(self):
        self.generation += 1
        self.stops += 1
        return self.generation

    def pause(self, paused):
        self.pauses.append(paused)

    def reconfigure(self, cfg):
        self.reconfigured.append(asdict(cfg))
        return self.generation

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
        cfg.translate.model = "custom"
        self.assertEqual(engine_config(cfg)["transcribe"], before["transcribe"])
        self.assertNotEqual(engine_config(cfg)["translate"], before["translate"])
        cfg.record.enabled = True
        self.assertEqual(engine_config(cfg)["transcribe"], before["transcribe"])
        cfg.asr.model = "base"
        self.assertNotEqual(engine_config(cfg)["transcribe"], before["transcribe"])


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
        self.c.settings.setValue("asr.model", "base")
        self.c.applySettings()
        self.c.applySettings()
        self.assertEqual(len(self.runtime.starts), 2)
        self.assertTrue(self.runtime.starts[-1][1])
        self.runtime.send("started", paused=True)
        self.assertEqual(self.c.state, "paused")

    def test_translation_apply_reconfigures_without_restart(self):
        self.running()
        self.runtime.send("entry", id=1, original="hello", language="en")
        self.c.settings.setValue("translate.model", "custom")
        self.c.applySettings()
        self.assertEqual(len(self.runtime.starts), 1)
        self.assertEqual([c["translate"]["model"] for c in self.runtime.reconfigured], ["custom"])
        self.assertEqual(self.c.state, "running")
        self.assertEqual(self.c.subtitles.rowCount(), 1)
        self.runtime.send("translation", id=1, translation="你好")
        self.assertFalse(self.c.noticeIsError)

    def test_engine_restart_continues_record_but_user_start_does_not(self):
        self.running()
        self.c.settings.setValue("asr.model", "base")
        self.c.applySettings()
        self.runtime.send("started", paused=False)
        self.c.stop()
        self.runtime.send("stopped")
        self.c.start()
        self.assertEqual(self.runtime.resumes, [False, True, False])

    def test_record_toggle_applies_in_place_and_reports_write_failure(self):
        self.running()
        self.assertFalse(self.c.recording)
        self.c.settings.setValue("record.enabled", True)
        self.c.applySettings()
        self.assertEqual(len(self.runtime.starts), 1)
        self.assertTrue(self.runtime.reconfigured[-1]["record"]["enabled"])
        self.assertTrue(self.c.recording)
        self.runtime.send("stage", stage="record", status="error", error="OSError")
        self.assertFalse(self.c.recording)
        self.assertIn("记录", self.c.statusDetail)
        self.runtime.send("stage", stage="record", status="ready")
        self.assertTrue(self.c.recording)

    def test_idle_apply_neither_starts_nor_reconfigures(self):
        self.c.settings.setValue("translate.model", "custom")
        self.c.applySettings()
        self.assertEqual((self.runtime.starts, self.runtime.reconfigured), ([], []))

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
                translations = []
                stage = TranslationStage(cfg.translate, translations.append, Mock())
                utterance = Utterance(1, original, language, 0.0, 1.0)
                self.assertTrue(stage.submit(utterance))
                if needs_translation:
                    self.assertEqual(stage._queue.get_nowait(), utterance)
                    self.assertEqual(translations, [])
                else:
                    self.assertTrue(stage._queue.empty())
                    self.assertEqual([t.text for t in translations], [original])

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
        transcriber = Transcriber(AppConfig(), Mock(), Mock())
        transcriber._capture = capture
        transcriber._cleanup.arm()
        transcriber._STOP_TIMEOUT = 0.05
        self.assertFalse(transcriber.stop())
        self.assertIs(transcriber._capture, capture)
        with self.assertRaises(RuntimeError):
            transcriber.start()
        capture.allow_stop.set()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and not transcriber.stop():
            time.sleep(0.01)
        self.assertTrue(transcriber._cleanup.done.is_set())

    def test_restart_waits_for_cancelled_initialization_cleanup(self):
        entered, cleaned, release = threading.Event(), threading.Event(), threading.Event()
        observations = []

        class Session:
            def __init__(self, cfg, emit, cancel, **context):
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

    def make_session(self, capture_fails=False, translate_delay=None, translated=None):
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

        session = Session(AppConfig(), events.append, asr_factory=lambda cfg: ASR(),
                          translator_factory=lambda cfg: Translator(),
                          capture_factory=lambda cfg, cb: Capture(), vad_factory=VAD)
        return session, events, closed

    def test_translation_change_keeps_recognition_and_hands_over_pending(self):
        session, events, closed = self.make_session()
        built = []
        release = threading.Event()

        class Translator:
            def __init__(self, name):
                self.name = name

            def translate(self, text, source_language=""):
                if self.name == "old":
                    release.wait(3)
                return f"{self.name}:{text}"

            def close(self):
                closed.append(f"translator-{self.name}")

        def factory(cfg):
            built.append(cfg.model)
            return Translator("old" if len(built) == 1 else "new")

        session._translator_factory = factory
        try:
            session.start()
            # Both old workers block, so later utterances wait in the old queue.
            for seq in range(1, 5):
                session._on_speech(AsrResult("en", f"s{seq}"), 0.0, 1.0)
            time.sleep(0.15)
            cfg = AppConfig()
            cfg.translate.model = "custom"
            session.reconfigure(cfg)
            self.assertEqual(built, [AppConfig().translate.model, "custom"])
            wait_until(lambda: sum(e["kind"] == "translation" for e in events) >= 2)
            release.set()
            wait_until(lambda: sum(e["kind"] == "translation" for e in events) == 4)
            texts = sorted(e["translation"] for e in events if e["kind"] == "translation")
            self.assertEqual(texts, ["new:s3", "new:s4", "old:s1", "old:s2"])
            self.assertNotIn("asr", closed)
        finally:
            release.set()
            self.assertTrue(session.stop())
        self.assertIn("translator-old", closed)
        self.assertIn("translator-new", closed)
        self.assertIn("asr", closed)

    def test_failed_translation_rebuild_keeps_recognition(self):
        session, events, closed = self.make_session()
        try:
            session.start()
            session._translator_factory = Mock(side_effect=RuntimeError)
            cfg = AppConfig()
            cfg.translate.model = "broken"
            session.reconfigure(cfg)
            self.assertIsNone(session._translation)
            self.assertIn({"kind": "stage", "stage": "translate", "status": "error",
                           "error": "RuntimeError"}, events)
            session._transcriber._on_audio_chunk(np.ones(1600, dtype=np.float32))
            wait_until(lambda: any(e["kind"] == "entry" for e in events))
        finally:
            self.assertTrue(session.stop())

    def test_capture_initialization_failure_cleans_all_resources(self):
        session, events, closed = self.make_session(capture_fails=True)
        with self.assertRaises(RuntimeError):
            session.start()
        self.assertEqual(sorted(closed), ["asr", "capture", "translator"])
        self.assertFalse(session._transcriber._threads)
        self.assertFalse(session._translation._threads)
        session.stop()
        self.assertEqual(len(closed), 3)

    def test_audio_to_translation_and_pause(self):
        session, events, closed = self.make_session()
        try:
            session.start(paused=True)
            session._transcriber._on_audio_chunk(np.ones(1600, dtype=np.float32))
            time.sleep(0.15)
            self.assertFalse(any(e["kind"] == "entry" for e in events))
            session.set_paused(False)
            session._transcriber._on_audio_chunk(np.ones(1600, dtype=np.float32))
            wait_until(lambda: any(e["kind"] == "translation" for e in events))
            self.assertEqual([e["kind"] for e in events if e["kind"] in ("entry", "translation")],
                             ["entry", "translation"])
        finally:
            session.stop()
        self.assertEqual(len(closed), 3)

    def test_stop_waits_for_request_before_closing_client_and_drops_reply(self):
        release, entered = threading.Event(), threading.Event()
        session, events, closed = self.make_session(translate_delay=release, translated=entered)
        session.start()
        session._transcriber._on_audio_chunk(np.ones(1600, dtype=np.float32))
        self.assertTrue(entered.wait(1))
        stop_thread = threading.Thread(target=session.stop)
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


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.now = [1_760_000_000.0]
        self.recorder = Recorder(self.dir, clock=lambda: self.now[0])

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    def test_out_of_order_and_missing_translations_merge_by_seq(self):
        path = self.recorder.open({"source": "system"})
        self.recorder.utterance(Utterance(1, "first", "en", 1.0, 2.0))
        self.recorder.utterance(Utterance(2, "second", "en", 2.0, 3.0))
        self.recorder.utterance(Utterance(3, "third", "en", 3.0, 4.0))
        self.recorder.translation(Translation(2, "第二"))
        self.recorder.translation(Translation(1, "第一"))
        self.recorder.mark("paused")
        self.recorder.close()
        with open(path, "a", encoding="utf-8") as stream:
            stream.write('{"type": "translation", "seq": 3, "te')  # torn by a crash
        data = load_transcript(path)
        self.assertEqual(data["meta"]["source"], "system")
        self.assertEqual([(e["seq"], e["text"], e["translation"]) for e in data["entries"]],
                         [(1, "first", "第一"), (2, "second", "第二"), (3, "third", "")])
        self.assertEqual([m["type"] for m in data["marks"]], ["paused"])

    def test_record_without_speech_is_removed_and_names_do_not_collide(self):
        first = self.recorder.open({})
        self.recorder.close()
        self.assertFalse(first.exists())
        a = self.recorder.open({})
        self.recorder.utterance(Utterance(1, "x", "en", 0, 1))
        self.recorder.close()
        b = self.recorder.open({})
        self.recorder.utterance(Utterance(1, "y", "en", 0, 1))
        self.recorder.close()
        self.assertNotEqual(a, b)
        self.assertTrue(a.exists() and b.exists())

    def test_write_failure_raises_once_then_closes(self):
        self.recorder.open({})
        real = self.recorder._file
        self.recorder._file = Mock(write=Mock(side_effect=OSError(errno.ENOSPC, "full")))
        try:
            with self.assertRaises(OSError):
                self.recorder.utterance(Utterance(1, "x", "en", 0, 1))
        finally:
            real.close()
        self.assertFalse(self.recorder.active)
        self.recorder.utterance(Utterance(2, "y", "en", 0, 1))

    def make_session(self, record=True, recorder=None):
        events = []
        cfg = AppConfig()
        cfg.record.enabled = record
        session = Session(
            cfg, events.append, recorder=recorder or self.recorder,
            asr_factory=lambda cfg: Mock(model_name="fake-asr",
                                           transcribe=Mock(return_value=AsrResult("en", "hi"))),
            translator_factory=lambda cfg: Mock(translate=Mock(return_value="你好")),
            capture_factory=lambda cfg, cb: Mock(device_name="fake", stop=Mock(return_value=None)),
            vad_factory=lambda on_segment, **kwargs: Mock(feed=on_segment),
        )
        return session, events

    def test_session_records_speech_translation_and_pause(self):
        session, events = self.make_session()
        try:
            session.start()
            path = self.recorder.path
            session._transcriber._on_audio_chunk(np.ones(16000, dtype=np.float32))
            wait_until(lambda: any(e["kind"] == "translation" for e in events))
            session.set_paused(True)
            session.set_paused(True)
        finally:
            self.assertTrue(session.stop())
        self.recorder.close()
        data = load_transcript(path)
        [entry] = data["entries"]
        self.assertEqual((entry["seq"], entry["text"], entry["translation"]), (1, "hi", "你好"))
        self.assertAlmostEqual(entry["end"] - entry["start"], 1.0, places=2)
        self.assertEqual([m["type"] for m in data["marks"]], ["started", "paused"])
        self.assertEqual(data["meta"]["target_language"], AppConfig().translate.target_language)
        self.assertNotIn("api_key", json.dumps(data["meta"]))

    def test_record_can_be_turned_off_and_open_failure_keeps_translating(self):
        session, events = self.make_session()
        try:
            session.start()
            session.reconfigure(AppConfig())
            self.assertFalse(self.recorder.active)
        finally:
            session.stop()
        broken = Mock(active=False, open=Mock(side_effect=PermissionError))
        session, events = self.make_session(recorder=broken)
        try:
            session.start()
            self.assertIn({"kind": "stage", "stage": "record", "status": "error",
                           "error": "PermissionError"}, events)
            self.assertTrue(any(e["kind"] == "started" for e in events))
        finally:
            session.stop()

    def test_coordinator_resume_keeps_record_and_numbering(self):
        seen = []

        class Session:
            def __init__(self, cfg, emit, cancel, *, ids, recorder):
                seen.append((next(ids), recorder))

            def start(self, paused=False):
                pass

            def stop(self):
                return True

        recorder = Mock()
        runtime = RuntimeCoordinator(Session, recorder)
        try:
            # Each start must take effect before the next one would cancel it.
            for count, resume in enumerate((False, True, False), 1):
                runtime.start(AppConfig(), resume=resume)
                wait_until(lambda count=count: len(seen) == count)
            runtime.stop()
        finally:
            runtime.close()
        self.assertEqual([n for n, _ in seen], [1, 2, 1])
        self.assertTrue(all(r is recorder for _, r in seen))
        # Two fresh starts, the stop and the shutdown end the record; the resume does not.
        self.assertEqual(recorder.close.call_count, 4)


if __name__ == "__main__":
    unittest.main()
