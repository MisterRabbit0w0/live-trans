"""Data passed between transcription, translation and recording stages."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Utterance:
    seq: int  # numbered by the session; stays unique across engine restarts
    text: str
    language: str
    started_at: float  # wall clock, seconds
    ended_at: float


@dataclass(frozen=True)
class Translation:
    seq: int
    text: str
