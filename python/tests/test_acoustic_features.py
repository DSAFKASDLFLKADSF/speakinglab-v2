"""Regression tests for waveform-based Phase 3 acoustic metrics.

The fixture is deliberately generated in memory so these tests stay offline and
do not depend on a particular browser container (webm/opus) or ffmpeg install.
Pitch extraction is implementation-dependent for short fixtures, so the
prosody assertions accept ``None`` while still requiring finite values when a
value is available.
"""

from __future__ import annotations

import math
import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio_features import (
    AudioFeatures,
    acoustic_metrics_to_dict,
    analyze_audio_features,
    features_from_transcription,
)
from whisper_transcribe import WhisperWord
from toefl_rubric import get_toefl_score_prompt


SAMPLE_RATE = 16_000


def _tone(seconds: float, *, frequency: float = 180.0) -> np.ndarray:
    """Create a deterministic voiced fixture at the analyzer sample rate."""
    count = int(round(seconds * SAMPLE_RATE))
    t = np.arange(count, dtype=np.float32) / SAMPLE_RATE
    return (0.35 * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def _voiced_with_pause() -> np.ndarray:
    # A clear 1.2 second pause between two voiced regions.  The edges are not
    # clipped, which keeps the RMS threshold behavior stable across librosa
    # versions.
    return np.concatenate(
        [_tone(1.0), np.zeros(int(1.2 * SAMPLE_RATE), np.float32), _tone(1.0)]
    )


class AcousticFeatureTests(unittest.TestCase):
    def test_waveform_silence_is_measured_without_word_gap(self):
        features = analyze_audio_features(
            _voiced_with_pause(),
            "hello world",
            sample_rate=SAMPLE_RATE,
            min_pause_duration=0.3,
            silence_threshold_db=-40,
        )

        self.assertAlmostEqual(features.duration_seconds, 3.2, delta=0.03)
        self.assertEqual(features.word_count, 2)
        self.assertGreaterEqual(features.pause_count, 1)
        self.assertGreater(features.longest_pause, 0.4)

        # Phase 3 fields must expose the amount of real waveform silence.  A
        # transcript-only implementation cannot satisfy these checks for a
        # punctuation-free transcript with no word timestamps.
        self.assertTrue(hasattr(features, "long_pause_count"))
        self.assertTrue(hasattr(features, "total_pause_time"))
        self.assertTrue(hasattr(features, "pause_ratio"))
        self.assertGreaterEqual(features.long_pause_count, 1)
        self.assertGreaterEqual(features.total_pause_time, features.longest_pause)
        self.assertGreater(features.pause_ratio, 0)
        self.assertLessEqual(features.pause_ratio, 1)

    def test_speech_rate_and_articulation_rate_are_finite(self):
        features = analyze_audio_features(
            _tone(2.0),
            "one two three four",
            sample_rate=SAMPLE_RATE,
            min_pause_duration=0.3,
        )

        self.assertGreater(features.wpm, 0)
        self.assertTrue(hasattr(features, "articulation_rate"))
        self.assertTrue(math.isfinite(features.articulation_rate))
        self.assertGreaterEqual(features.articulation_rate, features.wpm)

    def test_silence_only_audio_is_safe_and_prosody_may_be_unavailable(self):
        features = analyze_audio_features(
            np.zeros(SAMPLE_RATE, dtype=np.float32),
            "",
            sample_rate=SAMPLE_RATE,
        )

        self.assertGreater(features.duration_seconds, 0)
        self.assertGreaterEqual(features.pause_count, 0)
        self.assertGreaterEqual(features.longest_pause, 0)
        for field in ("pitch_median", "pitch_variation", "energy_variation"):
            self.assertTrue(hasattr(features, field))
            value = getattr(features, field)
            self.assertTrue(value is None or math.isfinite(value))

    def test_transcript_only_fallback_keeps_word_gap_behavior(self):
        words = [
            WhisperWord("One", 0, 0.5),
            WhisperWord("two", 1.2, 1.7),
        ]
        features = features_from_transcription(
            "One two",
            words=words,
            duration_seconds=1.7,
        )

        self.assertEqual(features.pause_count, 1)
        self.assertAlmostEqual(features.longest_pause, 0.7, delta=0.01)
        self.assertEqual(features.word_count, 2)

    def test_acoustic_metrics_are_serialized_as_normalized_nested_data(self):
        metrics = acoustic_metrics_to_dict(
            analyze_audio_features(
                _voiced_with_pause(),
                "hello world",
                sample_rate=SAMPLE_RATE,
            )
        )

        self.assertEqual(metrics["speech"]["word_count"], 2)
        self.assertIn("articulation_rate", metrics["speech"])
        self.assertIn("long_pause_count", metrics["pauses"])
        self.assertIn("total_pause_time", metrics["pauses"])
        self.assertIn("pause_ratio", metrics["pauses"])
        self.assertIn("count", metrics["fillers"])
        self.assertIn("pitch_median", metrics["prosody"])
        self.assertIn("pitch_variation", metrics["prosody"])
        self.assertIn("energy_variation", metrics["prosody"])
        self.assertEqual(metrics["source"], "waveform")

    def test_main_uses_waveform_analyzer_when_recording_bytes_are_available(self):
        # Keep this dispatch test independent of a browser codec. The analyzer
        # itself is covered above with a NumPy fixture; here we verify the
        # production orchestration does not silently fall back to transcript
        # timestamps when the downloaded recording is present.
        import main
        from unittest.mock import patch
        from providers.asr.base import TranscriptResult

        expected = AudioFeatures(
            wpm=120,
            pause_count=1,
            longest_pause=1.1,
            filler_count=0,
            duration_seconds=3.2,
            word_count=2,
            articulation_rate=180,
            long_pause_count=1,
            total_pause_time=1.1,
            pause_ratio=0.344,
            analysis_source="waveform",
        )
        transcription = TranscriptResult(
            transcript="hello world",
            words=[],
            duration=3.2,
            model="fixture:asr",
        )
        with patch.object(main, "analyze_audio_features", return_value=expected) as analyze:
            result = main.behavior_features_from_transcription(
                transcription,
                audio_bytes=b"encoded-audio",
            )

        self.assertIs(result, expected)
        analyze.assert_called_once()
        self.assertIs(analyze.call_args.args[0], b"encoded-audio")

    def test_acoustic_metrics_are_included_in_scoring_prompt(self):
        prompt = get_toefl_score_prompt(
            task="interview",
            question="What do you prefer?",
            transcript="I prefer tea.",
            acoustic_metrics={"source": "waveform", "speech": {"wpm": 120}},
        )
        payload = json.loads(prompt.user)
        self.assertEqual(payload["acoustic_metrics"]["source"], "waveform")


if __name__ == "__main__":
    unittest.main()
