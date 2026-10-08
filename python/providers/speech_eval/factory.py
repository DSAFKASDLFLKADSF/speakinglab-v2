"""Select the configured speech evaluation provider."""

from __future__ import annotations

from typing import Any

from .base import SpeechEvaluationProvider, SpeechEvaluationProviderError
from .mock_speech_eval import MockSpeechEvaluationProvider
from .tencent_soe import TencentSOEProvider


def resolve_speech_evaluation_provider_name(settings: Any) -> str:
    requested = (settings.speech_eval_provider or "none").strip().lower()
    if requested != "auto":
        return requested
    if (settings.tencent_secret_id or "").strip() and (settings.tencent_secret_key or "").strip():
        return "tencent"
    return "none"


def is_speech_evaluation_configured(settings: Any) -> bool:
    name = resolve_speech_evaluation_provider_name(settings)
    if name == "mock":
        return True
    if name == "tencent":
        return bool(
            (settings.tencent_secret_id or "").strip()
            and (settings.tencent_secret_key or "").strip()
        )
    return False


def create_speech_evaluation_provider(settings: Any) -> SpeechEvaluationProvider:
    name = resolve_speech_evaluation_provider_name(settings)
    if name == "mock":
        return MockSpeechEvaluationProvider()
    if name == "tencent":
        return TencentSOEProvider(
            secret_id=settings.tencent_secret_id,
            secret_key=settings.tencent_secret_key,
            region=settings.tencent_region,
            endpoint=settings.tencent_soe_endpoint,
            timeout=settings.tencent_soe_timeout_seconds,
            voice_file_type=settings.tencent_soe_voice_file_type,
            voice_encode_type=settings.tencent_soe_voice_encode_type,
            eval_mode_free=settings.tencent_soe_eval_mode_free,
            eval_mode_reference=settings.tencent_soe_eval_mode_reference,
        )
    raise SpeechEvaluationProviderError(
        "No speech evaluation provider is configured. Set "
        "SPEECH_EVAL_PROVIDER=mock for local development or configure Tencent SOE."
    )
