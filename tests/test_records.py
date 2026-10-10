"""Tests for RecordManager and AI summary generation."""
from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from livetrans.app.records import RecordManager
from livetrans.config import AppConfig
from livetrans.record.summary import save_summary


class InlineLoop:
    """post 立即执行：worker 的回调在测试线程可见，便于确定性断言。"""

    def post(self, fn, *args):
        fn(*args)


def fake_response(payload, status_code=200):
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.raise_for_status = Mock(return_value=None)
    return resp


class FakeHttp:
    """可控的 httpx.Client 替身：记录请求、可闸门阻塞、可定制响应。"""

    def __init__(self, payload=None):
        self.requests = []
        self.gate = threading.Event()
        self.payload = payload or {
            "choices": [{"message": {"content": "### 📌 纪要\n讨论了问候事宜。"},
                         "finish_reason": "stop"}]
        }
        self.handler = lambda body: fake_response(self.payload)

    @property
    def client_class(self):
        http = self

        class Client:
            def __init__(self, headers=None, timeout=None):
                self.headers = headers
                self.timeout = timeout

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, url, json=None):
                http.requests.append({"url": url, "json": json})
                http.gate.wait(10)
                return http.handler(json)

        return Client


class RecordManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg = AppConfig()
        self.cfg.translate.base_url = "http://fake-api/v1"
        self.cfg.translate.api_key = "test-key"
        self.cfg.translate.model = "test-model"
        self.cfg_holder = [self.cfg]  # 模拟 applySettings 替换整个 cfg
        self.loop = InlineLoop()
        self.events = []
        self.curr_path = None
        self.mgr = RecordManager(
            self.cfg,
            self.loop,
            get_current_record_path=lambda: self.curr_path,
            records_directory=self.dir,
            config_provider=lambda: self.cfg_holder[0],
            notify=lambda name, payload: self.events.append((name, payload)),
        )
        self.http = FakeHttp()
        self.http.gate.set()  # 默认放行
        patcher = patch("livetrans.record.summary.httpx.Client", self.http.client_class)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def _create_record(self, name: str, entries_count: int = 3, mtime_offset: int = 0,
                       session_t: float = 100.0, start_base: float = 0.0) -> Path:
        p = self.dir / name
        lines = [
            json.dumps({"type": "session", "version": 1, "t": session_t, "source": "system"}),
        ]
        for i in range(entries_count):
            lines.append(json.dumps({
                "type": "utterance", "seq": i + 1,
                "start": start_base + float(i * 2), "end": start_base + float(i * 2 + 1.5),
                "language": "en", "text": f"Hello {i + 1}",
            }))
            lines.append(json.dumps({
                "type": "translation", "seq": i + 1, "text": f"你好 {i + 1}",
            }))
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if mtime_offset:
            t = time.time() + mtime_offset
            import os
            os.utime(p, (t, t))
        return p

    def _wait_status(self, name, mode, wanted, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.mgr.summary_status(name=name, mode=mode)["status"]
            if status in (wanted if isinstance(wanted, tuple) else (wanted,)):
                return status
            time.sleep(0.01)
        raise AssertionError(f"等待 {wanted} 超时，当前 {status}")

    def _wait_requests(self, count, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.http.requests) >= count:
                return
            time.sleep(0.01)
        raise AssertionError("等待 HTTP 请求超时")

    def test_list_records_empty_and_sorted(self):
        self.assertEqual(self.mgr.list_records(), [])

        self._create_record("20260928-100000.jsonl", entries_count=2, mtime_offset=-10)
        p2 = self._create_record("20260928-120000.jsonl", entries_count=5, mtime_offset=0)
        self.curr_path = p2

        records = self.mgr.list_records()
        self.assertEqual(len(records), 2)
        # Newest first
        self.assertEqual(records[0]["name"], "20260928-120000.jsonl")
        self.assertEqual(records[0]["utterances"], 5)
        self.assertTrue(records[0]["is_current"])
        self.assertFalse(records[0]["has_summary"])

        self.assertEqual(records[1]["name"], "20260928-100000.jsonl")
        self.assertEqual(records[1]["utterances"], 2)
        self.assertFalse(records[1]["is_current"])

    def test_get_record_and_directory_traversal_protection(self):
        self._create_record("test-session.jsonl", entries_count=2)
        record = self.mgr.get_record("test-session")
        self.assertEqual(record["name"], "test-session.jsonl")
        self.assertEqual(len(record["entries"]), 2)
        self.assertEqual(record["entries"][0]["text"], "Hello 1")
        self.assertEqual(record["entries"][0]["translation"], "你好 1")
        self.assertIsNone(record["summary"])

        with self.assertRaises(FileNotFoundError):
            self.mgr.get_record("../../non-existent")

    def test_delete_record(self):
        p = self._create_record("to-delete.jsonl", entries_count=1)
        save_summary(p, {"content": "summary test", "mode": "minutes"})
        self.assertTrue((self.dir / "to-delete.summary.json").is_file())

        self.mgr.delete_record("to-delete.jsonl")
        self.assertFalse(p.is_file())
        self.assertFalse((self.dir / "to-delete.summary.json").is_file())

    def test_delete_current_active_record_rejected(self):
        p = self._create_record("active.jsonl", entries_count=1)
        self.curr_path = p
        with self.assertRaises(RuntimeError):
            self.mgr.delete_record("active.jsonl")
    def test_summarize_is_async_and_notifies_done(self):
        self._create_record("sum-test.jsonl", entries_count=2)
        result = self.mgr.summarize_record("sum-test.jsonl", mode="minutes")
        self.assertIn(result["status"], ("queued", "running"))
        self.assertEqual(result["mode"], "minutes")
        # 提交即时返回，不等待 HTTP
        self._wait_status("sum-test.jsonl", "minutes", "done")

        status = self.mgr.summary_status(record_id="sum-test.jsonl", mode="minutes")
        self.assertEqual(status["status"], "done")
        self.assertIn("讨论了问候事宜", status["summary"]["content"])
        self.assertEqual(status["summary"]["mode"], "minutes")
        self.assertTrue((self.dir / "sum-test.summary.json").is_file())
        # 终态经 record.summary 事件推送，含 record_id/mode/status
        done = [p for n, p in self.events
                if n == "record.summary" and p["status"] == "done"]
        self.assertEqual(len(done), 1)
        self.assertEqual((done[0]["record_id"], done[0]["mode"]),
                         ("sum-test.jsonl", "minutes"))
        self.assertNotIn("test-key", json.dumps(done))  # 密钥不进通知

    def test_summary_status_reads_valid_cache(self):
        self._create_record("sum-test.jsonl", entries_count=2)
        self.mgr.summarize_record("sum-test.jsonl", mode="minutes")
        self._wait_status("sum-test.jsonl", "minutes", "done")
        calls = len(self.http.requests)
        # 缓存命中：提交返回 done，不再发请求
        result = self.mgr.summarize_record("sum-test.jsonl", mode="minutes")
        self.assertEqual(result["status"], "done")
        self.assertEqual(len(self.http.requests), calls)
        # force 重新生成
        self.mgr.summarize_record("sum-test.jsonl", mode="minutes", force=True)
        self._wait_status("sum-test.jsonl", "minutes", "done")
        self.assertEqual(len(self.http.requests), calls + 1)

    def test_summary_status_idle_without_cache(self):
        self._create_record("idle.jsonl", entries_count=1)
        status = self.mgr.summary_status(record_id="idle.jsonl", mode="minutes")
        self.assertEqual(status["status"], "idle")

    def test_single_flight_and_inflight_status(self):
        self._create_record("slow.jsonl", entries_count=2)
        self.http.gate.clear()
        self.mgr.summarize_record("slow.jsonl", mode="minutes")
        self._wait_requests(1)
        # 进行中重复提交返回 running，不另起任务
        again = self.mgr.summarize_record("slow.jsonl", mode="minutes", force=True)
        self.assertEqual(again["status"], "running")
        # 切页 GET 能看到在途状态
        self.assertIn(
            self.mgr.summary_status("slow.jsonl", mode="minutes")["status"],
            ("queued", "running"))
        self.http.gate.set()
        self._wait_status("slow.jsonl", "minutes", "done")
        self.assertEqual(len(self.http.requests), 1)
        # 不同 mode 可并行
        self.http.gate.clear()
        self.mgr.summarize_record("slow.jsonl", mode="concise")
        self._wait_requests(2)
        self.http.gate.set()
        self._wait_status("slow.jsonl", "concise", "done")

    def test_cancel_drops_late_result(self):
        p = self._create_record("cancel-me.jsonl", entries_count=2)
        self.http.gate.clear()
        self.mgr.summarize_record("cancel-me.jsonl", mode="minutes")
        self._wait_requests(1)
        result = self.mgr.summary_cancel(record_id="cancel-me.jsonl", mode="minutes")
        self.assertEqual(result["status"], "cancelled")
        self.http.gate.set()
        time.sleep(0.2)  # 让晚到结果走完收尾路径
        self.assertFalse(p.with_suffix(".summary.json").is_file())
        self.assertEqual(
            self.mgr.summary_status("cancel-me.jsonl", mode="minutes")["status"],
            "cancelled")
        cancelled = [p for n, p in self.events
                     if n == "record.summary" and p["status"] == "cancelled"]
        self.assertTrue(cancelled)
        # 取消后可重新提交
        self.mgr.summarize_record("cancel-me.jsonl", mode="minutes")
        self._wait_status("cancel-me.jsonl", "minutes", "done")
        self.assertTrue(p.with_suffix(".summary.json").is_file())

    def test_delete_drops_late_result(self):
        p = self._create_record("gone.jsonl", entries_count=2)
        self.http.gate.clear()
        self.mgr.summarize_record("gone.jsonl", mode="minutes")
        self._wait_requests(1)
        self.mgr.delete_record("gone.jsonl")
        self.http.gate.set()
        time.sleep(0.2)
        self.assertFalse(p.is_file())
        self.assertFalse(p.with_suffix(".summary.json").is_file())

    def test_cache_key_mismatch_regenerates(self):
        # 无版本旧缓存 → 视为未知，状态 idle，重新生成
        legacy = self._create_record("legacy.jsonl", entries_count=2)
        save_summary(legacy, {"content": "旧摘要", "mode": "minutes", "model": "old"})
        self.assertEqual(
            self.mgr.summary_status("legacy.jsonl", mode="minutes")["status"], "idle")
        self.mgr.summarize_record("legacy.jsonl", mode="minutes")
        self._wait_status("legacy.jsonl", "minutes", "done")
        base = len(self.http.requests)

        # 换模型 → 缓存键不匹配 → 旧 done 不冒充有效 → 重新生成
        self._create_record("keyed.jsonl", entries_count=2)
        self.mgr.summarize_record("keyed.jsonl", mode="minutes")
        self._wait_status("keyed.jsonl", "minutes", "done")
        base += 1
        self.cfg_holder[0].translate.model = "other-model"
        self.assertEqual(
            self.mgr.summary_status("keyed.jsonl", mode="minutes")["status"], "idle")
        self.mgr.summarize_record("keyed.jsonl", mode="minutes")
        self._wait_status("keyed.jsonl", "minutes", "done")
        self.assertEqual(len(self.http.requests), base + 1)

        # 源文件续写 → 内容哈希变化 → 重新生成
        self._create_record("keyed.jsonl", entries_count=3)
        self.assertEqual(
            self.mgr.summary_status("keyed.jsonl", mode="minutes")["status"], "idle")

    def test_cache_write_failure_reports_error(self):
        p = self._create_record("write-fail.jsonl", entries_count=2)
        with patch("livetrans.app.records.save_summary",
                   side_effect=OSError("disk full")):
            self.mgr.summarize_record("write-fail.jsonl", mode="minutes")
            self._wait_status("write-fail.jsonl", "minutes", "error")
        status = self.mgr.summary_status("write-fail.jsonl", mode="minutes")
        self.assertEqual(status["status"], "error")
        self.assertIn("disk full", status["error"])
        self.assertFalse(p.with_suffix(".summary.json").is_file())
        errors = [p for n, p in self.events
                  if n == "record.summary" and p["status"] == "error"]
        self.assertTrue(errors)

    def test_snapshot_does_not_drift_with_settings(self):
        self._create_record("snap.jsonl", entries_count=2)
        self.mgr.summarize_record("snap.jsonl", mode="minutes")
        self._wait_status("snap.jsonl", "minutes", "done")
        self.assertIn("fake-api", self.http.requests[0]["url"])

        # applySettings 换端点/模型后，新任务使用新配置
        new_cfg = AppConfig()
        new_cfg.translate.base_url = "http://new-endpoint/v1"
        new_cfg.translate.api_key = "new-key"
        new_cfg.translate.model = "new-model"
        self.cfg_holder[0] = new_cfg
        self.mgr.summarize_record("snap.jsonl", mode="concise")
        self._wait_status("snap.jsonl", "concise", "done")
        self.assertIn("new-endpoint", self.http.requests[1]["url"])
        self.assertEqual(self.http.requests[1]["json"]["model"], "new-model")

    def test_input_budget_exceeded_reports_error(self):
        self.cfg_holder[0].record.summary_max_chars = 10
        self._create_record("huge.jsonl", entries_count=3)
        self.mgr.summarize_record("huge.jsonl", mode="minutes")
        self._wait_status("huge.jsonl", "minutes", "error")
        self.assertEqual(len(self.http.requests), 0)  # 超限不发出请求
        status = self.mgr.summary_status("huge.jsonl", mode="minutes")
        self.assertIn("过长", status["error"])

    def test_truncated_output_reports_error(self):
        self.http.payload = {
            "choices": [{"message": {"content": "### 半截纪要"},
                         "finish_reason": "length"}]
        }
        p = self._create_record("trunc.jsonl", entries_count=2)
        self.mgr.summarize_record("trunc.jsonl", mode="minutes")
        self._wait_status("trunc.jsonl", "minutes", "error")
        self.assertIn("截断", self.mgr.summary_status("trunc.jsonl", "minutes")["error"])
        self.assertFalse(p.with_suffix(".summary.json").is_file())

    def test_empty_content_reports_error(self):
        self.http.payload = {
            "choices": [{"message": {"content": "   "}, "finish_reason": "stop"}]
        }
        p = self._create_record("empty.jsonl", entries_count=2)
        self.mgr.summarize_record("empty.jsonl", mode="minutes")
        self._wait_status("empty.jsonl", "minutes", "error")
        self.assertIn("为空", self.mgr.summary_status("empty.jsonl", "minutes")["error"])
        self.assertFalse(p.with_suffix(".summary.json").is_file())

    def test_unix_timestamps_become_relative_in_request_and_export(self):
        from livetrans.record.summary import format_transcript_text, session_origin
        # 真实形态：会话原点 1_760_000_000，发言是 Unix 绝对时间
        t0 = 1_760_000_000.0
        self._create_record("unix.jsonl", entries_count=2,
                            session_t=t0, start_base=t0)
        self.mgr.summarize_record("unix.jsonl", mode="minutes")
        self._wait_status("unix.jsonl", "minutes", "done")
        request_text = json.dumps(self.http.requests[0]["json"], ensure_ascii=False)
        self.assertIn("[00:00]", request_text)
        self.assertIn("[00:02]", request_text)
        self.assertNotIn("29333333", request_text)  # 绝不再出现几千万分钟

        # 缺 meta 时回退到最早发言为原点
        entries = [{"start": 500.0, "text": "a"}, {"start": 5661.0, "text": "b"}]
        origin = session_origin({}, entries)
        text = format_transcript_text(entries, origin)
        self.assertIn("[00:00] a", text)
        self.assertIn("[1:26:01] b", text)

        # 导出同样使用相对时间与正确的 meta 含义
        exported = self.mgr.export_record("unix.jsonl")
        self.assertIn("`00:00`", exported["content"])
        self.assertIn("**声音来源**：system", exported["content"])
        self.assertNotIn("记录时间**：system", exported["content"])

    def test_export_record(self):
        p = self._create_record("export-test.jsonl", entries_count=2)
        save_summary(p, {"content": "### 📌 摘要\n测试内容", "model": "mock-llm"})
        exported = self.mgr.export_record("export-test.jsonl")
        self.assertEqual(exported["filename"], "export-test.md")
        self.assertIn("LiveTrans 语音与翻译记录导出", exported["content"])
        self.assertIn("AI 智能总结与纪要", exported["content"])
        self.assertIn("Hello 1", exported["content"])
        self.assertIn("你好 1", exported["content"])


if __name__ == "__main__":
    unittest.main()
