"""Common speech-to-text contracts.

Business logic consumes this normalized result instead of a vendor response.
The legacy ``transcript``/``duration`` names remain available for the v2.1
callers; ``text``/``duration_seconds`` are the provider-neutral names.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class ASRProviderError(Exception):
    """Base error for a speech-to-text provider failure."""


@dataclass(frozen=True)
class TranscriptWord:
    word: str
    start: float | None = None
    end: float | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class TranscriptResult:
    """Normalized transcript returned by every ASR adapter."""

    transcript: str
    words: list[TranscriptWord]
    language: str | None = None
    duration: float | None = None
    model: str = "unknown"

    @property
    def text(self) -> str:
        return self.transcript

    @property
    def duration_seconds(self) -> float | None:
        return self.duration


class ASRProvider(ABC):
    """Interface implemented by ASR vendors and the local test provider."""

    provider_name = "unknown"

    @abstractmethod
    def transcribe(
        self,
        audio: str | Path | bytes | BinaryIO,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        language: str = "en",
        audio_url: str | None = None,
    ) -> TranscriptResult:
        """Transcribe an audio payload or an optionally supplied public URL."""

