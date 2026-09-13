"""Incremental subtitle data shared by the control center and overlay."""
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class SubtitleModel(QAbstractListModel):
    ROLES = {
        Qt.ItemDataRole.UserRole + 1: b"original",
        Qt.ItemDataRole.UserRole + 2: b"translation",
        Qt.ItemDataRole.UserRole + 3: b"language",
    }

    def __init__(self, limit=3, parent=None):
        super().__init__(parent)
        self._rows = []
        self._limit = limit

    def roleNames(self):
        return self.ROLES

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = self.ROLES.get(role)
        return self._rows[index.row()].get(name.decode()) if name else None

    def add(self, entry_id, original, language):
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append(dict(id=entry_id, original=original, language=language, translation=""))
        self.endInsertRows()
        self.set_limit(self._limit)

    def translate(self, entry_id, translation):
        for row, entry in enumerate(self._rows):
            if entry["id"] == entry_id:
                entry["translation"] = translation
                index = self.index(row)
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.UserRole + 2])
                break

    def set_limit(self, limit):
        self._limit = max(1, min(10, limit))
        remove = len(self._rows) - self._limit
        if remove > 0:
            self.beginRemoveRows(QModelIndex(), 0, remove - 1)
            del self._rows[:remove]
            self.endRemoveRows()

    def clear(self):
        if self._rows:
            self.beginResetModel()
            self._rows.clear()
            self.endResetModel()
