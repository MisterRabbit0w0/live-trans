"""翻译后端抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

# 上下文历史：(源语言代码, 原文, 译文) 的列表，按时间从旧到新排列。
# 实现可取用末尾若干条作为对话上下文，提升代词指代与术语一致性。
TranslationHistory = Sequence[tuple[str, str, str]]


class Translator(ABC):
    @abstractmethod
    def translate(
        self,
        text: str,
        source_language: str = "",
        history: TranslationHistory | None = None,
    ) -> str:
        """把 text 翻译成目标语言，返回译文。失败时抛异常。

        history 为可选的上下文历史；不支持的实现可忽略该参数。
        """

    def close(self) -> None:  # noqa: B027
        pass
