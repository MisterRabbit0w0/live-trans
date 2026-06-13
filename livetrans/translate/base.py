"""翻译后端抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Translator(ABC):
    @abstractmethod
    def translate(self, text: str, source_language: str = "") -> str:
        """把 text 翻译成目标语言，返回译文。失败时抛异常。"""

    def close(self) -> None:  # noqa: B027
        pass
