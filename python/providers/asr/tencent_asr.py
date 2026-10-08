"""Tencent Cloud ASR adapter using the signed v3 HTTP API.

Only this module knows Tencent request/response shapes.  The rest of the
service receives the normalized :class:`TranscriptResult` contract.
"""

from __future__ import annotations

import base64
import logging
import math
import os
import time
from pathlib import Path
from typing import Any, BinaryIO

from .base import ASRProvider, ASRProviderError, TranscriptResult, TranscriptWord
from ..tencent_cloud import (
    TencentCloudClient,
    TencentCloudError,
    _hash as _cloud_hash,
    _hmac as _cloud_hmac,
    requests,  # Re-exported for compatibility with existing request tests.
    tc3_authorization,
)

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://asr.tencentcloudapi.com"
DEFAULT_REGION = "ap-guangzhou"
DEFAULT_ENGINE_MODEL_TYPE = "16k_en"
DEFAULT_TIMEOUT = 120.0
SERVICE = "asr"
VERSION = "2019-06-14"


class TencentASRError(ASRProviderError):
    """Raised when Tencent ASR cannot create, poll, or parse a task."""


def _hash(value: str) -> str:
    """Compatibility wrapper for the shared Tencent signing helper."""

    return _cloud_hash(value)


def _sign(secret_key: str, message: str) -> bytes:
    """Compatibility wrapper for the shared Tencent signing helper."""

    return _cloud_hmac(secret_key, message)


def _authorization(
    *,
    secret_id: str,
    secret_key: str,
    region: str,
    host: str,
    action: str,
    payload: str,
    timestamp: int,
) -> str:
    del action
    return tc3_authorization(
        secret_id=secret_id,
        secret_key=secret_key,
        region=region,
        service=SERVICE,
        host=host,
        payload=payload,
        timestamp=timestamp,
    )


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _first(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload and payload[name] is not None:
            return payload[name]
    return None


def _word_from_item(item: dict[str, Any]) -> TranscriptWord | None:
    text = str(_first(item, "Word", "word", "Text", "text", "FinalSentence") or "").strip()
    if not text:
        return None
    start = _number(_first(item, "StartMs", "start_ms", "StartTime", "start"))
    end = _number(_first(item, "EndMs", "end_ms", "EndTime", "end"))
    # Tencent uses milliseconds for its ASR timing fields.  Accept seconds for
    # test doubles and future API variants when values are already fractional.
    if start is not None and (start > 100 or float(start).is_integer()):
        start /= 1000
    if end is not None and (end > 100 or float(end).is_integer()):
        end /= 1000
    confidence = _number(_first(item, "Confidence", "confidence", "Pronunciation"))
    if confidence is not None and confidence > 1:
        confidence /= 100
    return TranscriptWord(word=text, start=start, end=end, confidence=confidence)


def _parse_words(data: dict[str, Any], transcript: str) -> list[TranscriptWord]:
    candidates: list[Any] = []
    for key in ("Words", "words", "WordList", "word_list", "ResultDetail", "result_detail"):
        value = data.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    words: list[TranscriptWord] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        # ResultDetail can contain a nested Words list.
        nested = item.get("Words") or item.get("words")
        if isinstance(nested, list):
            for nested_item in nested:
                if isinstance(nested_item, dict):
                    word = _word_from_item(nested_item)
                    if word:
                        words.append(word)
            continue
        word = _word_from_item(item)
        if word:
            words.append(word)
    if words:
        return words
    return [TranscriptWord(word=token) for token in transcript.split() if token]


def _parse_result(response: dict[str, Any], *, language: str, model: str) -> TranscriptResult:
    data = response.get("Response", response)
    if not isinstance(data, dict):
        raise TencentASRError("Tencent ASR returned an invalid response.")
    result_data = data.get("Data") if isinstance(data.get("Data"), dict) else data
    transcript = str(
        _first(result_data, "Result", "result", "Text", "text", "FlashResult") or ""
    ).strip()
    if not transcript:
        raise TencentASRError("Tencent ASR returned an empty transcript.")
    words = _parse_words(result_data, transcript)
    duration = _number(_first(result_data, "AudioDuration", "audio_duration", "Duration", "duration"))
    if duration is None:
        timed_ends = [word.end for word in words if word.end is not None]
        duration = max(timed_ends) if timed_ends else None
    return TranscriptResult(
        transcript=transcript,
        words=words,
        language=str(_first(result_data, "Language", "language") or language),
        duration=duration,
        model=model,
    )


class TencentASRProvider(ASRProvider):
    provider_name = "tencent"

    def __init__(
        self,
        *,
        secret_id: str | None = None,
        secret_key: str | None = None,
        region: str = DEFAULT_REGION,
        endpoint: str = DEFAULT_ENDPOINT,
        engine_model_type: str = DEFAULT_ENGINE_MODEL_TYPE,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = 1.0,
    ) -> None:
        self.secret_id = (secret_id or os.getenv("TENCENT_SECRET_ID") or "").strip()
        self.secret_key = (secret_key or os.getenv("TENCENT_SECRET_KEY") or "").strip()
        self.region = (region or os.getenv("TENCENT_REGION") or DEFAULT_REGION).strip()
        self.endpoint = (endpoint or os.getenv("TENCENT_ASR_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")
        self.engine_model_type = (engine_model_type or os.getenv("TENCENT_ASR_ENGINE_MODEL_TYPE") or DEFAULT_ENGINE_MODEL_TYPE).strip()
        self.timeout = max(1.0, float(timeout))
        self.poll_interval = max(0.05, float(poll_interval))
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
    def from_environment(cls) -> "TencentASRProvider":
        return cls(
            secret_id=os.getenv("TENCENT_SECRET_ID"),
            secret_key=os.getenv("TENCENT_SECRET_KEY"),
            region=os.getenv("TENCENT_REGION", DEFAULT_REGION),
            endpoint=os.getenv("TENCENT_ASR_ENDPOINT", DEFAULT_ENDPOINT),
            engine_model_type=os.getenv("TENCENT_ASR_ENGINE_MODEL_TYPE", DEFAULT_ENGINE_MODEL_TYPE),
            timeout=float(os.getenv("TENCENT_ASR_TIMEOUT_SECONDS", DEFAULT_TIMEOUT)),
            poll_interval=float(os.getenv("TENCENT_ASR_POLL_INTERVAL_SECONDS", "1")),
        )

    def _request(self, action: str, body: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        try:
            return self.client.request(action, body, timeout=timeout)
        except TencentCloudError as exc:
            raise TencentASRError(str(exc)) from exc

    def _create_task(self, audio: bytes, *, audio_url: str | None, language: str) -> str:
        body: dict[str, Any] = {
            "EngineModelType": self.engine_model_type,
            "ChannelNum": 1,
            "ResTextFormat": 0,
            "FilterDirty": 0,
            "FilterModal": 0,
            "FilterPunc": 0,
        }
        if audio_url:
            body.update({"SourceType": 0, "Url": audio_url})
        else:
            body.update({"SourceType": 1, "Data": base64.b64encode(audio).decode("ascii"), "DataLen": len(audio)})
        result = self._request("CreateRecTask", body, timeout=self.timeout)
        response = result.get("Response", result)
        task_id = response.get("Data", {}).get("TaskId") if isinstance(response.get("Data"), dict) else response.get("TaskId")
        if not task_id:
            raise TencentASRError("Tencent ASR did not return a task id.")
        del language
        return str(task_id)

    def _poll_task(self, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TencentASRError("Tencent ASR transcription timed out.")
            response = self._request("DescribeTaskStatus", {"TaskId": int(task_id) if task_id.isdigit() else task_id}, timeout=min(30.0, remaining))
            data = response.get("Response", response)
            status_data = data.get("Data") if isinstance(data, dict) and isinstance(data.get("Data"), dict) else data
            status = str(_first(status_data, "StatusStr", "status", "Status") or "").lower()
            if status in {"success", "completed", "complete", "1"} or status_data.get("Status") == 1:
                return response
            if status in {"failed", "error", "2", "3"} or status_data.get("Status") in {2, 3}:
                raise TencentASRError(str(_first(status_data, "ErrorMsg", "error", "Message") or "Tencent ASR task failed."))
            time.sleep(min(self.poll_interval, max(0.05, remaining)))

    def transcribe(
        self,
        audio: str | Path | bytes | BinaryIO,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        language: str = "en",
        audio_url: str | None = None,
    ) -> TranscriptResult:
        del filename, content_type
        if isinstance(audio, (str, Path)):
            audio_bytes = Path(audio).read_bytes()
        elif isinstance(audio, bytes):
            audio_bytes = audio
        else:
            audio_bytes = audio.read()
        task_id = self._create_task(audio_bytes, audio_url=audio_url, language=language)
        response = self._poll_task(task_id)
        return _parse_result(response, language=language, model=f"tencent:{self.engine_model_type}")
