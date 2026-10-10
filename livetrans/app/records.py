"""Record management and AI summary coordinator."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ..config import AppConfig
from ..record.summary import (
    SummaryService,
    format_markdown_export,
    generate_summary,
    load_summary,
    save_summary,
    summary_cache_key,
)
from ..record.transcript import load_transcript, parse_transcript, records_dir

log = logging.getLogger(__name__)

# 同一时刻最多并行的纪要请求数；超出的任务排队等待（提交立即返回）
MAX_SUMMARY_JOBS = 4


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


class _SummaryJob:
    """一次纪要提交的全部上下文。

    仅保存在内存中：核心进程重启即视为中断，不声称自动续跑。
    ``cancelled`` 由取消/删除置位，在途 HTTP 无法撤回，晚到结果直接丢弃。
    """

    def __init__(self, record_id: str, mode: str, path: Path,
                 service: SummaryService, cache_key: str):
        self.record_id = record_id
        self.mode = mode
        self.path = path
        self.service = service
        self.cache_key = cache_key
        self.status = "queued"  # queued | running | done | error | cancelled
        self.error = ""
        self.summary: dict | None = None
        self.cancelled = threading.Event()


class RecordManager:
    """Manages saved session transcripts and AI-generated meeting minutes.

    纪要任务在专用 daemon 线程执行，不占用 loop：``summarize_record`` 立即返回
    ``{status, mode}``，完成/失败经 ``notify``（即 ``record.summary`` 事件）推送，
    切页后可用 ``summary_status`` 取回在途/终态。任务表只在内存中，核心重启
    后旧任务一律视为中断，不做自动续跑。
    """

    def __init__(
        self,
        cfg: AppConfig,
        loop,
        get_current_record_path: Callable[[], Path | None] = lambda: None,
        records_directory: Path | None = None,
        config_provider: Callable[[], AppConfig] | None = None,
        notify: Callable[[str, dict], None] | None = None,
    ):
        self._loop = loop
        self._get_current_record_path = get_current_record_path
        self._dir = records_directory
        # 提交瞬间取当前已应用配置的不可变快照；缺省时退回构造时的 cfg
        self._config_provider = config_provider or (lambda: cfg)
        self._notify = notify or (lambda name, payload: None)
        self._jobs: dict[tuple[str, str], _SummaryJob] = {}
        self._job_slots = threading.BoundedSemaphore(MAX_SUMMARY_JOBS)

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
        record_id = self._record_id(name)
        try:
            file.unlink(missing_ok=True)
            summary_file = file.with_suffix(".summary.json")
            if summary_file.is_file():
                summary_file.unlink(missing_ok=True)
        except OSError as error:
            log.warning("删除记录文件失败 (%s)", error)
            raise
        # 删除后晚到的纪要结果失效，不写缓存也不覆盖任何新记录
        self._invalidate_jobs(record_id)
        return True

    # ----- 纪要任务 ----------------------------------------------------

    @staticmethod
    def _record_id(name: str) -> str:
        clean = Path(str(name)).name
        return clean if clean.endswith(".jsonl") else clean + ".jsonl"

    def _invalidate_jobs(self, record_id: str, mode: str | None = None):
        """标失效并向壳广播 cancelled；同一事件对每个 (id, mode) 只发一次。"""
        for (rid, m), job in list(self._jobs.items()):
            if rid != record_id or (mode is not None and m != mode):
                continue
            if job.status in ("queued", "running"):
                job.cancelled.set()
                job.status = "cancelled"
                self._emit_summary(job)

    def _emit_summary(self, job: _SummaryJob):
        payload = {"record_id": job.record_id, "mode": job.mode, "status": job.status}
        if job.status == "error":
            payload["error"] = job.error
        self._notify("record.summary", payload)

    def summarize_record(self, name: str | None = None, record_id: str | None = None,
                         mode: str = "minutes", force: bool = False) -> dict:
        """提交纪要任务，立即返回 ``{status, mode}``；结果经 record.summary 事件推送。

        同一 record_id+mode 单飞：进行中再次提交返回 running，不另起任务。
        """
        rid = self._record_id(record_id or name or "")
        if not rid or rid == ".jsonl":
            raise ValueError("缺少记录标识")
        file = self._resolve_file(rid)
        key = (rid, mode)
        job = self._jobs.get(key)
        if job is not None and job.status in ("queued", "running"):
            return {"record_id": rid, "mode": mode, "status": "running"}

        # 提交瞬间的不可变服务快照；在途任务不随后续设置编辑漂移
        cfg = self._config_provider()
        service = SummaryService.from_config(
            cfg.translate, getattr(cfg.record, "summary_max_chars", None))
        # 读源文件一次：内容哈希进缓存键，同一批字节进解析，杜绝读到一半被改
        source_bytes = file.read_bytes()
        cache_key = summary_cache_key(source_bytes, mode, service)
        if not force:
            existing = load_summary(file)
            if existing and existing.get("cache_key") == cache_key:
                # 无版本或键不一致的旧缓存一律视为未知，重新生成
                job = _SummaryJob(rid, mode, file, service, cache_key)
                job.status = "done"
                job.summary = existing
                self._jobs[key] = job
                self._emit_summary(job)
                return {"record_id": rid, "mode": mode, "status": "done"}

        job = _SummaryJob(rid, mode, file, service, cache_key)
        self._jobs[key] = job
        threading.Thread(
            target=self._run_summary, args=(job, source_bytes),
            name=f"livetrans-summary-{rid}", daemon=True,
        ).start()
        return {"record_id": rid, "mode": mode, "status": job.status}

    def _run_summary(self, job: _SummaryJob, source_bytes: bytes):
        """Worker 线程：排队等待并发名额 → 请求 → 把结果交回 loop 判定有效性。"""
        with self._job_slots:
            if job.cancelled.is_set():
                return
            job.status = "running"
            try:
                data = parse_transcript(source_bytes.decode("utf-8"))
                entries = data.get("entries", [])
                if not entries:
                    raise ValueError("该记录文件中没有有效的语音条目，无法生成纪要")
                summary = generate_summary(entries, job.service, mode=job.mode,
                                           meta=data.get("meta", {}))
                summary["cache_key"] = job.cache_key
                self._loop.post(self._finish, job, summary, None)
            except Exception as error:
                log.warning("纪要生成失败 %s (%s)", job.record_id, type(error).__name__)
                self._loop.post(self._finish, job, None, error)

    def _finish(self, job: _SummaryJob, summary: dict | None, error: Exception | None):
        """在 loop 线程判定结果是否仍然有效，再写缓存并广播终态。"""
        # 取消/删除/被新提交替换的任务，晚到结果直接丢弃
        if job.cancelled.is_set() or self._jobs.get((job.record_id, job.mode)) is not job:
            return
        if error is None:
            try:
                save_summary(job.path, summary)
            except OSError as write_error:
                error = write_error
            else:
                job.status = "done"
                job.summary = summary
        if error is not None:
            job.status = "error"
            job.error = str(error) or type(error).__name__
        self._emit_summary(job)

    def summary_status(self, record_id: str | None = None, name: str | None = None,
                       mode: str = "minutes") -> dict:
        """切页/重开时取回纪要状态：idle | queued | running | done | error | cancelled。"""
        rid = self._record_id(record_id or name or "")
        if not rid or rid == ".jsonl":
            raise ValueError("缺少记录标识")
        job = self._jobs.get((rid, mode))
        if job is not None and job.status in ("queued", "running"):
            return {"record_id": rid, "mode": mode, "status": job.status}
        if job is not None and job.status == "error":
            return {"record_id": rid, "mode": mode, "status": "error",
                    "error": job.error}
        if job is not None and job.status == "cancelled":
            return {"record_id": rid, "mode": mode, "status": "cancelled"}
        # 终态/无任务都要按当前内容与配置重新校验缓存键：
        # 换模型、换端点或源文件续写后，旧的 done 不能冒充有效摘要
        file = self._resolve_file(rid)
        cfg = self._config_provider()
        service = SummaryService.from_config(
            cfg.translate, getattr(cfg.record, "summary_max_chars", None))
        cache_key = summary_cache_key(file.read_bytes(), mode, service)
        if job is not None and job.status == "done" and job.cache_key == cache_key:
            return {"record_id": rid, "mode": mode, "status": "done",
                    "summary": job.summary}
        existing = load_summary(file)
        if existing and existing.get("cache_key") == cache_key:
            return {"record_id": rid, "mode": mode, "status": "done", "summary": existing}
        return {"record_id": rid, "mode": mode, "status": "idle"}

    def summary_cancel(self, record_id: str | None = None, name: str | None = None,
                       mode: str = "minutes") -> dict:
        """标记任务失效；不承诺撤回已发出的 HTTP 请求，晚到结果直接丢弃。"""
        rid = self._record_id(record_id or name or "")
        if not rid or rid == ".jsonl":
            raise ValueError("缺少记录标识")
        job = self._jobs.get((rid, mode))
        if job is None or job.status not in ("queued", "running"):
            return {"record_id": rid, "mode": mode, "status": "idle"}
        job.cancelled.set()
        job.status = "cancelled"
        self._emit_summary(job)
        return {"record_id": rid, "mode": mode, "status": "cancelled"}

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
