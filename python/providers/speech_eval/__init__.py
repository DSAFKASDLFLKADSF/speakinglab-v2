"""Normalized pronunciation and fluency evaluation providers."""

from .base import (
    SpeechEvaluationProvider,
    SpeechEvaluationProviderError,
    PronunciationMetrics,
    PronunciationWord,
)
from .factory import (
    create_speech_evaluation_provider,
    is_speech_evaluation_configured,
    resolve_speech_evaluation_provider_name,
)
from .mock_speech_eval import MockSpeechEvaluationProvider
from .tencent_soe import TencentSOEProvider, TencentSOEError

__all__ = [
    "MockSpeechEvaluationProvider",
    "PronunciationMetrics",
    "PronunciationWord",
    "SpeechEvaluationProvider",
    "SpeechEvaluationProviderError",
    "TencentSOEError",
    "TencentSOEProvider",
    "create_speech_evaluation_provider",
    "is_speech_evaluation_configured",
    "resolve_speech_evaluation_provider_name",
]
