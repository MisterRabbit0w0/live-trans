"""ASR 后端抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class AsrResult:
    language: str  # 检测/指定的语言代码，如 en / ja
    text: str


class AsrEngine(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray, language: str | None = None) -> AsrResult:
        """audio: float32 mono @16kHz。language=None 表示自动检测。"""

    def close(self) -> None:  # noqa: B027
        pass
