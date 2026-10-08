"""Versioned delivery scoring for the Phase 4 interview result.

The LLM remains responsible for subjective language judgments (content and
grammar/vocabulary). Delivery scores are calculated here from normalized
acoustic and pronunciation evidence. The thresholds are intentionally
configuration-driven: ``delivery-v1`` is an initial heuristic and is not a
teacher-calibrated TOEFL conversion.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


DEFAULT_SCORING_VERSION = "delivery-v1"


@dataclass(frozen=True)
class ScoringConfig:
    """Thresholds and weights for one delivery-scoring version."""

    version: str = DEFAULT_SCORING_VERSION
    objective_weight: float = 0.6
    pace_ideal_min: float = 110.0
    pace_ideal_max: float = 170.0
    pace_hard_min: float = 50.0
    pace_hard_max: float = 240.0
    pause_ratio_ideal_max: float = 0.08
    pause_ratio_hard_max: float = 0.35
    long_pause_rate_ideal_max: float = 1.0
    long_pause_rate_hard_max: float = 4.0
    filler_rate_ideal_max: float = 1.5
    filler_rate_hard_max: float = 8.0

    @classmethod
    def from_environment(cls) -> "ScoringConfig":
        """Read optional thresholds without making malformed env fatal."""

        def number(name: str, default: float, *, low: float, high: float) -> float:
            try:
                value = float(os.getenv(name, str(default)))
            except (TypeError, ValueError):
                return default
            if value != value or value in (float("inf"), float("-inf")):
                return default
            return max(low, min(high, value))

        version = os.getenv("DELIVERY_SCORING_VERSION", DEFAULT_SCORING_VERSION).strip()
        pace_ideal_min = number("DELIVERY_SCORING_PACE_IDEAL_MIN", 110.0, low=1.0, high=300.0)
        pace_ideal_max = number("DELIVERY_SCORING_PACE_IDEAL_MAX", 170.0, low=1.0, high=300.0)
        pace_hard_min = number("DELIVERY_SCORING_PACE_HARD_MIN", 50.0, low=0.0, high=300.0)
        pace_hard_max = number("DELIVERY_SCORING_PACE_HARD_MAX", 240.0, low=1.0, high=500.0)
        pause_ratio_ideal_max = number("DELIVERY_SCORING_PAUSE_IDEAL_MAX", 0.08, low=0.0, high=1.0)
        pause_ratio_hard_max = number("DELIVERY_SCORING_PAUSE_HARD_MAX", 0.35, low=0.0, high=1.0)
        long_pause_rate_ideal_max = number("DELIVERY_SCORING_LONG_PAUSE_IDEAL_MAX", 1.0, low=0.0, high=30.0)
        long_pause_rate_hard_max = number("DELIVERY_SCORING_LONG_PAUSE_HARD_MAX", 4.0, low=0.0, high=60.0)
        filler_rate_ideal_max = number("DELIVERY_SCORING_FILLER_IDEAL_MAX", 1.5, low=0.0, high=50.0)
        filler_rate_hard_max = number("DELIVERY_SCORING_FILLER_HARD_MAX", 8.0, low=0.0, high=100.0)
        return cls(
            version=version or DEFAULT_SCORING_VERSION,
            objective_weight=number(
                "DELIVERY_SCORING_OBJECTIVE_WEIGHT", 0.6, low=0.0, high=1.0
            ),
            pace_ideal_min=pace_ideal_min,
            pace_ideal_max=max(pace_ideal_min, pace_ideal_max),
            pace_hard_min=min(pace_hard_min, pace_ideal_min),
            pace_hard_max=max(pace_hard_max, pace_ideal_max),
            pause_ratio_ideal_max=pause_ratio_ideal_max,
            pause_ratio_hard_max=max(pause_ratio_hard_max, pause_ratio_ideal_max),
            long_pause_rate_ideal_max=long_pause_rate_ideal_max,
            long_pause_rate_hard_max=max(long_pause_rate_hard_max, long_pause_rate_ideal_max),
            filler_rate_ideal_max=filler_rate_ideal_max,
            filler_rate_hard_max=max(filler_rate_hard_max, filler_rate_ideal_max),
        )


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if result == result and abs(result) != float("inf") else default


def _clamp_score(value: float) -> float:
    return round(max(1.0, min(5.0, value)), 2)


def _legacy_score(scores: Mapping[str, Any], key: str, default: float = 3.0) -> float:
    return _clamp_score(_number(scores.get(key), default))


def _upper_threshold_score(value: float, ideal_max: float, hard_max: float) -> float:
    """Score a metric where lower values are better."""
    if value <= ideal_max:
        return 5.0
    if hard_max <= ideal_max:
        return 1.0 if value > ideal_max else 5.0
    return _clamp_score(5.0 - 4.0 * (value - ideal_max) / (hard_max - ideal_max))


def _range_score(value: float, config: ScoringConfig) -> float:
    if config.pace_ideal_min <= value <= config.pace_ideal_max:
        return 5.0
    if value < config.pace_ideal_min:
        span = max(0.001, config.pace_ideal_min - config.pace_hard_min)
        return _clamp_score(1.0 + 4.0 * (value - config.pace_hard_min) / span)
    span = max(0.001, config.pace_hard_max - config.pace_ideal_max)
    return _clamp_score(5.0 - 4.0 * (value - config.pace_ideal_max) / span)


def _pronunciation_score(
    pronunciation: Mapping[str, Any] | None,
    legacy_scores: Mapping[str, Any],
) -> float:
    pronunciation = pronunciation or {}
    accuracy = _number(pronunciation.get("pronunciation_accuracy"), -1.0)
    fluency = _number(pronunciation.get("pronunciation_fluency"), -1.0)
    completeness = _number(pronunciation.get("completeness"), -1.0)
    available = [value for value in (accuracy, fluency, completeness) if value >= 0]
    if available:
        return _clamp_score(1.0 + 4.0 * (sum(available) / len(available)) / 100.0)
    return _legacy_score(legacy_scores, "pronunciation")


def score_interview(
    *,
    acoustic_metrics: Mapping[str, Any] | None,
    pronunciation_metrics: Mapping[str, Any] | None,
    legacy_scores: Mapping[str, Any],
    config: ScoringConfig | None = None,
) -> dict[str, Any]:
    """Return the versioned objective/language/overall interview breakdown."""
    config = config or ScoringConfig.from_environment()
    acoustic = acoustic_metrics or {}
    speech = acoustic.get("speech") if isinstance(acoustic.get("speech"), Mapping) else {}
    pauses = acoustic.get("pauses") if isinstance(acoustic.get("pauses"), Mapping) else {}
    fillers = acoustic.get("fillers") if isinstance(acoustic.get("fillers"), Mapping) else {}

    wpm = _number(speech.get("wpm"))
    pause_ratio = max(0.0, _number(pauses.get("pause_ratio")))
    long_pause_count = max(0.0, _number(pauses.get("long_pause_count")))
    duration = max(0.1, _number(acoustic.get("duration_seconds"), 1.0))
    filler_count = max(0.0, _number(fillers.get("count")))
    word_count = max(0.0, _number(speech.get("word_count")))

    pace = _range_score(wpm, config)
    pause_score = _upper_threshold_score(
        pause_ratio, config.pause_ratio_ideal_max, config.pause_ratio_hard_max
    )
    long_pause_rate = long_pause_count / (duration / 60.0)
    long_pause_score = _upper_threshold_score(
        long_pause_rate,
        config.long_pause_rate_ideal_max,
        config.long_pause_rate_hard_max,
    )
    filler_rate = filler_count / max(1.0, word_count) * 100.0
    filler_score = _upper_threshold_score(
        filler_rate, config.filler_rate_ideal_max, config.filler_rate_hard_max
    )
    fluency = _clamp_score(
        pause_score * 0.55 + long_pause_score * 0.25 + filler_score * 0.20
    )
    pronunciation = _pronunciation_score(pronunciation_metrics, legacy_scores)

    content = _legacy_score(legacy_scores, "topic")
    grammar_vocabulary = _legacy_score(legacy_scores, "grammar")
    objective = _clamp_score(pace * 0.35 + pronunciation * 0.40 + fluency * 0.25)
    language = _clamp_score((content + grammar_vocabulary) / 2.0)
    overall = _clamp_score(
        objective * config.objective_weight
        + language * (1.0 - config.objective_weight)
    )

    return {
        "scoring_version": config.version,
        "objective": {
            "pace": pace,
            "pronunciation": pronunciation,
            "fluency": fluency,
        },
        "language": {
            "content": content,
            "grammar_vocabulary": grammar_vocabulary,
        },
        "overall": overall,
    }
