"""Phase 2 speech-evaluation provider contract tests; no cloud calls."""

from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.asr.base import TranscriptResult, TranscriptWord
from providers.speech_eval.factory import (
    create_speech_evaluation_provider,
    resolve_speech_evaluation_provider_name,
)
from providers.speech_eval.mock_speech_eval import MockSpeechEvaluationProvider
from providers.speech_eval.tencent_soe import TencentSOEProvider, _parse_result


def _transcript() -> TranscriptResult:
    return TranscriptResult(
        transcript="Hello world",
        words=[
            TranscriptWord("Hello", start=0, end=0.5),
            TranscriptWord("world", start=0.6, end=1.0),
        ],
        duration=1.0,
        model="mock:transcript",
    )


class SpeechEvaluationContractTests(unittest.TestCase):
    def test_mock_free_speaking_is_deterministic(self):
        provider = MockSpeechEvaluationProvider()
        result = provider.evaluate(b"audio", transcript=_transcript(), mode="free_speaking")
        self.assertEqual(result.pronunciation_accuracy, 86)
        self.assertEqual(result.pronunciation_fluency, 88)
        self.assertEqual([word.status for word in result.words], ["ok", "ok"])
        self.assertEqual(result, provider.evaluate(b"different", transcript=_transcript(), mode="free_speaking"))

    def test_mock_reference_mode_scores_alignment_and_completeness(self):
        result = MockSpeechEvaluationProvider().evaluate(
            b"audio",
            transcript=_transcript(),
            mode="reference",
            reference_text="Hello there world",
        )
        self.assertEqual(result.pronunciation_accuracy, 53.3)
        self.assertEqual(result.completeness, 66.7)
        self.assertEqual([word.status for word in result.words], ["ok", "needs_review", "missing"])

    def test_tencent_result_is_normalized_from_nested_provider_shape(self):
        result = _parse_result(
            {
                "Response": {
                    "Data": {
                        "PronAccuracy": 91.25,
                        "PronFluency": 87,
                        "PronCompletion": 80,
                        "SentenceInfoSet": [
                            {
                                "Words": [
                                    {"Word": "Hello", "PronAccuracy": 95, "StartMs": 0, "EndMs": 500},
                                    {"Word": "world", "PronAccuracy": 88, "StartMs": 600, "EndMs": 1000},
                                ]
                            }
                        ],
                    }
                }
            }
        )
        self.assertEqual(result.pronunciation_accuracy, 91.2)
        self.assertEqual(result.words[1].start, 0.6)
        self.assertEqual(result.words[1].status, "ok")

    def test_tencent_provider_builds_reference_request_without_network(self):
        provider = TencentSOEProvider(secret_id="id", secret_key="key")
        with patch.object(
            provider,
            "_request",
            return_value={"Response": {"PronAccuracy": 90, "PronFluency": 85}},
        ) as request:
            result = provider.evaluate(
                b"fixture",
                transcript=_transcript(),
                mode="reference",
                reference_text="Hello world",
            )
        body = request.call_args.args[0]
        self.assertEqual(body["RefText"], "Hello world")
        self.assertEqual(body["EvalMode"], 1)
        self.assertEqual(base64.b64decode(body["VoiceData"]), b"fixture")
        self.assertEqual(result.provider, "tencent")

    def test_factory_selects_mock(self):
        settings = MagicMock(speech_eval_provider="mock")
        self.assertEqual(resolve_speech_evaluation_provider_name(settings), "mock")
        self.assertIsInstance(create_speech_evaluation_provider(settings), MockSpeechEvaluationProvider)


if __name__ == "__main__":
    unittest.main()
