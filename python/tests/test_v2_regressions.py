"""Offline regression cases; no recordings or requests go to external services."""
import asyncio
import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assembly_transcribe as assembly
import glm_client
import main
import neural_tts
from audio_features import features_from_transcription, _detect_pauses_from_word_gaps
from fastapi import HTTPException
from interview_feedback import normalize_interview_feedback
from toefl_rubric import get_toefl_score_prompt
from whisper_transcribe import WhisperWord


class TranscriptionRegressionTests(unittest.TestCase):
    def test_assembly_duration_is_seconds_and_word_timing_is_milliseconds(self):
        self.assertEqual(assembly._duration_seconds({'audio_duration': 45}), 45)
        words = assembly._parse_words({'words': [{'text': 'hello', 'start': 1200, 'end': 1800}]}, 'hello')
        self.assertEqual((words[0].start, words[0].end), (1.2, 1.8))

    def test_invalid_timing_preserves_text_without_crashing(self):
        for invalid in ['bad', float('inf'), float('nan'), -1, True, None]:
            with self.subTest(value=invalid):
                word = assembly._parse_words({'words': [{'text': 'hello', 'start': invalid, 'end': 1200}]}, 'hello')[0]
                self.assertEqual(word.word, 'hello')
                self.assertIsNone(word.start)
                self.assertIsNone(assembly._duration_seconds({'audio_duration': invalid}))

    def test_filler_words_are_requested_from_transcription(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {'id': 'test-only'}
        with patch.object(assembly.requests, 'post', return_value=response) as post:
            assembly._submit_transcript('test-only', 'https://example.test', 'https://example.test/audio', language_code='en', timeout=1)
        self.assertTrue(post.call_args.kwargs['json']['disfluencies'])

    def test_known_continuous_speech_has_zero_pauses(self):
        words = [WhisperWord('One.', 0, 1), WhisperWord('Two.', 1.1, 2)]
        metrics = features_from_transcription('One. Two.', words=words, duration_seconds=2)
        self.assertEqual(metrics.pause_count, 0)
        self.assertEqual(metrics.longest_pause, 0)

    def test_missing_word_timing_does_not_create_a_false_gap(self):
        words = [WhisperWord('One', 0, 1), WhisperWord('two'), WhisperWord('three', 7, 8)]
        self.assertEqual(_detect_pauses_from_word_gaps(words, min_pause_duration=0.3), [])

    def test_placeholder_mode_never_substitutes_for_a_recorded_answer(self):
        with patch.object(main, 'is_transcription_configured', return_value=False), patch.object(main.settings, 'dev_echo_reference', True):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(main.transcribe_audio(b'fixture', 'audio/webm'))
        self.assertEqual(caught.exception.status_code, 503)


class ScoringRegressionTests(unittest.TestCase):
    def test_no_credit_error_is_distinct_from_temporary_rate_limiting(self):
        from openai import RateLimitError
        for body in [{'code': '1113'}, {'error': {'code': '1113'}}]:
            exc = RateLimitError('Unavailable', response=MagicMock(status_code=429), body=body)
            mapped = glm_client._map_openai_error(exc)
            self.assertEqual(mapped.error_code, 'insufficient_quota')
            self.assertEqual(mapped.status_code, 503)
            self.assertIn('credits', main.http_exception_from_glm(mapped).detail)
        limited = RateLimitError('Busy', response=MagicMock(status_code=429), body={'error': {'code': '1302'}})
        self.assertEqual(glm_client._map_openai_error(limited).error_code, 'rate_limit')

    def test_no_credit_error_is_not_retried(self):
        from openai import RateLimitError
        client = MagicMock()
        client.chat.completions.create.side_effect = RateLimitError('Unavailable', response=MagicMock(status_code=429), body={'error': {'code': '1113'}})
        prompt = get_toefl_score_prompt(task='listen_repeat', transcript='Hello.', reference_text='Hello.')
        with patch.object(glm_client, 'OpenAI', return_value=client), patch.object(glm_client.time, 'sleep') as sleep:
            with self.assertRaises(glm_client.GlmApiError) as caught:
                glm_client.call_glm(prompt, api_key='test-only')
        self.assertEqual(caught.exception.error_code, 'insufficient_quota')
        self.assertEqual(client.chat.completions.create.call_count, 1)
        sleep.assert_not_called()
        client.close.assert_called_once()

    def test_missing_and_invalid_scores_are_not_silently_set_to_one(self):
        cases = [{}, {'score': 4}, {'topic': 4}, {'topic': 4, 'pace': 2, 'pronunciation': 3, 'grammar': None}]
        for value in [float('inf'), float('nan'), True, 'bad']:
            cases.append({'topic': value, 'pace': 2, 'pronunciation': 3, 'grammar': 5})
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(glm_client.GlmApiError):
                glm_client._normalize_scores(payload, 'interview')
        with self.assertRaises(glm_client.GlmApiError):
            glm_client._normalize_scores({}, 'listen_repeat')

    def test_valid_score_rounding_and_bounds_are_unchanged(self):
        self.assertEqual(glm_client._normalize_scores({'topic': 4, 'pace': 2, 'pronunciation': 3, 'grammar': 5}, 'interview'), {'topic': 4, 'pace': 2, 'pronunciation': 3, 'grammar': 5})
        self.assertEqual(glm_client._normalize_scores({'score': 4}, 'listen_repeat'), {'score': 4})

    def test_runtime_glm_settings_are_honored_and_client_is_closed(self):
        client = MagicMock()
        client.chat.completions.create.return_value.choices[0].message.content = json.dumps({'score': 4})
        prompt = get_toefl_score_prompt(task='listen_repeat', transcript='Hello.', reference_text='Hello.')
        with patch.object(glm_client, 'OpenAI', return_value=client) as constructor:
            result = glm_client.call_glm(prompt, api_key='test-only', timeout=30, max_output_tokens=3210, thinking='enabled')
        self.assertEqual(result.scores['score'], 4)
        self.assertEqual(client.chat.completions.create.call_args.kwargs['max_tokens'], 3210)
        self.assertNotIn('extra_body', client.chat.completions.create.call_args.kwargs)
        self.assertLessEqual(client.chat.completions.create.call_args.kwargs['timeout'], 30)
        self.assertEqual(constructor.call_args.kwargs['max_retries'], 0)
        client.close.assert_called_once()

    def test_timed_out_call_does_not_start_a_second_full_timeout_window(self):
        from openai import APITimeoutError
        client = MagicMock()
        client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
        prompt = get_toefl_score_prompt(task='listen_repeat', transcript='Hello.', reference_text='Hello.')
        with patch.object(glm_client, 'OpenAI', return_value=client), patch.object(glm_client.time, 'monotonic', side_effect=[0, 1, 31, 31]), patch.object(glm_client.time, 'sleep'):
            with self.assertRaises(glm_client.GlmApiError):
                glm_client.call_glm(prompt, api_key='test-only', timeout=30)
        self.assertEqual(client.chat.completions.create.call_count, 1)
        client.close.assert_called_once()

    def test_explicitly_unavailable_feedback_is_not_reported_as_error_free(self):
        raw = {'content_feedback': {'on_topic': {'status': 'unavailable', 'issues': []}}}
        result = normalize_interview_feedback(raw, transcript='Hello.', hesitation=None)
        self.assertEqual(result['content_feedback']['on_topic']['status'], 'unavailable')


class SpeechCacheRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_synthesis_cannot_poison_the_cache(self):
        import edge_tts
        async def fail_after_partial_write(filename):
            Path(filename).write_bytes(b'partial' * 100)
            raise RuntimeError('test failure')
        fake = MagicMock()
        fake.save = fail_after_partial_write
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'speech.mp3'
            with patch.object(edge_tts, 'Communicate', return_value=fake):
                with self.assertRaises(RuntimeError):
                    await neural_tts.synthesize_to_file('Test.', dest)
            self.assertFalse(dest.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_pitch_is_part_of_the_cache_identity(self):
        self.assertNotEqual(neural_tts.cache_key('Test.', 'voice', '-10%', '+0Hz'), neural_tts.cache_key('Test.', 'voice', '-10%', '+20Hz'))


if __name__ == '__main__':
    unittest.main()
