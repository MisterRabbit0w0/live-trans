"""正常停止排空尾句与在途工作；在途结果绑定原录制文件。

All fakes are in-process; no audio device, model or network is touched.
"""
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

import livetrans.audio.vad as vad_module
from livetrans.asr.base import AsrResult
from livetrans.config import AppConfig
from livetrans.record.transcript import Recorder, load_transcript
from livetrans.session import Session


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for lifecycle event")


class FakeVAD:
    """Buffers everything; emits only on finish() (and optionally per feed)."""

    def __init__(self, on_segment, emit_on_feed=False, **kwargs):
        self.callback = on_segment
        self.emit_on_feed = emit_on_feed
        self.buffer = []

    def feed(self, audio):
        if self.emit_on_feed:
            self.callback(audio)
        else:
            self.buffer.append(audio)

    def finish(self):
        if self.buffer:
            self.callback(np.concatenate(self.buffer))
            self.buffer = []


class FakeASR:
    def __init__(self, gate=None, language="en", text="hi"):
        self.gate = gate
        self.calls = 0
        self.language = language
        self.text = text
        self.entered = threading.Event()

    def transcribe(self, audio, language=None):
        self.calls += 1
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(10)
        return AsrResult(self.language, self.text)

    def close(self):
        pass


class FakeTranslator:
    def __init__(self, gate=None, text="你好"):
        self.gate = gate
        self.text = text
        self.entered = threading.Event()

    def translate(self, text, source_language=""):
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(10)
        return self.text

    def close(self):
        pass


class FakeCapture:
    device_name = "fake"

    def start(self):
        pass

    def stop(self):
        pass


class VadFinishTest(unittest.TestCase):
    """VadSegmenter.finish() 按既有最短语音规则 emit 或丢弃尾段。"""

    def make_segmenter(self, probs, **kwargs):
        emitted = []

        class StubModel:
            def reset(self):
                pass

            def prob(self, frame):
                return next(probs)

        original = vad_module._SileroOnnx
        vad_module._SileroOnnx = StubModel
        try:
            segmenter = vad_module.VadSegmenter(emitted.append, **kwargs)
        finally:
            vad_module._SileroOnnx = original
        return segmenter, emitted

    def feed(self, segmenter, n_frames):
        segmenter.feed(np.zeros(n_frames * vad_module.FRAME_SIZE, dtype=np.float32))

    def test_finish_emits_buffered_tail_meeting_min_speech(self):
        segmenter, emitted = self.make_segmenter(iter([0.9] * 12), min_speech_ms=100)
        self.feed(segmenter, 10)
        self.assertEqual(emitted, [])
        segmenter.finish()
        self.assertEqual(len(emitted), 1)
        self.assertGreater(len(emitted[0]), 0)

    def test_finish_drops_tail_shorter_than_min_speech(self):
        segmenter, emitted = self.make_segmenter(iter([0.9] * 5), min_speech_ms=250)
        self.feed(segmenter, 3)
        segmenter.finish()
        self.assertEqual(emitted, [])

    def test_finish_without_speech_is_a_noop(self):
        segmenter, emitted = self.make_segmenter(iter([0.0] * 12), min_speech_ms=100)
        self.feed(segmenter, 10)
        segmenter.finish()
        self.assertEqual(emitted, [])


class StopFlushTest(unittest.TestCase):
    """正常停止（drain）与故障中止（cancel）路径分开验证。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.recorder = Recorder(self.dir)

    def tearDown(self):
        self.recorder.close()
        self.tmp.cleanup()

    def make_session(self, vad_kwargs=None, translator=None, asr=None, record=True):
        events = []
        cfg = AppConfig()
        cfg.record.enabled = record
        session = Session(
            cfg, events.append, recorder=self.recorder,
            asr_factory=lambda cfg: asr or FakeASR(),
            translator_factory=lambda cfg: translator or FakeTranslator(),
            capture_factory=lambda cfg, cb: FakeCapture(),
            vad_factory=lambda on_segment, **kw: FakeVAD(on_segment, **(vad_kwargs or {})),
        )
        return session, events

    def entries(self, path):
        return load_transcript(path)["entries"]

    def test_normal_stop_flushes_tail_and_translation(self):
        """复现：已说完但未达静音阈值的尾句必须在正常停止后入记录。"""
        session, events = self.make_session()
        session.start()
        session._transcriber._on_audio_chunk(np.ones(16000, dtype=np.float32))
        path = self.recorder.path
        self.assertTrue(session.stop())
        # 停止预算内尾句的 ASR 和翻译都完成并写入原记录。
        [entry] = self.entries(path)
        self.assertEqual((entry["text"], entry["translation"]), ("hi", "你好"))
        self.assertIn("translation", [e["kind"] for e in events])

    def test_inflight_translation_completes_during_stop(self):
        gate = threading.Event()
        translator = FakeTranslator(gate=gate)
        session, events = self.make_session(
            vad_kwargs=dict(emit_on_feed=True), translator=translator)
        session.start()
        session._transcriber._on_audio_chunk(np.ones(1600, dtype=np.float32))
        path = self.recorder.path
        self.assertTrue(translator.entered.wait(1))  # 翻译在途时按下停止
        stopped = []
        stop_thread = threading.Thread(target=lambda: stopped.append(session.stop()))
        stop_thread.start()
        time.sleep(0.05)
        gate.set()
        stop_thread.join(3)
        self.assertFalse(stop_thread.is_alive())
        self.assertEqual(stopped, [True])
        [entry] = self.entries(path)
        self.assertEqual(entry["translation"], "你好")

    def test_abort_drops_tail_without_claiming_success(self):
        session, events = self.make_session()
        session.start()
        session._transcriber._on_audio_chunk(np.ones(16000, dtype=np.float32))
        path = self.recorder.path
        session._transcriber.request_stop()
        self.assertTrue(session._transcriber.wait_stopped(3))
        self.assertTrue(session.stop())
        # 中止路径丢弃尾句，不串记录也不声称保存。
        self.assertEqual(self.entries(path), [])
    def test_stop_drain_timeout_escalates_to_abort_without_hang(self):
        gate = threading.Event()
        asr = FakeASR(gate=gate)
        session, events = self.make_session(
            vad_kwargs=dict(emit_on_feed=True), asr=asr)
        session._STOP_TIMEOUT = 0.2
        session.start()
        session._transcriber._on_audio_chunk(np.ones(1600, dtype=np.float32))
        self.assertTrue(asr.entered.wait(1))  # ASR 卡住，排空预算耗尽
        started = time.monotonic()
        self.assertFalse(session.stop())
        self.assertLess(time.monotonic() - started, 2.0)
        gate.set()  # 释放卡住的 fake ASR，daemon 线程可收尾
        self.assertTrue(session._cancel.is_set())

    def test_stop_while_paused_is_bounded_and_keeps_pause_drop(self):
        session, events = self.make_session()
        session.start()
        session._transcriber._on_audio_chunk(np.ones(16000, dtype=np.float32))
        session.set_paused(True)
        # 暂停期间采集到的音频按既有语义丢弃。
        session._transcriber._on_audio_chunk(np.ones(16000, dtype=np.float32))
        path = self.recorder.path
        self.assertTrue(session.stop())
        [entry] = self.entries(path)
        self.assertEqual(entry["text"], "hi")

    def test_hotcut_drops_late_utterance_and_translation_from_old_file(self):
        """热切（close+open 新文件）后，迟到的 ASR/翻译结果丢弃，不串进新文件。"""
        asr_gate, tr_gate = threading.Event(), threading.Event()
        asr_gate.set()  # 第一句先放行；tr_gate 保持阻塞让翻译"在途"
        asr, translator = FakeASR(gate=asr_gate), FakeTranslator(gate=tr_gate)
        session, events = self.make_session(
            vad_kwargs=dict(emit_on_feed=True), asr=asr, translator=translator)
        session.start()
        path_a = self.recorder.path
        # 第一句：翻译在途时热切的下半段先让它完成，保证文件 A 有内容。
        session._transcriber._on_audio_chunk(np.ones(1600, dtype=np.float32))
        wait_until(lambda: translator.entered.is_set())
        tr_gate.set()
        wait_until(lambda: self.entries(path_a))
        # 第二句：ASR 在途时热切记录文件。
        asr_gate.clear()
        translator.entered.clear()
        tr_gate.clear()
        tr_gate.set()  # 翻译不阻塞；只让 ASR 卡住形成在途结果
        session._transcriber._on_audio_chunk(np.ones(1600, dtype=np.float32))
        wait_until(lambda: asr.calls >= 2)
        self.recorder.close()
        path_b = self.recorder.open({})
        self.assertNotEqual(path_a, path_b)
        asr_gate.set()
        wait_until(lambda: any(e["kind"] == "entry" and e["id"] == 2 for e in events))
        self.assertTrue(session.stop())
        # 旧文件保持原样；迟到的 utterance/translation 不写入新文件。
        self.assertEqual(len(self.entries(path_a)), 1)
        self.assertEqual(self.entries(path_b), [])

    def test_translation_late_after_hotcut_never_touches_new_file(self):
        tr_gate = threading.Event()
        translator = FakeTranslator(gate=tr_gate)
        session, events = self.make_session(
            vad_kwargs=dict(emit_on_feed=True), translator=translator)
        session.start()
        path_a = self.recorder.path
        session._transcriber._on_audio_chunk(np.ones(1600, dtype=np.float32))
        self.assertTrue(translator.entered.wait(1))
        self.recorder.close()
        path_b = self.recorder.open({})
        tr_gate.set()
        self.assertTrue(session.stop())
        self.assertEqual(len(self.entries(path_a)), 1)  # utterance 在热切前已写入
        self.assertEqual(self.entries(path_b), [])
        # 翻译仍投递给 UI，只是不串进新记录。
        self.assertIn("translation", [e["kind"] for e in events])


if __name__ == "__main__":
    unittest.main()
