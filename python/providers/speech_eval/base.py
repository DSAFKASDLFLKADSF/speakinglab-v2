"""Provider-neutral speech evaluation contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

from providers.asr.base import TranscriptResult

SpeechEvaluationMode = Literal["free_speaking", "reference"]


class SpeechEvaluationProviderError(Exception):
    """Base error raised by a speech evaluation provider."""


@dataclass(frozen=True)
class PronunciationWord:
    """Normalized word-level speech evaluation evidence."""

    word: str
    score: float | None = None
    status: str = "unknown"
    start: float | None = None
    end: float | None = None

    def to_dict(self) -> dict[str, str | float | None]:
        return {
            "word": self.word,
            "score": self.score,
            "status": self.status,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True)
class PronunciationMetrics:
    """Normalized pronunciation/fluency result exposed above provider code."""

    pronunciation_accuracy: float | None
    pronunciation_fluency: float | None
    completeness: float | None
    words: list[PronunciationWord]
    provider: str
    model: str

    def to_dict(self) -> dict[str, object]:
        return {
            "pronunciation_accuracy": self.pronunciation_accuracy,
            "pronunciation_fluency": self.pronunciation_fluency,
            "completeness": self.completeness,
            "words": [word.to_dict() for word in self.words],
            "provider": self.provider,
            "model": self.model,
        }


class SpeechEvaluationProvider(ABC):
    """Interface for free-speaking and reference-based speech evaluation."""

    provider_name = "unknown"

    @abstractmethod
    def evaluate(
        self,
        audio: str | Path | bytes | BinaryIO,
        *,
        transcript: TranscriptResult,
        mode: SpeechEvaluationMode,
        reference_text: str | None = None,
        filename: str | None = None,
        content_type: str | None = None,
        audio_url: str | None = None,
    ) -> PronunciationMetrics:
        """Evaluate pronunciation/fluency without exposing vendor response data."""

