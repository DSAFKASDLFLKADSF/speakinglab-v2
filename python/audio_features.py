"""Extract speaking behavior metrics from audio and transcript."""

from __future__ import annotations

import logging
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import librosa
import numpy as np

from providers.asr.base import TranscriptWord

logger = logging.getLogger(__name__)

FILLER_PATTERN = re.compile(
    r"\b(um+|uh+|er+|ah+|em+|hmm+|like|you know|i mean|sort of|kind of)\b",
    re.IGNORECASE,
)

DEFAULT_MIN_PAUSE_SECONDS = 0.3
DEFAULT_LONG_PAUSE_SECONDS = 1.0
DEFAULT_SILENCE_THRESHOLD_DB = -40.0
# 20 ms RMS windows with 10 ms hops at the analysis sample rate. Pitch needs
# longer windows and is calculated independently from this silence envelope.
DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_FRAME_LENGTH = 320
DEFAULT_HOP_LENGTH = 160
DEFAULT_PITCH_FRAME_LENGTH = 2048
MIN_RMS = 1e-4


@dataclass(frozen=True)
class AudioFeatures:
    wpm: float
    pause_count: int
    longest_pause: float
    filler_count: int
    duration_seconds: float
    word_count: int
    articulation_rate: float = 0.0
    long_pause_count: int = 0
    total_pause_time: float = 0.0
    pause_ratio: float = 0.0
    pitch_median: float | None = None
    pitch_variation: float | None = None
    energy_variation: float | None = None
    analysis_source: str = "transcript"
    speech_duration_seconds: float | None = None


def _count_fillers(transcript: str) -> int:
    return len(FILLER_PATTERN.findall(transcript.strip()))


def _suffix_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return ".webm"
    lowered = content_type.split(";")[0].strip().lower()
    mapping = {
        "audio/webm": ".webm",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
    }
    return mapping.get(lowered, ".webm")


def _estimate_duration_seconds(
    audio_bytes: bytes | None,
    word_count: int,
    duration_hint: float | None = None,
) -> float:
    if _positive_number(duration_hint):
        return max(0.1, round(float(duration_hint), 2))
    if audio_bytes and len(audio_bytes) > 0:
        # Rough estimate for compressed browser speech (webm/opus).
        return max(1.0, round(len(audio_bytes) / 12_000, 2))
    return max(1.0, round(word_count * 0.35, 2))


def _fallback_features(
    transcript: str,
    *,
    audio_bytes: bytes | None = None,
    duration_hint: float | None = None,
    words: Sequence[TranscriptWord] | None = None,
) -> AudioFeatures:
    logger.warning(
        "Using transcript-based estimates; waveform/prosody measurements unavailable."
    )
    return features_from_transcription(
        transcript, words=words, audio_bytes=audio_bytes, duration_hint=duration_hint
    )


def _try_ffmpeg_to_wav(src: Path) -> Path | None:
    if not shutil.which("ffmpeg"):
        return None

    fd, out_name = tempfile.mkstemp(suffix=".wav")
    import os

    os.close(fd)
    out_path = Path(out_name)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-ac",
                "1",
                "-ar",
                "16000",
                str(out_path),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return out_path
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("ffmpeg conversion failed: %s", exc)
        out_path.unlink(missing_ok=True)
        return None


def _load_audio_bytes(
    audio: bytes,
    *,
    suffix: str,
    sample_rate: int | None,
) -> tuple[np.ndarray, int, list[Path]]:
    """Load raw bytes; returns waveform and temp paths to clean up."""
    temp_paths: list[Path] = []

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio)
        src_path = Path(tmp.name)
    temp_paths.append(src_path)

    decode_error: Exception | None = None
    try:
        y, sr = librosa.load(src_path, sr=sample_rate, mono=True)
        return y, sr, temp_paths
    except Exception as exc:
        decode_error = exc
        logger.debug("librosa load failed for %s: %s", suffix, exc)

    wav_path = _try_ffmpeg_to_wav(src_path)
    if wav_path is not None:
        temp_paths.append(wav_path)
        try:
            y, sr = librosa.load(wav_path, sr=sample_rate, mono=True)
            return y, sr, temp_paths
        except Exception as exc:
            decode_error = exc
            logger.debug(
                "librosa load failed after ffmpeg for %s: %s", suffix, exc
            )

    # Failure never returns temp_paths to the caller, so cleanup belongs here.
    for path in temp_paths:
        path.unlink(missing_ok=True)
    if decode_error is not None:
        raise decode_error
    raise RuntimeError("Failed to decode audio bytes")


def _load_audio(
    audio: str | Path | bytes | np.ndarray,
    *,
    sample_rate: int | None = None,
    suffix: str = ".webm",
) -> tuple[np.ndarray, int, list[Path]]:
    """
    Load mono audio for analysis.

    Returns (waveform, sr, temp_paths). Caller must unlink temp_paths when set.
    """
    if isinstance(audio, np.ndarray):
        sr = sample_rate or DEFAULT_SAMPLE_RATE
        return audio, sr, []

    if isinstance(audio, bytes):
        return _load_audio_bytes(audio, suffix=suffix, sample_rate=sample_rate)

    path = Path(audio)
    y, sr = librosa.load(path, sr=sample_rate, mono=True)
    return y, sr, []


def _detect_pauses_from_audio(
    y: np.ndarray,
    sr: int,
    *,
    min_pause_duration: float = DEFAULT_MIN_PAUSE_SECONDS,
    silence_threshold_db: float = DEFAULT_SILENCE_THRESHOLD_DB,
    frame_length: int = DEFAULT_FRAME_LENGTH,
    hop_length: int = DEFAULT_HOP_LENGTH,
) -> list[float]:
    """Return pause durations (seconds) detected from low-energy regions."""
    if y.size == 0:
        return []

    rms = librosa.feature.rms(
        y=y, frame_length=frame_length, hop_length=hop_length
    )[0]
    rms = np.nan_to_num(rms, nan=0.0, posinf=0.0, neginf=0.0)
    if rms.size == 0:
        return []

    max_rms = float(np.max(rms))
    if max_rms < MIN_RMS:
        return []

    db = librosa.amplitude_to_db(rms, ref=max_rms)
    silent = db < silence_threshold_db
    voiced = np.flatnonzero(~silent)
    if voiced.size < 2:
        # A completely silent recording has no internal pause. Its duration is
        # still reported by the caller, but it must not become one giant pause.
        return []

    pauses: list[float] = []
    first_voiced = int(voiced[0])
    last_voiced = int(voiced[-1])
    in_pause = False
    pause_start = 0
    for idx in range(first_voiced, last_voiced + 1):
        if silent[idx] and not in_pause:
            pause_start = idx
            in_pause = True
        elif not silent[idx] and in_pause:
            duration = (idx - pause_start) * hop_length / sr
            if duration >= min_pause_duration:
                pauses.append(duration)
            in_pause = False

    return pauses


def _prosody_from_audio(
    y: np.ndarray,
    sr: int,
    *,
    frame_length: int = DEFAULT_PITCH_FRAME_LENGTH,
    hop_length: int = DEFAULT_HOP_LENGTH,
) -> tuple[float | None, float | None, float | None]:
    """Return pitch median, pitch spread, and relative RMS variation."""
    if y.size == 0 or not np.any(np.abs(y) > 0):
        return None, None, None

    rms = librosa.feature.rms(
        y=y, frame_length=frame_length, hop_length=hop_length
    )[0]
    finite_rms = rms[np.isfinite(rms) & (rms > 0)]
    max_rms = float(np.max(finite_rms)) if finite_rms.size else 0.0
    if max_rms < MIN_RMS:
        return None, None, None
    rms_floor = max_rms * 10 ** (DEFAULT_SILENCE_THRESHOLD_DB / 20)
    voiced_rms = finite_rms[finite_rms >= rms_floor] if rms_floor else finite_rms
    energy_variation = None
    if voiced_rms.size:
        energy_variation = round(
            float(np.std(voiced_rms) / max(float(np.mean(voiced_rms)), 1e-8)), 3
        )

    pitch_median = None
    pitch_variation = None
    try:
        fmax = min(500.0, max(100.0, sr / 2.0 - 1.0))
        pitches = librosa.yin(
            y,
            fmin=75.0,
            fmax=fmax,
            sr=sr,
            frame_length=frame_length,
            hop_length=hop_length,
        )
        frame_mask = np.isfinite(rms) & (rms >= rms_floor)
        usable = min(len(pitches), len(frame_mask))
        pitches = pitches[:usable]
        frame_mask = frame_mask[:usable]
        voiced = pitches[
            frame_mask & np.isfinite(pitches) & (pitches >= 75.0) & (pitches <= fmax)
        ]
        if voiced.size:
            pitch_median = round(float(np.median(voiced)), 1)
            pitch_variation = round(float(np.std(voiced)), 1)
    except Exception as exc:
        logger.debug("Pitch analysis failed: %s", exc)

    return pitch_median, pitch_variation, energy_variation


def _positive_number(value: object) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


def _voiced_span_seconds(
    y: np.ndarray,
    sr: int,
    *,
    silence_threshold_db: float = DEFAULT_SILENCE_THRESHOLD_DB,
    frame_length: int = DEFAULT_FRAME_LENGTH,
    hop_length: int = DEFAULT_HOP_LENGTH,
) -> float:
    """Return the voiced envelope span, excluding leading/trailing silence."""
    if y.size == 0:
        return 0.0
    rms = librosa.feature.rms(
        y=y, frame_length=frame_length, hop_length=hop_length
    )[0]
    rms = np.nan_to_num(rms, nan=0.0, posinf=0.0, neginf=0.0)
    max_rms = float(np.max(rms)) if rms.size else 0.0
    if max_rms < MIN_RMS:
        return 0.0
    floor = max_rms * 10 ** (silence_threshold_db / 20)
    voiced = np.flatnonzero(rms >= max(floor, MIN_RMS))
    if voiced.size == 0:
        return 0.0
    span = (int(voiced[-1]) - int(voiced[0]) + 1) * hop_length / sr
    return min(float(len(y) / sr), max(0.0, span))


def _has_word_timing(word: TranscriptWord) -> bool:
    return (not isinstance(word.start, bool) and not isinstance(word.end, bool)
            and isinstance(word.start, (int, float)) and isinstance(word.end, (int, float))
            and math.isfinite(word.start) and math.isfinite(word.end)
            and 0 <= word.start < word.end)


def _detect_pauses_from_word_gaps(
    words: Sequence[TranscriptWord],
    *,
    min_pause_duration: float = DEFAULT_MIN_PAUSE_SECONDS,
) -> list[float]:
    """Infer pauses from Whisper word timestamps when available."""
    pauses: list[float] = []
    for prev, curr in zip(words, words[1:]):
        if not _has_word_timing(prev) or not _has_word_timing(curr):
            continue
        gap = float(curr.start) - float(prev.end)  # type: ignore[arg-type]
        if gap >= min_pause_duration:
            pauses.append(gap)

    return pauses


def _resolve_duration_seconds(
    word_count: int,
    *,
    duration_seconds: float | None = None,
    duration_hint: float | None = None,
    words: Sequence[TranscriptWord] | None = None,
    audio_bytes: bytes | None = None,
) -> float:
    """Pick the best available duration without decoding audio."""
    if _positive_number(duration_hint):
        return max(0.1, round(float(duration_hint), 2))
    if _positive_number(duration_seconds):
        return max(0.1, round(float(duration_seconds), 2))

    timed = [w for w in (words or []) if _has_word_timing(w)]
    if len(timed) >= 2:
        span = float(timed[-1].end) - float(timed[0].start)  # type: ignore[arg-type]
        if span > 0:
            return round(span, 2)
    if len(timed) == 1 and timed[0].end is not None:
        return round(max(float(timed[0].end), 0.1), 2)  # type: ignore[arg-type]

    return _estimate_duration_seconds(audio_bytes, word_count, None)


def features_from_transcription(
    transcript: str,
    *,
    words: Sequence[TranscriptWord] | None = None,
    duration_seconds: float | None = None,
    duration_hint: float | None = None,
    audio_bytes: bytes | None = None,
    min_pause_duration: float = DEFAULT_MIN_PAUSE_SECONDS,
) -> AudioFeatures:
    """
    Lightweight speaking metrics from transcript + word timestamps.

    Avoids Librosa/ffmpeg audio decode — suitable for GLM scoring evidence.
    """
    text = transcript.strip()
    tokens = [t for t in text.split() if t]
    word_count = len(tokens)
    filler_count = _count_fillers(text)

    duration = _resolve_duration_seconds(
        word_count,
        duration_seconds=duration_seconds,
        duration_hint=duration_hint,
        words=words,
        audio_bytes=audio_bytes,
    )
    duration = max(duration, 0.1)

    pauses = _detect_pauses_from_word_gaps(
        words or [], min_pause_duration=min_pause_duration
    )
    timed_words = words or []
    has_timing = len(timed_words) >= 2 and all(_has_word_timing(word) for word in timed_words)
    if pauses or has_timing:
        pause_count = len(pauses)
        longest_pause = round(max(pauses, default=0), 2)
    else:
        punctuation_pauses = len(re.findall(r"[,;:.!?…]", text))
        pause_count = max(0, punctuation_pauses + filler_count)
        longest_pause = round(
            min(duration * 0.4, max(0.3, filler_count * 0.5)), 2
        )

    duration_min = duration / 60.0
    wpm = round(word_count / duration_min, 1) if word_count else 0.0
    total_pause_time = round(sum(pauses), 2)
    speech_duration = max(duration - total_pause_time, 0.1)

    return AudioFeatures(
        wpm=wpm,
        pause_count=pause_count,
        longest_pause=longest_pause,
        filler_count=filler_count,
        duration_seconds=round(duration, 2),
        word_count=word_count,
        articulation_rate=round(word_count / (speech_duration / 60.0), 1) if word_count else 0.0,
        long_pause_count=sum(pause >= DEFAULT_LONG_PAUSE_SECONDS for pause in pauses),
        total_pause_time=total_pause_time,
        pause_ratio=round(min(total_pause_time / duration, 1.0), 3),
        analysis_source="transcript",
    )


def analyze_audio_features(
    audio: str | Path | bytes | np.ndarray,
    transcript: str,
    *,
    words: Sequence[TranscriptWord] | None = None,
    sample_rate: int | None = None,
    content_type: str | None = None,
    duration_hint: float | None = None,
    min_pause_duration: float = DEFAULT_MIN_PAUSE_SECONDS,
    silence_threshold_db: float = DEFAULT_SILENCE_THRESHOLD_DB,
) -> AudioFeatures:
    """
    Analyze speaking features: WPM, pauses, longest pause, and filler words.

    Falls back to transcript-based estimates when webm/opus cannot be decoded
    (common on Windows without ffmpeg in PATH).
    """
    text = transcript.strip()
    audio_bytes = audio if isinstance(audio, bytes) else None
    suffix = _suffix_from_content_type(content_type)

    temp_paths: list[Path] = []
    try:
        y, sr, temp_paths = _load_audio(
            audio,
            sample_rate=sample_rate,
            suffix=suffix,
        )
    except Exception as exc:
        logger.warning("Audio decode failed (%s), using fallback metrics.", exc)
        return _fallback_features(
            transcript,
            audio_bytes=audio_bytes,
            duration_hint=duration_hint,
            words=words,
        )

    try:
        tokens = [t for t in text.split() if t]
        word_count = len(tokens)
        filler_count = _count_fillers(text)

        duration_seconds = float(librosa.get_duration(y=y, sr=sr))
        duration_seconds = max(duration_seconds, 0.1)

        audio_pauses = _detect_pauses_from_audio(
            y,
            sr,
            min_pause_duration=min_pause_duration,
            silence_threshold_db=silence_threshold_db,
        )
        # A successfully decoded recording is authoritative, including when
        # it contains no detectable internal silence. Timestamp gaps are used
        # only by the transcript fallback path after decode failure.
        pauses = audio_pauses

        pause_count = len(pauses)
        longest_pause = round(max(pauses), 2) if pauses else 0.0
        total_pause_time = round(sum(pauses), 2)
        pause_ratio = round(min(total_pause_time / duration_seconds, 1.0), 3)
        voiced_span = _voiced_span_seconds(y, sr, silence_threshold_db=silence_threshold_db)
        speech_duration = max(voiced_span - total_pause_time, 0.1)
        articulation_rate = round(word_count / (speech_duration / 60.0), 1) if word_count else 0.0
        pitch_median, pitch_variation, energy_variation = _prosody_from_audio(y, sr)

        duration_min = duration_seconds / 60.0
        wpm = round(word_count / duration_min, 1) if word_count else 0.0

        return AudioFeatures(
            wpm=wpm,
            pause_count=pause_count,
            longest_pause=longest_pause,
            filler_count=filler_count,
            duration_seconds=round(duration_seconds, 2),
            word_count=word_count,
            articulation_rate=articulation_rate,
            long_pause_count=sum(pause >= DEFAULT_LONG_PAUSE_SECONDS for pause in pauses),
            total_pause_time=total_pause_time,
            pause_ratio=pause_ratio,
            pitch_median=pitch_median,
            pitch_variation=pitch_variation,
            energy_variation=energy_variation,
            analysis_source="waveform",
            speech_duration_seconds=round(speech_duration, 2),
        )
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)


def acoustic_metrics_to_dict(features: AudioFeatures) -> dict[str, object]:
    """Serialize acoustic metrics without exposing decoder/provider internals."""
    return {
        "duration_seconds": features.duration_seconds,
        "speech": {
            "word_count": features.word_count,
            "wpm": features.wpm,
            "articulation_rate": features.articulation_rate,
        },
        "pauses": {
            "pause_count": features.pause_count,
            "long_pause_count": features.long_pause_count,
            "longest_pause": features.longest_pause,
            "total_pause_time": features.total_pause_time,
            "pause_ratio": features.pause_ratio,
        },
        "fillers": {"count": features.filler_count},
        "prosody": {
            "pitch_median": features.pitch_median,
            "pitch_variation": features.pitch_variation,
            "energy_variation": features.energy_variation,
        },
        "source": features.analysis_source,
    }
