"""Real audio conversion tests; cloud providers are never called."""

import io
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio_encoding import AudioEncodingError, MAX_PCM_BYTES, pcm_to_wav, to_pcm16


class AudioEncodingTests(unittest.TestCase):
    def test_canonical_wav_round_trip_preserves_pcm(self):
        pcm = b"\x01\x02" * 16000
        self.assertEqual(to_pcm16(pcm_to_wav(pcm)), pcm)

    def test_oversize_recordings_are_rejected_instead_of_truncated(self):
        with self.assertRaisesRegex(AudioEncodingError, "limit"):
            to_pcm16(pcm_to_wav(b"\0" * (MAX_PCM_BYTES + 2)))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required for real WebM fixture")
    def test_browser_webm_opus_is_converted_to_16khz_mono(self):
        # Generate actual stereo 48 kHz WebM/Opus, as a browser may record it.
        encoded = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "sine=frequency=180:sample_rate=48000:duration=1",
             "-ac", "2", "-c:a", "libopus", "-f", "webm", "pipe:1"],
            check=True, capture_output=True, timeout=10,
        ).stdout
        pcm = to_pcm16(encoded)
        self.assertAlmostEqual(len(pcm) / 32000, 1, delta=0.03)
        self.assertTrue(any(pcm))
        with wave.open(io.BytesIO(pcm_to_wav(pcm)), "rb") as recording:
            self.assertEqual((recording.getnchannels(), recording.getsampwidth(), recording.getframerate()), (1, 2, 16000))


if __name__ == "__main__":
    unittest.main()
