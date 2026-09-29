"""Incremental subtitle data shared by the control center and overlay."""
from __future__ import annotations


class SubtitleBuffer:
    """A bounded list of bilingual rows; ``on_change`` runs after mutations."""

    def __init__(self, limit: int = 3, on_change=lambda: None):
        self.on_change = on_change
        self._rows: list[dict] = []
        self._limit = max(1, min(10, limit))

    def add(self, entry_id, original: str, language: str) -> None:
        self._rows.append({"id": entry_id, "original": original,
                           "language": language, "translation": ""})
        self._evict()
        self.on_change()

    def translate(self, entry_id, translation: str) -> None:
        for entry in self._rows:
            if entry["id"] == entry_id:
                entry["translation"] = translation
                self.on_change()
                break

    def set_limit(self, limit: int) -> None:
        limit = max(1, min(10, limit))
        if limit == self._limit and len(self._rows) <= limit:
            return
        self._limit = limit
        self._evict()
        self.on_change()

    def _evict(self) -> None:
        del self._rows[: max(0, len(self._rows) - self._limit)]

    def clear(self) -> None:
        if self._rows:
            self._rows.clear()
            self.on_change()

    def rows(self) -> list[dict]:
        return [dict(row) for row in self._rows]
