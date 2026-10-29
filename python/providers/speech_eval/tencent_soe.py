"""Tencent Speech Evaluation (SOE) adapter.

Tencent's ``TransmitOralProcess`` response is intentionally parsed only here;
upper layers receive :class:`PronunciationMetrics` regardless of provider.
"""

from __future__ import annotations

import base64
import math
import os
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from audio_encoding import AudioEncodingError, pcm_to_wav, to_pcm16
from providers.asr.base import TranscriptResult
from providers.tencent_cloud import TencentCloudClient, TencentCloudError

from .base import (
    PronunciationMetrics,
    PronunciationWord,
    SpeechEvaluationMode,
    SpeechEvaluationProvider,
    SpeechEvaluationProviderError,
)

DEFAULT_ENDPOINT = "https://soe.tencentcloudapi.com"
DEFAULT_REGION = "ap-guangzhou"
DEFAULT_TIMEOUT = 120.0
SERVICE = "soe"
VERSION = "2018-07-24"
ACTION = "TransmitOralProcessWithInit"


class TencentSOEError(SpeechEvaluationProviderError):
    """Raised when Tencent SOE fails or returns an unusable result."""


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _score(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    # Tencent returns 0-100 scores. Clamp malformed provider values before
    # exposing them to scoring or UI code.
    return round(max(0.0, min(100.0, number)), 1)


def _ratio_score(value: Any) -> float | None:
    """Tencent fluency/completion are fractions; -1 means unavailable."""
    number = _number(value)
    if number is None or not 0 <= number <= 1:
        return None
    return round(number * 100, 1)


def _word_time(item: dict[str, Any], *, end: bool = False) -> float | None:
    ms_names = ("EndMs", "end_ms", "EndTime", "MemEndTime") if end else ("StartMs", "start_ms", "StartTime", "MemBeginTime")
    for name in ms_names:
        if item.get(name) is not None:
            value = _number(item[name])
            return value / 1000 if value is not None and value >= 0 else None
    value = _number(item.get("end" if end else "start"))
    return value if value is not None and value >= 0 else None


def _first(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        if payload.get(name) is not None:
            return payload[name]
    return None


def _parse_word(item: dict[str, Any]) -> PronunciationWord | None:
    word = str(_first(item, "Word", "word", "Text", "text") or "").strip()
    if not word:
        return None
    score = _score(
        _first(item, "PronAccuracy", "PronunciationAccuracy", "Score", "score")
    )
    raw_status = str(_first(item, "Status", "status") or "").strip().lower()
    status = {
        "ok": "ok",
        "correct": "ok",
        "right": "ok",
        "replacement": "needs_review",
        "wrong": "needs_review",
        "missing": "missing",
    }.get(raw_status)
    if status is None:
        status = "ok" if score is None or score >= 80 else "needs_review"
    start = _word_time(item)
    end = _word_time(item, end=True)
    return PronunciationWord(word=word, score=score, status=status, start=start, end=end)


def _parse_result(
    response: dict[str, Any], *, provider: str = "tencent", model: str = "tencent-soe"
) -> PronunciationMetrics:
    envelope = response.get("Response", response)
    if not isinstance(envelope, dict):
        raise TencentSOEError("Tencent SOE returned an invalid response.")
    data = envelope.get("Data") if isinstance(envelope.get("Data"), dict) else envelope
    accuracy = _score(
        _first(data, "PronAccuracy", "PronunciationAccuracy", "pronunciation_accuracy")
    )
    fluency = _ratio_score(
        _first(data, "PronFluency", "PronunciationFluency", "pronunciation_fluency")
    )
    completeness = _ratio_score(
        _first(data, "PronCompletion", "Completeness", "completeness")
    )
    raw_words: list[Any] = []
    for key in ("Words", "words", "WordInfos", "word_infos", "SentenceInfoSet"):
        value = data.get(key)
        if isinstance(value, list):
            raw_words.extend(value)
    words: list[PronunciationWord] = []
    for item in raw_words:
        if not isinstance(item, dict):
            continue
        nested = item.get("Words") or item.get("words") or item.get("WordInfos")
        candidates = nested if isinstance(nested, list) else [item]
        for candidate in candidates:
            if isinstance(candidate, dict):
                parsed = _parse_word(candidate)
                if parsed:
                    words.append(parsed)
    word_scores = [word.score for word in words if word.score is not None]
    if accuracy is None and word_scores:
        accuracy = round(sum(word_scores) / len(word_scores), 1)
    return PronunciationMetrics(
        pronunciation_accuracy=accuracy,
        pronunciation_fluency=fluency,
        completeness=completeness,
        words=words,
        provider=provider,
        model=model,
    )


class TencentSOEProvider(SpeechEvaluationProvider):
    provider_name = "tencent"

    def __init__(
        self,
        *,
        secret_id: str | None = None,
        secret_key: str | None = None,
        region: str = DEFAULT_REGION,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = DEFAULT_TIMEOUT,
        voice_file_type: int = 1,
        voice_encode_type: int = 1,
        eval_mode_free: int = 3,
        eval_mode_reference: int = 1,
        score_coeff: float = 4.0,
    ) -> None:
        self.secret_id = (secret_id or os.getenv("TENCENT_SECRET_ID") or "").strip()
        self.secret_key = (secret_key or os.getenv("TENCENT_SECRET_KEY") or "").strip()
        self.region = (region or os.getenv("TENCENT_REGION") or DEFAULT_REGION).strip()
        self.endpoint = (endpoint or os.getenv("TENCENT_SOE_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")
        self.timeout = max(1.0, float(timeout))
        self.voice_file_type = voice_file_type
        self.voice_encode_type = voice_encode_type
        self.eval_mode_free = eval_mode_free
        self.eval_mode_reference = eval_mode_reference
        self.score_coeff = score_coeff
        self.client = TencentCloudClient(
            secret_id=self.secret_id,
            secret_key=self.secret_key,
            region=self.region,
            endpoint=self.endpoint,
            service=SERVICE,
            version=VERSION,
            timeout=self.timeout,
        )

    @classmethod
    def from_environment(cls) -> "TencentSOEProvider":
        return cls(
            secret_id=os.getenv("TENCENT_SECRET_ID"),
            secret_key=os.getenv("TENCENT_SECRET_KEY"),
            region=os.getenv("TENCENT_REGION", DEFAULT_REGION),
            endpoint=os.getenv("TENCENT_SOE_ENDPOINT", DEFAULT_ENDPOINT),
            timeout=float(os.getenv("TENCENT_SOE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT)),
            voice_file_type=int(os.getenv("TENCENT_SOE_VOICE_FILE_TYPE", "1")),
            voice_encode_type=int(os.getenv("TENCENT_SOE_VOICE_ENCODE_TYPE", "1")),
            eval_mode_free=int(os.getenv("TENCENT_SOE_EVAL_MODE_FREE", "3")),
            eval_mode_reference=int(os.getenv("TENCENT_SOE_EVAL_MODE_REFERENCE", "1")),
            score_coeff=float(os.getenv("TENCENT_SOE_SCORE_COEFF", "4.0")),
        )

    def _request(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.client.request(ACTION, body, timeout=self.timeout)
        except TencentCloudError as exc:
            raise TencentSOEError(str(exc)) from exc

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
        del filename, content_type, audio_url
        if isinstance(audio, (str, Path)):
            audio_bytes = Path(audio).read_bytes()
        elif isinstance(audio, bytes):
            audio_bytes = audio
        else:
            audio_bytes = audio.read()
        if not audio_bytes:
            raise TencentSOEError("Tencent SOE cannot evaluate empty audio.")
        if mode == "reference" and not (reference_text or "").strip():
            raise TencentSOEError("Reference text is required for reference evaluation.")
        if self.voice_file_type not in (1, 2) or self.voice_encode_type != 1:
            raise TencentSOEError("Tencent SOE conversion supports VoiceFileType 1/2 and PCM encoding 1.")
        if not 1 <= self.score_coeff <= 4:
            raise TencentSOEError("Tencent SOE ScoreCoeff must be between 1 and 4.")
        try:
            pcm = to_pcm16(audio_bytes)
        except AudioEncodingError as exc:
            raise TencentSOEError(str(exc)) from exc
        audio_bytes = pcm_to_wav(pcm) if self.voice_file_type == 2 else pcm

        body: dict[str, Any] = {
            "VoiceFileType": self.voice_file_type,
            "VoiceEncodeType": self.voice_encode_type,
            "SeqId": 1,
            "IsEnd": 1,
            "UserVoiceData": base64.b64encode(audio_bytes).decode("ascii"),
            "SessionId": uuid.uuid4().hex,
            "WorkMode": 1,
            "EvalMode": self.eval_mode_reference if mode == "reference" else self.eval_mode_free,
            "ScoreCoeff": self.score_coeff,
            "ServerType": 0,
            "TextMode": 0,
            "SentenceInfoEnabled": 1,
        }
        if mode == "reference":
            body["RefText"] = (reference_text or "").strip()
            if not body["RefText"]:
                raise TencentSOEError("Reference text is required for reference evaluation.")
        else:
            # Free-speaking mode does not use a reference sentence. Transcript
            # remains available to local callers for evidence and word mapping.
            del transcript
        response = self._request(body)
        return _parse_result(response, model="tencent:soe")

