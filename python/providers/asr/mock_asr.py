"""Deterministic local ASR provider for development and offline tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

from .base import ASRProvider, TranscriptResult, TranscriptWord


DEFAULT_MOCK_TRANSCRIPT = (
    "I think this is a useful practice response for local development."
)


class MockASRProvider(ASRProvider):
    """Return stable transcript data without reading or uploading audio."""

    provider_name = "mock"

    def __init__(self, transcript: str | None = None, duration: float = 6.0) -> None:
        self.transcript = (transcript or DEFAULT_MOCK_TRANSCRIPT).strip()
        self.duration = max(0.1, float(duration))

    @classmethod
    def from_environment(cls) -> "MockASRProvider":
        raw_duration = os.getenv("MOCK_ASR_DURATION_SECONDS", "6")
        try:
            duration = float(raw_duration)
        except (TypeError, ValueError):
            duration = 6.0
        return cls(os.getenv("MOCK_ASR_TRANSCRIPT") or None, duration)

    def transcribe(
        self,
        audio: str | Path | bytes | BinaryIO,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        language: str = "en",
        audio_url: str | None = None,
    ) -> TranscriptResult:
        del audio, filename, content_type, audio_url
        tokens = self.transcript.split()
        step = self.duration / max(1, len(tokens))
        words = [
            TranscriptWord(
                word=token,
                start=round(index * step, 3),
                end=round((index + 1) * step, 3),
                confidence=1.0,
            )
            for index, token in enumerate(tokens)
        ]
        return TranscriptResult(
            transcript=self.transcript,
            words=words,
            language=language,
            duration=self.duration,
            model="mock-asr-v1",
        )
