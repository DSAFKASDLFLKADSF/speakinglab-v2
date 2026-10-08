"""Deterministic speech evaluation for local development and tests."""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

from providers.asr.base import TranscriptResult

from .base import (
    PronunciationMetrics,
    PronunciationWord,
    SpeechEvaluationMode,
    SpeechEvaluationProvider,
)


def _token(value: str) -> str:
    return re.sub(r"[^a-z0-9']", "", value.lower())


class MockSpeechEvaluationProvider(SpeechEvaluationProvider):
    """Return stable scores while preserving task-specific semantics."""

    provider_name = "mock"

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
        del audio, filename, content_type, audio_url
        if mode == "reference":
            return self._reference_result(transcript, reference_text or "")
        words = [
            PronunciationWord(
                word=word.word,
                score=86.0,
                status="ok",
                start=word.start,
                end=word.end,
            )
            for word in transcript.words
        ]
        return PronunciationMetrics(
            pronunciation_accuracy=86.0,
            pronunciation_fluency=88.0,
            completeness=None,
            words=words,
            provider=self.provider_name,
            model="mock-speech-eval-v1",
        )

    def _reference_result(
        self, transcript: TranscriptResult, reference_text: str
    ) -> PronunciationMetrics:
        reference_items = [
            (word, _token(word))
            for word in reference_text.split()
            if _token(word)
        ]
        reference_words = [token for _, token in reference_items]
        transcript_words = [_token(word.word) for word in transcript.words if _token(word.word)]
        results: list[PronunciationWord] = []
        for index, expected in enumerate(reference_words):
            actual = transcript_words[index] if index < len(transcript_words) else ""
            score = 100.0 if actual == expected else (60.0 if actual else 0.0)
            results.append(
                PronunciationWord(
                    word=reference_items[index][0],
                    score=score,
                    status=(
                        "ok"
                        if score >= 80
                        else "needs_review"
                        if actual
                        else "missing"
                    ),
                )
            )
        if not results:
            accuracy = 0.0
            completeness = 0.0
        else:
            accuracy = round(sum(word.score or 0 for word in results) / len(results), 1)
            completeness = round(
                min(len(transcript_words), len(reference_words))
                / len(reference_words)
                * 100,
                1,
            )
        return PronunciationMetrics(
            pronunciation_accuracy=accuracy,
            pronunciation_fluency=round(max(0.0, min(100.0, accuracy + 4)), 1),
            completeness=completeness,
            words=results,
            provider=self.provider_name,
            model="mock-speech-eval-v1",
        )
