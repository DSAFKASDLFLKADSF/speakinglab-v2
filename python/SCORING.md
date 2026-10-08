# Phase 4 scoring engine

Interview responses now expose a `scoring` object alongside the legacy
`scores` fields. The legacy fields remain for existing clients and are still
the four integer rubric scores returned by the LLM.

`scoring.objective` is calculated locally from normalized waveform and speech
evaluation evidence:

- `pace` uses WPM against a configurable conversational range.
- `fluency` combines pause ratio, long-pause rate, and filler density.
- `pronunciation` uses Tencent/mock speech-evaluation scores when available;
  it falls back to the legacy pronunciation score when no provider result is
  available.

`scoring.language` maps the LLM's subjective `topic` and `grammar` scores to
`content` and `grammar_vocabulary`. `overall` combines the objective and
language averages with a configurable objective weight.

The initial heuristic is versioned as `delivery-v1`. It is deliberately kept
in `scoring_engine.py` and should be calibrated against teacher ratings before
being treated as an official TOEFL conversion.

Optional environment variables:

```text
DELIVERY_SCORING_VERSION=delivery-v1
DELIVERY_SCORING_OBJECTIVE_WEIGHT=0.6
DELIVERY_SCORING_PACE_IDEAL_MIN=110
DELIVERY_SCORING_PACE_IDEAL_MAX=170
DELIVERY_SCORING_PACE_HARD_MIN=50
DELIVERY_SCORING_PACE_HARD_MAX=240
DELIVERY_SCORING_PAUSE_IDEAL_MAX=0.08
DELIVERY_SCORING_PAUSE_HARD_MAX=0.35
DELIVERY_SCORING_LONG_PAUSE_IDEAL_MAX=1
DELIVERY_SCORING_LONG_PAUSE_HARD_MAX=4
DELIVERY_SCORING_FILLER_IDEAL_MAX=1.5
DELIVERY_SCORING_FILLER_HARD_MAX=8
```
