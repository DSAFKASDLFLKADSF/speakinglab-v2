"""Offline Phase 3 pipeline tests with actual WAV decoding and waveform analysis."""

from __future__ import annotations

import io
import json
import math
import sys
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from analysis_jobs import AnalysisJobStore
from providers.asr.base import TranscriptResult, TranscriptWord
from providers.speech_eval.mock_speech_eval import MockSpeechEvaluationProvider


SAMPLE_RATE = 16_000
TRANSCRIPT = "Hello world"
WAVEFORM_SECONDS = 3.2


def _wav_recording() -> bytes:
    """Encode valid PCM WAV with one internal 1.2 second silence region."""
    t = np.arange(SAMPLE_RATE, dtype=np.float64) / SAMPLE_RATE
    tone = np.sin(2 * np.pi * 180 * t) * 0.35
    waveform = np.concatenate([tone, np.zeros(int(1.2 * SAMPLE_RATE)), tone])
    pcm = (waveform * 32767).astype("<i2")
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(SAMPLE_RATE)
            recording.writeframes(pcm.tobytes())
        return buffer.getvalue()


class AcousticPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.audio_bytes = _wav_recording()
        # The ASR words intentionally have continuous timing. The result's
        # internal pause must therefore originate from decoded waveform data.
        self.transcription = TranscriptResult(
            transcript=TRANSCRIPT,
            words=[TranscriptWord("Hello", 0, 0.5), TranscriptWord("world", 0.5, 1.0)],
            duration=WAVEFORM_SECONDS,
            model="fixture:asr",
        )
        self.pronunciation_provider = MockSpeechEvaluationProvider()
        self.scoring_payloads: list[dict] = []
        self.fetch = AsyncMock(return_value=(self.audio_bytes, "audio/wav", len(self.audio_bytes)))
        self.transcribe = AsyncMock(return_value=self.transcription)
        self.evaluate = AsyncMock(side_effect=self._evaluate)
        self.scorer = AsyncMock(side_effect=self._score)
        self.job_store = AnalysisJobStore()
        patches = [
            patch.object(main, "fetch_audio", self.fetch),
            patch.object(main, "transcribe_audio", self.transcribe),
            patch.object(main, "evaluate_speech", self.evaluate),
            patch.object(main, "score_with_glm", self.scorer),
            patch.object(main, "job_store", self.job_store),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.interview = main.InterviewRequest(
            audio_url="https://example.test/fixture.wav",
            prompt="What do you prefer?",
            duration_ms=3200,
        )
        self.listen_repeat = main.ListenRepeatRequest(
            audio_url="https://example.test/fixture.wav",
            reference_text=TRANSCRIPT,
        )

    async def _evaluate(self, audio, content_type, transcription, **kwargs):
        self.assertEqual(audio, self.audio_bytes)
        self.assertEqual(content_type, "audio/wav")
        return self.pronunciation_provider.evaluate(audio, transcript=transcription, **kwargs)

    async def _score(self, prompt):
        payload = json.loads(prompt.user)
        self.scoring_payloads.append(payload)
        if prompt.task == "interview":
            scores = {"topic": 4, "pace": 3, "pronunciation": 4, "grammar": 4}
            summary = "All four dimensions have been scored."
        else:
            scores = {"score": 4}
            summary = "Good match."
        feedback = {"summary": summary, "sections": []}
        return scores, feedback, summary, "fixture:glm", [], None, None

    def _assert_acoustic(self, result):
        acoustic = result["acoustic_metrics"]
        self.assertEqual(acoustic["source"], "waveform")
        self.assertAlmostEqual(acoustic["duration_seconds"], WAVEFORM_SECONDS, delta=0.03)
        self.assertEqual(acoustic["speech"]["word_count"], 2)
        self.assertGreaterEqual(acoustic["pauses"]["pause_count"], 1)
        self.assertGreaterEqual(acoustic["pauses"]["long_pause_count"], 1)
        self.assertGreater(acoustic["pauses"]["total_pause_time"], 0.8)
        self.assertGreater(acoustic["pauses"]["pause_ratio"], 0.2)
        self.assertGreater(
            acoustic["speech"]["articulation_rate"], acoustic["speech"]["wpm"]
        )
        for value in acoustic["prosody"].values():
            self.assertTrue(value is None or math.isfinite(value))
        self.assertEqual(result["pronunciation_metrics"]["provider"], "mock")
        self.assertEqual(result["transcript"], TRANSCRIPT)

    def _assert_scoring_acoustic(self, count):
        self.assertEqual(len(self.scoring_payloads), count)
        for payload in self.scoring_payloads:
            acoustic = payload["acoustic_metrics"]
            self.assertEqual(acoustic["source"], "waveform")
            self.assertGreater(acoustic["pauses"]["pause_ratio"], 0.2)
            self.assertEqual(payload["behavior_metrics"]["pause_count"], acoustic["pauses"]["pause_count"])
            self.assertEqual(payload["pronunciation_metrics"]["provider"], "mock")

    async def test_sync_interview_and_listen_repeat_use_decoded_waveform(self):
        interview = await main.run_interview_analysis(self.interview)
        listen_repeat = await main.run_listen_repeat_analysis(self.listen_repeat)
        for result in [interview.model_dump(), listen_repeat.model_dump()]:
            self._assert_acoustic(result)
        self._assert_scoring_acoustic(2)
        self.assertEqual(self.evaluate.call_args_list[0].kwargs["mode"], "free_speaking")
        self.assertEqual(self.evaluate.call_args_list[1].kwargs["mode"], "reference")

    async def test_benchmark_interview_and_listen_repeat_keep_waveform_metrics(self):
        interview = await main._run_interview_timed(
            main.BenchmarkInterviewItem(**self.interview.model_dump(), title="fixture")
        )
        listen_repeat = await main._run_listen_repeat_timed(
            main.BenchmarkListenRepeatItem(**self.listen_repeat.model_dump(), title="fixture")
        )
        for result in [interview, listen_repeat]:
            self.assertTrue(result.success, result.error)
            self._assert_acoustic(result.result)
            self.assertIn("audio_features", [stage.id for stage in result.stages])
        self._assert_scoring_acoustic(2)

    async def test_async_jobs_store_waveform_metrics_and_scoring_evidence(self):
        interview = await self.job_store.create("interview", self.interview.model_dump(mode="json"))
        listen_repeat = await self.job_store.create("listen_repeat", self.listen_repeat.model_dump(mode="json"))
        await main._run_interview_job(interview.id, self.interview)
        await main._run_listen_repeat_job(listen_repeat.id, self.listen_repeat)
        for job in [interview, listen_repeat]:
            self.assertEqual(job.status, "done", job.error)
            self._assert_acoustic(job.result)
        self._assert_scoring_acoustic(2)


if __name__ == "__main__":
    unittest.main()
