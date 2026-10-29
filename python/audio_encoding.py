"""Bounded in-memory conversion for Tencent's 16 kHz mono PCM interfaces."""

from __future__ import annotations

import io
import shutil
import subprocess
import wave

SAMPLE_RATE = 16_000
MAX_AUDIO_SECONDS = 180
MAX_PCM_BYTES = SAMPLE_RATE * 2 * MAX_AUDIO_SECONDS


class AudioEncodingError(ValueError):
    pass


def to_pcm16(audio: bytes) -> bytes:
    """Decode a browser recording to signed little-endian 16-bit mono PCM.

    Already compatible WAV files use the standard-library fast path. Other
    containers (including WebM/Opus) are decoded by ffmpeg without temp files.
    Oversized recordings fail explicitly instead of being silently truncated.
    """
    if not audio:
        raise AudioEncodingError("Recording is empty.")
    pcm = None
    try:
        with wave.open(io.BytesIO(audio), "rb") as recording:
            if (recording.getnchannels(), recording.getsampwidth(),
                    recording.getframerate(), recording.getcomptype()) == (1, 2, SAMPLE_RATE, "NONE"):
                pcm = recording.readframes(SAMPLE_RATE * MAX_AUDIO_SECONDS + 1)
    except (wave.Error, EOFError):
        pass
    if pcm is None:
        if not shutil.which("ffmpeg"):
            raise AudioEncodingError("ffmpeg is required to convert this recording for Tencent.")
        try:
            result = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-i", "pipe:0", "-t", str(MAX_AUDIO_SECONDS + 1), "-vn",
                 "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
                 "-f", "s16le", "pipe:1"],
                input=audio, capture_output=True, check=True, timeout=30,
            )
            pcm = result.stdout
        except (subprocess.SubprocessError, OSError) as exc:
            raise AudioEncodingError("Unable to decode the recording for Tencent.") from exc
    if len(pcm) > MAX_PCM_BYTES:
        raise AudioEncodingError(f"Recording exceeds the {MAX_AUDIO_SECONDS}-second analysis limit.")
    if not pcm or len(pcm) % 2:
        raise AudioEncodingError("Recording contains no complete PCM audio samples.")
    return pcm


def pcm_to_wav(pcm: bytes) -> bytes:
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(SAMPLE_RATE)
            recording.writeframes(pcm)
        return buffer.getvalue()
