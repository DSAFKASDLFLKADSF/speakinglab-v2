"""Neural English TTS via Microsoft Edge voices (TOEFL-style clarity)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

# Clear American English — similar to computer-delivered TOEFL prompts
DEFAULT_VOICE = "en-US-JennyNeural"
# Slightly slower for academic listen-and-repeat
DEFAULT_RATE = "-10%"
DEFAULT_PITCH = "+0Hz"

CACHE_DIR = Path(__file__).resolve().parent / "cache" / "tts"


def cache_key(text: str, voice: str, rate: str, pitch: str = DEFAULT_PITCH) -> str:
    raw = f"{voice}|{rate}|{text.strip()}"
    if pitch != DEFAULT_PITCH:
        raw += f"|{pitch}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path(text: str, voice: str = DEFAULT_VOICE, rate: str = DEFAULT_RATE, pitch: str = DEFAULT_PITCH) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{cache_key(text, voice, rate, pitch)}.mp3"


async def synthesize_to_file(
    text: str,
    dest: Path,
    *,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
) -> Path:
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError(
            "edge-tts is not installed. Run: pip install edge-tts"
        ) from exc

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Cannot synthesize empty text.")

    dest.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(cleaned, voice, rate=rate, pitch=pitch)
    temporary = dest.with_name(f"{dest.stem}.{uuid4().hex}.tmp.mp3")
    try:
        await communicate.save(str(temporary))
        if not temporary.is_file() or temporary.stat().st_size <= 512:
            raise RuntimeError("Speech synthesis returned empty audio.")
        temporary.replace(dest)
    finally:
        temporary.unlink(missing_ok=True)
    logger.info("Neural TTS saved path=%s chars=%s", dest.name, len(cleaned))
    return dest


async def synthesize_cached(
    text: str,
    *,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
) -> Path:
    path = cache_path(text, voice, rate, pitch)
    if path.is_file() and path.stat().st_size > 512:
        return path
    return await synthesize_to_file(text, path, voice=voice, rate=rate, pitch=pitch)


def synthesize_cached_sync(
    text: str,
    *,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = DEFAULT_PITCH,
) -> Path:
    return asyncio.run(
        synthesize_cached(text, voice=voice, rate=rate, pitch=pitch)
    )
