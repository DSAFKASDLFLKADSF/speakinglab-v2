"""Speech-to-text provider adapters and normalized transcript models."""

from .base import ASRProvider, ASRProviderError, TranscriptResult, TranscriptWord
from .mock_asr import MockASRProvider
from .tencent_asr import TencentASRProvider, TencentASRError

__all__ = [
    "ASRProvider",
    "ASRProviderError",
    "MockASRProvider",
    "TencentASRError",
    "TencentASRProvider",
    "TranscriptResult",
    "TranscriptWord",
]
