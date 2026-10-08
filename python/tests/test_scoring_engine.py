"""Phase 4 scoring-engine tests; all inputs are normalized offline fixtures."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scoring_engine import ScoringConfig, score_interview


GOOD_ACOUSTIC = {
    "duration_seconds": 60,
    "speech": {"word_count": 130, "wpm": 130, "articulation_rate": 140},
    "pauses": {
        "pause_count": 2,
        "long_pause_count": 0,
        "longest_pause": 0.4,
        "total_pause_time": 3,
        "pause_ratio": 0.05,
    },
    "fillers": {"count": 1},
    "prosody": {"pitch_median": 150, "pitch_variation": 8, "energy_variation": 0.2},
    "source": "waveform",
}


class ScoringEngineTests(unittest.TestCase):
    def test_phase4_separates_objective_and_language_scores(self):
        result = score_interview(
            acoustic_metrics=GOOD_ACOUSTIC,
            pronunciation_metrics={
                "pronunciation_accuracy": 90,
                "pronunciation_fluency": 92,
                "completeness": 95,
            },
            legacy_scores={"topic": 4, "grammar": 3, "pronunciation": 2},
        )

        self.assertEqual(result["scoring_version"], "delivery-v1")
        self.assertEqual(result["objective"]["pace"], 5.0)
        self.assertGreater(result["objective"]["pronunciation"], 4.5)
        self.assertEqual(result["objective"]["fluency"], 5.0)
        self.assertEqual(result["language"], {"content": 4.0, "grammar_vocabulary": 3.0})
        self.assertGreater(result["overall"], 3.5)

    def test_poor_delivery_degrades_only_the_objective_dimensions(self):
        poor = {
            **GOOD_ACOUSTIC,
            "duration_seconds": 60,
            "speech": {"word_count": 30, "wpm": 30, "articulation_rate": 30},
            "pauses": {
                "pause_count": 8,
                "long_pause_count": 5,
                "longest_pause": 3,
                "total_pause_time": 30,
                "pause_ratio": 0.5,
            },
            "fillers": {"count": 12},
        }
        result = score_interview(
            acoustic_metrics=poor,
            pronunciation_metrics=None,
            legacy_scores={"topic": 4, "grammar": 4, "pronunciation": 2},
        )

        self.assertLess(result["objective"]["pace"], 2)
        self.assertLess(result["objective"]["fluency"], 3)
        self.assertEqual(result["objective"]["pronunciation"], 2.0)
        self.assertEqual(result["language"], {"content": 4.0, "grammar_vocabulary": 4.0})

    def test_configured_version_and_weight_are_applied(self):
        config = ScoringConfig(version="delivery-test", objective_weight=0.8)
        result = score_interview(
            acoustic_metrics=GOOD_ACOUSTIC,
            pronunciation_metrics=None,
            legacy_scores={"topic": 1, "grammar": 1, "pronunciation": 1},
            config=config,
        )

        self.assertEqual(result["scoring_version"], "delivery-test")
        expected = round(
            result["objective"]["pace"] * 0.35
            + result["objective"]["pronunciation"] * 0.4
            + result["objective"]["fluency"] * 0.25,
            2,
        )
        self.assertGreater(result["overall"], expected * 0.8)

    def test_environment_configuration_is_safe_and_repeatable(self):
        with patch.dict(
            os.environ,
            {
                "DELIVERY_SCORING_VERSION": "delivery-env",
                "DELIVERY_SCORING_OBJECTIVE_WEIGHT": "0.75",
                "DELIVERY_SCORING_PACE_IDEAL_MIN": "bad",
            },
            clear=False,
        ):
            config = ScoringConfig.from_environment()
        self.assertEqual(config.version, "delivery-env")
        self.assertEqual(config.objective_weight, 0.75)
        self.assertEqual(config.pace_ideal_min, 110.0)


if __name__ == "__main__":
    unittest.main()
