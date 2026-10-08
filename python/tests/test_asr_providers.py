"""Phase 1 provider contract tests; no cloud credentials or network calls."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.asr.base import TranscriptResult
from providers.asr.factory import create_asr_provider, resolve_provider_name
from providers.asr.mock_asr import MockASRProvider
from providers.asr.tencent_asr import TencentASRProvider, _parse_result


class ASRContractTests(unittest.TestCase):
    def test_mock_provider_is_deterministic_and_normalized(self):
        provider = MockASRProvider("Hello from the local test provider.", duration=4)
        first = provider.transcribe(b"audio")
        second = provider.transcribe(b"different audio")

        self.assertIsInstance(first, TranscriptResult)
        self.assertEqual(first.text, "Hello from the local test provider.")
        self.assertEqual(first.duration_seconds, 4)
        self.assertEqual(first, second)
        self.assertEqual(first.words[0].start, 0)
        self.assertEqual(first.words[-1].end, 4)
        self.assertEqual(first.words[0].confidence, 1)

    def test_tencent_result_is_normalized_from_provider_shape(self):
        result = _parse_result(
            {
                "Response": {
                    "Data": {
                        "Result": "Hello world",
                        "AudioDuration": 2.4,
                        "ResultDetail": [
                            {
                                "Words": [
                                    {"Word": "Hello", "StartMs": 100, "EndMs": 800, "Confidence": 96},
                                    {"Word": "world", "StartMs": 900, "EndMs": 2200, "Confidence": 91},
                                ]
                            }
                        ],
                    }
                }
            },
            language="en",
            model="tencent:16k_en",
        )
        self.assertEqual(result.text, "Hello world")
        self.assertEqual(result.duration_seconds, 2.4)
        self.assertEqual((result.words[0].start, result.words[0].end), (0.1, 0.8))
        self.assertEqual(result.words[0].confidence, 0.96)

    def test_tencent_provider_creates_and_polls_without_leaking_raw_shape(self):
        provider = TencentASRProvider(secret_id="id", secret_key="key", poll_interval=0.01)
        responses = [
            {"Response": {"Data": {"TaskId": 123}}},
            {"Response": {"Data": {"Status": 0, "StatusStr": "waiting"}}},
            {"Response": {"Data": {"Status": 1, "StatusStr": "success", "Result": "done"}}},
        ]
        with patch.object(provider, "_request", side_effect=responses) as request:
            result = provider.transcribe(b"fixture")
        self.assertEqual(result.text, "done")
        self.assertEqual(result.model, "tencent:16k_en")
        self.assertEqual(request.call_args_list[0].args[0], "CreateRecTask")
        self.assertEqual(request.call_args_list[1].args[0], "DescribeTaskStatus")

    def test_factory_selects_mock_without_credentials(self):
        settings = MagicMock(
            asr_provider="mock",
            mock_asr_transcript=None,
            mock_asr_duration_seconds=6,
            tencent_secret_id=None,
            tencent_secret_key=None,
        )
        self.assertEqual(resolve_provider_name(settings), "mock")
        self.assertIsInstance(create_asr_provider(settings), MockASRProvider)


if __name__ == "__main__":
    unittest.main()
