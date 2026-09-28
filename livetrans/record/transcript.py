"""Append-only JSONL transcripts, one file per recording.

Every line is a self-contained JSON object. A translation arrives as its own
line keyed by ``seq`` because workers finish out of order, and a failed
translation never arrives at all. A crash loses at most the line being written.

    {"type": "session", "version": 1, "t": ..., "source": ..., ...}
    {"type": "started", "t": ..., "device": ..., "model": ...}
    {"type": "utterance", "seq": 1, "start": ..., "end": ..., "language": "en", "text": ...}
    {"type": "translation", "seq": 1, "text": ...}
    {"type": "paused", "t": ...} / {"type": "resumed", "t": ...}
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from ..config import config_dir
from ..events import Translation, Utterance

log = logging.getLogger(__name__)

FORMAT_VERSION = 1


def records_dir() -> Path:
    return config_dir() / "records"


class Recorder:
    """One open transcript at a time, shared by consecutive engine sessions.

    Thread-safe: utterances come from recognition, translations from the
    translation workers and pause marks from the GUI thread. A failed write
    raises ``OSError`` once and leaves the recorder closed.
    """

    def __init__(self, directory: Path | None = None, clock=time.time):
        self._directory = directory
        self._clock = clock
        self._lock = threading.Lock()
        self._file = None
        self._path: Path | None = None
        self._utterances = 0

    @property
    def active(self) -> bool:
        return self._file is not None

    @property
    def path(self) -> Path | None:
        return self._path

    def open(self, meta: dict) -> Path:
        with self._lock:
            if self._file is None:
                directory = self._directory or records_dir()
                directory.mkdir(parents=True, exist_ok=True)
                stem = datetime.fromtimestamp(self._clock()).strftime("%Y%m%d-%H%M%S")
                for suffix in ("", *(f"-{n}" for n in range(2, 100))):
                    path = directory / f"{stem}{suffix}.jsonl"
                    try:
                        self._file = open(path, "x", encoding="utf-8", newline="\n")
                    except FileExistsError:
                        continue
                    break
                else:
                    raise FileExistsError(stem)
                self._path, self._utterances = path, 0
                self._write_locked(dict(type="session", version=FORMAT_VERSION,
                                        t=self._now(), **meta))
            return self._path

    def utterance(self, u: Utterance):
        self._write(dict(type="utterance", seq=u.seq, start=round(u.started_at, 3),
                         end=round(u.ended_at, 3), language=u.language, text=u.text),
                    utterance=True)

    def translation(self, t: Translation):
        self._write(dict(type="translation", seq=t.seq, text=t.text))

    def mark(self, kind: str, **data):
        self._write(dict(type=kind, t=self._now(), **data))

    def close(self):
        """Finish the current file; a file without any speech is removed."""
        with self._lock:
            file, path, empty = self._file, self._path, self._utterances == 0
            self._file = self._path = None
            if file is None:
                return
            try:
                file.close()
                if empty:
                    path.unlink()
            except OSError as error:
                log.warning("记录关闭失败 (%s)", type(error).__name__)

    def _now(self):
        return round(self._clock(), 3)

    def _write(self, record: dict, utterance=False):
        with self._lock:
            if self._file is not None:
                self._write_locked(record)
                self._utterances += utterance

    def _write_locked(self, record: dict):
        try:
            self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._file.flush()
        except OSError:
            file, self._file, self._path = self._file, None, None
            try:
                file.close()
            except OSError:
                pass
            raise


def load_transcript(path: Path) -> dict:
    """Merge a transcript into ``{"meta", "entries", "marks"}`` ordered by ``seq``.

    Entries whose translation never arrived have ``translation`` set to ``""``.
    An unreadable trailing line (for example after a crash) is skipped.
    """
    meta, entries, translations, marks = {}, {}, {}, []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            kind = record.get("type")
            seq = record.get("seq")
            if kind == "session":
                meta = record
            elif kind == "utterance" and isinstance(seq, int):
                entries[seq] = record
            elif kind == "translation" and isinstance(seq, int):
                translations[seq] = str(record.get("text", ""))
            elif kind not in ("utterance", "translation"):
                marks.append(record)
    return {
        "meta": meta,
        "entries": [dict(entries[seq], translation=translations.get(seq, ""))
                    for seq in sorted(entries)],
        "marks": marks,
    }
