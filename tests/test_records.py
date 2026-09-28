"""Tests for RecordManager and AI summary generation."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from livetrans.app.records import RecordManager
from livetrans.config import AppConfig
from livetrans.record.summary import save_summary


class RecordManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg = AppConfig()
        self.cfg.translate.base_url = "http://fake-api/v1"
        self.cfg.translate.api_key = "test-key"
        self.cfg.translate.model = "test-model"
        self.loop = Mock()
        self.curr_path = None
        self.mgr = RecordManager(
            self.cfg,
            self.loop,
            get_current_record_path=lambda: self.curr_path,
            records_directory=self.dir,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _create_record(self, name: str, entries_count: int = 3, mtime_offset: int = 0) -> Path:
        p = self.dir / name
        lines = [
            json.dumps({"type": "session", "version": 1, "t": 100.0, "source": "system"}),
        ]
        for i in range(entries_count):
            lines.append(json.dumps({
                "type": "utterance", "seq": i + 1, "start": float(i * 2), "end": float(i * 2 + 1.5),
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

    @patch("httpx.Client")
    def test_summarize_and_caching(self, mock_client_cls):
        mock_client = Mock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "### 📌 主题与核心主旨\n讨论了问候事宜。"}}]
        }
        mock_client.post.return_value = mock_resp
        self._create_record("sum-test.jsonl", entries_count=2)
        summary = self.mgr.summarize_record("sum-test.jsonl", mode="minutes")
        self.assertIn("讨论了问候事宜", summary["content"])
        self.assertEqual(summary["mode"], "minutes")
        self.assertTrue((self.dir / "sum-test.summary.json").is_file())

        # Second call without force uses cache (no API call)
        mock_client.post.reset_mock()
        cached = self.mgr.summarize_record("sum-test.jsonl", mode="minutes", force=False)
        self.assertEqual(cached["content"], summary["content"])
        mock_client.post.assert_not_called()

        # Call with force calls API again
        self.mgr.summarize_record("sum-test.jsonl", mode="minutes", force=True)
        mock_client.post.assert_called_once()

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
