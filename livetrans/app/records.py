"""Record management and AI summary coordinator."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ..config import AppConfig
from ..record.summary import (
    format_markdown_export,
    generate_summary,
    load_summary,
    save_summary,
)
from ..record.transcript import load_transcript, records_dir

log = logging.getLogger(__name__)


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


class RecordManager:
    """Manages saved session transcripts and AI-generated meeting minutes."""

    def __init__(
        self,
        cfg: AppConfig,
        loop,
        get_current_record_path: Callable[[], Path | None] = lambda: None,
        records_directory: Path | None = None,
    ):
        self._cfg = cfg
        self._loop = loop
        self._get_current_record_path = get_current_record_path
        self._dir = records_directory

    @property
    def directory(self) -> Path:
        return self._dir or records_dir()

    def list_records(self) -> list[dict]:
        """List all recordings, sorted by creation date descending."""
        d = self.directory
        if not d.is_dir():
            return []
        current_path = self._get_current_record_path()
        results = []
        for file in sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                stat = file.stat()
                summary_file = file.with_suffix(".summary.json")
                # Quick count of utterances without loading full JSON
                with open(file, encoding="utf-8", errors="ignore") as f:
                    utterance_count = sum(
                        1
                        for line in f
                        if '"type": "utterance"' in line or '"type":"utterance"' in line
                    )
                is_curr = False
                if current_path is not None:
                    try:
                        is_curr = file.resolve() == current_path.resolve()
                    except OSError:
                        pass
                results.append({
                    "name": file.name,
                    "stem": file.stem,
                    "size": stat.st_size,
                    "size_label": format_size(stat.st_size),
                    "modified": stat.st_mtime,
                    "date_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "utterances": utterance_count,
                    "has_summary": summary_file.is_file(),
                    "is_current": is_curr,
                })
            except Exception as error:
                log.warning("读取记录文件 %s 属性失败: %s", file.name, error)
        return results

    def _resolve_file(self, name: str) -> Path:
        # Security: prevent directory traversal
        clean_name = Path(name).name
        if not clean_name.endswith(".jsonl"):
            clean_name += ".jsonl"
        target = self.directory / clean_name
        if not target.is_file():
            raise FileNotFoundError(f"未找到记录文件: {name}")
        return target

    def get_record(self, name: str) -> dict:
        file = self._resolve_file(name)
        data = load_transcript(file)
        summary = load_summary(file)
        stat = file.stat()
        return {
            "name": file.name,
            "stem": file.stem,
            "meta": data.get("meta", {}),
            "entries": data.get("entries", []),
            "summary": summary,
            "size_label": format_size(stat.st_size),
            "date_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def delete_record(self, name: str) -> bool:
        file = self._resolve_file(name)
        current = self._get_current_record_path()
        if current is not None:
            try:
                if file.resolve() == current.resolve():
                    raise RuntimeError("当前正在写入该记录文件，无法删除")
            except OSError:
                pass
        summary_file = file.with_suffix(".summary.json")
        try:
            file.unlink(missing_ok=True)
            if summary_file.is_file():
                summary_file.unlink(missing_ok=True)
            return True
        except OSError as error:
            log.warning("删除记录文件失败 (%s)", error)
            raise

    def summarize_record(self, name: str, mode: str = "minutes", force: bool = False) -> dict:
        file = self._resolve_file(name)
        if not force:
            existing = load_summary(file)
            if existing and existing.get("mode") == mode:
                return existing

        data = load_transcript(file)
        entries = data.get("entries", [])
        if not entries:
            raise ValueError("该记录文件中没有有效的语音条目，无法生成纪要")

        summary = generate_summary(entries, self._cfg.translate, mode=mode)
        save_summary(file, summary)
        return summary

    def export_record(self, name: str, format: str = "md") -> dict:
        file = self._resolve_file(name)
        data = load_transcript(file)
        summary = load_summary(file)
        text = format_markdown_export(data, summary)
        return {
            "name": file.name,
            "filename": f"{file.stem}.md",
            "content": text,
        }
