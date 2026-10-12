"""Tests for context-aware translation history and retry in TranslationStage."""

from __future__ import annotations

import threading
import time

from livetrans.config import TranslateConfig
from livetrans.events import Utterance
from livetrans.translate.base import Translator
from livetrans.translate.openai_compat import OpenAICompatTranslator
from livetrans.translate.stage import TranslationStage


def make_utterance(seq, text, language="en"):
    return Utterance(seq=seq, text=text, language=language, started_at=0.0, ended_at=1.0)


class FakeTranslator(Translator):
    """Records calls; fails the first `fail_times` calls."""

    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.calls = []
        self.lock = threading.Lock()

    def translate(self, text, source_language="", history=None):
        with self.lock:
            self.calls.append((text, source_language, list(history or [])))
            if len(self.calls) <= self.fail_times:
                raise RuntimeError("boom")
        return f"译文:{text}"


def make_stage(translator, target_language="中文"):
    cfg = TranslateConfig(target_language=target_language)
    received = []
    reports = []
    stage = TranslationStage(
        cfg,
        on_translation=received.append,
        report=lambda *a: reports.append(a),
        translator_factory=lambda cfg: translator,
    )
    return stage, received, reports


def run_stage(stage, utterances, wait=3.0):
    stage.start()
    try:
        for u in utterances:
            assert stage.submit(u)
        deadline = time.time() + wait
        while time.time() < deadline:
            # wait until workers drain (queue empty + no in-flight growth)
            time.sleep(0.05)
            if stage._queue.empty():
                time.sleep(0.2)
                if stage._queue.empty():
                    break
    finally:
        stage.stop()
    return stage


def test_history_passed_as_context():
    tr = FakeTranslator()
    stage, received, _ = make_stage(tr)
    run_stage(stage, [make_utterance(1, "hello"), make_utterance(2, "world")])
    assert len(received) == 2
    # second call must see the first pair as history
    _, _, history = tr.calls[1]
    assert history == [("en", "hello", "译文:hello")]


def test_history_bounded_to_three():
    tr = FakeTranslator()
    stage, received, _ = make_stage(tr)
    run_stage(stage, [make_utterance(i, f"s{i}") for i in range(1, 6)])
    assert len(received) == 5
    _, _, history = tr.calls[-1]
    assert len(history) == 3
    assert [h[1] for h in history] == ["s2", "s3", "s4"]


def test_retry_then_success():
    tr = FakeTranslator(fail_times=1)
    stage, received, reports = make_stage(tr)
    run_stage(stage, [make_utterance(1, "hello")])
    assert len(received) == 1
    assert received[0].text == "译文:hello"
    assert len(tr.calls) == 2  # one failure + one retry


def test_drop_after_retry_exhausted():
    tr = FakeTranslator(fail_times=10)
    stage, received, reports = make_stage(tr)
    run_stage(stage, [make_utterance(1, "hello")])
    assert received == []
    assert len(tr.calls) == 2
    assert any(r[1] == "error" for r in reports)


def test_same_language_bypass_still_records_history():
    tr = FakeTranslator()
    stage, received, _ = make_stage(tr, target_language="English")
    # utterance language 'en' == target 'en' -> bypass path
    run_stage(
        stage, [make_utterance(1, "hi", language="en"), make_utterance(2, "there", language="en")]
    )
    assert [t.text for t in received] == ["hi", "there"]
    assert tr.calls == []  # translator never invoked
    assert stage._history_snapshot() == [("en", "hi", "hi"), ("en", "there", "there")]


def test_translator_builds_history_messages(monkeypatch):
    # httpx(trust_env=True) chokes on bracketed IPv6 entries in no_proxy;
    # isolate the client construction from the ambient proxy environment.
    for var in (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "no_proxy",
        "NO_PROXY",
        "all_proxy",
        "ALL_PROXY",
    ):
        monkeypatch.delenv(var, raising=False)
    tr = OpenAICompatTranslator("http://x/v1", "k", "m", "中文")
    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "你好"}}]}

    class FakeClient:
        def post(self, url, json=None):
            captured["body"] = json
            return FakeResp()

        def close(self):
            pass

    tr._client = FakeClient()
    history = [("en", "hello", "你好呀"), ("en", "how are you", "你好吗")]
    assert tr.translate("good morning", source_language="en", history=history) == "你好"
    msgs = captured["body"]["messages"]
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user"]
    # history user turns keep the [lang] prefix convention
    assert msgs[1]["content"] == "[en] hello"
    assert msgs[2]["content"] == "你好呀"
    assert msgs[5]["content"] == "[en] good morning"
