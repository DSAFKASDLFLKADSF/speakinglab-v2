"""Interview diagnostics, independent of score normalization and delivery metrics."""

from __future__ import annotations

import math
import re
from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field


class ContentIssue(BaseModel):
    problem: str
    evidence: str
    why_it_matters: str
    imitable_improvement: str


class ContentIssueGroup(BaseModel):
    status: Literal["complete", "unavailable"] = "unavailable"
    issues: list[ContentIssue] = Field(default_factory=list)


class ContentFeedback(BaseModel):
    on_topic: ContentIssueGroup = Field(default_factory=ContentIssueGroup)
    reasoning: ContentIssueGroup = Field(default_factory=ContentIssueGroup)
    example_detail: ContentIssueGroup = Field(default_factory=ContentIssueGroup)


class LanguageIssue(BaseModel):
    original: str
    problem: str
    better_version: str
    pattern_to_imitate: str


class LanguageFeedback(BaseModel):
    status: Literal["complete", "unavailable"] = "unavailable"
    issues: list[LanguageIssue] = Field(default_factory=list)


class ContinuationOption(BaseModel):
    strategy: Literal["explain_why", "give_consequence", "give_example"]
    text: str


class HesitationRecovery(BaseModel):
    detected: bool = False
    timestamp: float | None = None
    duration_seconds: float | None = None
    kind: Literal["pause", "fillers"] | None = None
    timing_source: Literal["word_timestamps"] | None = None
    context_before_hesitation: str = ""
    continuation_options: list[ContinuationOption] = Field(default_factory=list)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _token(value: str) -> str:
    return re.sub(r"[^a-z ]", "", value.lower()).strip()


def _filler_size(words: Sequence[Any], index: int) -> int:
    token = _token(words[index].word)
    if re.fullmatch(r"u+h+|u+m+|e+r+m*|h+m+", token) or token in {"like", "you know"}:
        return 1
    if token == "you" and index + 1 < len(words) and _token(words[index + 1].word) == "know":
        return 2
    return 0


def _valid_time(word: Any) -> bool:
    return (
        isinstance(word.start, (float, int)) and not isinstance(word.start, bool)
        and isinstance(word.end, (float, int)) and not isinstance(word.end, bool)
        and math.isfinite(word.start) and math.isfinite(word.end)
        and 0 <= word.start < word.end
    )


def detect_hesitation(words: Sequence[Any]) -> dict[str, Any] | None:
    """Select one >=5s internal gap or sustained filler run using ASR word times.

    No punctuation/word-count estimates; never bridge a word with missing timing.
    Leading/trailing silence is excluded because it may be recording idle time.
    """
    candidates: list[dict[str, Any]] = []
    # Do not manufacture chronology by sorting broken ASR output.
    previous_end = -1.0
    for word in words:
        if _valid_time(word):
            if word.start < previous_end:
                return None
            previous_end = word.end

    def add(start: float, end: float, index: int, kind: str) -> None:
        if end - start < 5.0:
            return
        # Keep all preceding content, but trim trailing hesitation tokens.
        prefix_end = index
        while prefix_end and _token(words[prefix_end - 1].word) in {"um", "uh", "er", "erm", "hmm", "like", "you know"}:
            prefix_end -= 1
        context = " ".join(w.word.strip() for w in words[:prefix_end]).strip()
        substantive = [t for t in _token(context).split() if t not in {"um", "uh", "er", "erm", "hmm", "like", "you", "know"}]
        if len(substantive) < 3:
            return
        candidates.append({
            "detected": True,
            "timestamp": round(start, 3),
            "duration_seconds": round(end - start, 3),
            "kind": kind,
            "timing_source": "word_timestamps",
            "context_before_hesitation": context,
        })

    for i in range(1, len(words)):
        previous, current = words[i - 1], words[i]
        if _valid_time(previous) and _valid_time(current):
            add(previous.end, current.start, i, "pause")

    i = 0
    while i < len(words):
        start_index = i
        units = 0
        while i < len(words):
            size = _filler_size(words, i)
            if not size or not all(_valid_time(w) for w in words[i:i + size]):
                break
            # A phrase/run is continuous only when adjacent gaps are <=1s.
            first_pair = i if i > start_index else i + 1
            if any(words[j].start - words[j - 1].end > 1.0 for j in range(first_pair, i + size)):
                break
            units += 1
            i += size
        if units >= 2:
            add(words[start_index].start, words[i - 1].end, start_index, "fillers")
        i = max(i, start_index + 1)

    return max(candidates, key=lambda event: event["duration_seconds"], default=None)


def _quoted_in(quote: str, transcript: str) -> bool:
    normalize = lambda value: " ".join(value.lower().split())
    return bool(quote) and normalize(quote) in normalize(transcript)


def _issues(raw: Any, fields: tuple[str, ...], limit: int, transcript: str, quote_key: str) -> dict[str, Any]:
    items = raw.get("issues") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return {"status": "unavailable", "issues": []}
    unavailable = isinstance(raw, dict) and raw.get("status") == "unavailable"
    issues = []
    malformed = False
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            malformed = True
            continue
        issue = {key: _text(item.get(key)) for key in fields}
        if not all(issue.values()) or not _quoted_in(issue[quote_key], transcript):
            malformed = True
            continue
        identity = " ".join(issue[quote_key].lower().split())
        if identity not in seen:
            issues.append(issue)
            seen.add(identity)
    return {"status": "unavailable" if malformed or unavailable else "complete", "issues": issues[:limit]}


def normalize_interview_feedback(raw: Any, *, transcript: str, hesitation: dict[str, Any] | None) -> dict[str, Any]:
    """Drop incomplete/ungrounded diagnostics without affecting numeric scores."""
    raw = raw if isinstance(raw, dict) else {}
    content = raw.get("content_feedback")
    content = content if isinstance(content, dict) else {}
    content_feedback = {
        key: _issues(content.get(key), ("problem", "evidence", "why_it_matters", "imitable_improvement"), 2, transcript, "evidence")
        for key in ("on_topic", "reasoning", "example_detail")
    }
    language_feedback = _issues(raw.get("language_feedback"), ("original", "problem", "better_version", "pattern_to_imitate"), 3, transcript, "original")
    recovery = HesitationRecovery().model_dump()
    if hesitation:
        # Timing and context are server-owned, never accepted from the LLM.
        recovery.update(hesitation)
        supplied = raw.get("hesitation_recovery")
        options = supplied.get("continuation_options") if isinstance(supplied, dict) else None
        seen = set()
        if isinstance(options, list):
            for option in options:
                if not isinstance(option, dict):
                    continue
                strategy = _text(option.get("strategy"))
                text = _text(option.get("text"))
                if strategy not in {"explain_why", "give_consequence", "give_example"} or strategy in seen:
                    continue
                if not text or len(text) > 600 or len(re.split(r"(?<=[.!?])\s+", text)) > 2:
                    continue
                seen.add(strategy)
                recovery["continuation_options"].append({"strategy": strategy, "text": text})
        if len(recovery["continuation_options"]) < 2:
            recovery["continuation_options"] = []
    return {
        "summary": "Review topic development and language use below.",
        "sections": [],
        "content_feedback": content_feedback,
        "language_feedback": language_feedback,
        "hesitation_recovery": recovery,
    }
