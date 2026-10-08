"""Build the configured ASR adapter without leaking vendors into API code."""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO

from assembly_transcribe import assembly_transcribe, assembly_transcribe_url
from whisper_transcribe import whisper_transcribe

from .base import ASRProvider, ASRProviderError, TranscriptResult
from .mock_asr import MockASRProvider
from .tencent_asr import TencentASRProvider


class LegacyASRProvider(ASRProvider):
    """Compatibility adapter for v2.1 AssemblyAI and Whisper integrations."""

    def __init__(self, name: str, settings: Any) -> None:
        self.provider_name = name
        self.settings = settings

    def transcribe(
        self,
        audio: str | Path | bytes | BinaryIO,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        language: str = "en",
        audio_url: str | None = None,
    ) -> TranscriptResult:
        if self.provider_name == "assemblyai":
            models = [
                item.strip()
                for item in self.settings.assemblyai_speech_models.split(",")
                if item.strip()
            ] or ["universal-2"]
            if audio_url:
                return assembly_transcribe_url(
                    audio_url,
                    language_code=language,
                    api_key=self.settings.assemblyai_api_key,
                    base_url=self.settings.assemblyai_base_url,
                    speech_models=models,
                )
            return assembly_transcribe(
                audio,
                filename=filename,
                content_type=content_type,
                language_code=language,
                api_key=self.settings.assemblyai_api_key,
                base_url=self.settings.assemblyai_base_url,
                speech_models=models,
            )

        return whisper_transcribe(
            audio,
            filename=filename,
            content_type=content_type,
            language=language,
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
            model=self.settings.whisper_model,
        )


def resolve_provider_name(settings: Any) -> str:
    requested = (settings.asr_provider or "auto").strip().lower()
    if requested != "auto":
        return requested
    if (settings.tencent_secret_id or "").strip() and (settings.tencent_secret_key or "").strip():
        return "tencent"
    if (settings.assemblyai_api_key or "").strip():
        return "assemblyai"
    if (settings.openai_api_key or "").strip():
        return "whisper"
    return "none"


def is_provider_configured(settings: Any) -> bool:
    name = resolve_provider_name(settings)
    if name == "mock":
        return True
    if name == "tencent":
        return bool((settings.tencent_secret_id or "").strip() and (settings.tencent_secret_key or "").strip())
    if name == "assemblyai":
        return bool((settings.assemblyai_api_key or "").strip())
    if name == "whisper":
        return bool((settings.openai_api_key or "").strip())
    return False


def create_asr_provider(settings: Any) -> ASRProvider:
    name = resolve_provider_name(settings)
    if name == "mock":
        return MockASRProvider(settings.mock_asr_transcript, settings.mock_asr_duration_seconds)
    if name == "tencent":
        return TencentASRProvider(
            secret_id=settings.tencent_secret_id,
            secret_key=settings.tencent_secret_key,
            region=settings.tencent_region,
            endpoint=settings.tencent_asr_endpoint,
            engine_model_type=settings.tencent_asr_engine_model_type,
            timeout=settings.tencent_asr_timeout_seconds,
            poll_interval=settings.tencent_asr_poll_interval_seconds,
        )
    if name in {"assemblyai", "whisper"}:
        return LegacyASRProvider(name, settings)
    raise ASRProviderError(
        "No ASR provider is configured. Set ASR_PROVIDER=mock for local development, "
        "or configure Tencent/AssemblyAI/Whisper credentials."
    )
