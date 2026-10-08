"""Offline regression tests: python -m unittest discover -s python/tests -v."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from interview_feedback import detect_hesitation, normalize_interview_feedback
from toefl_rubric import get_toefl_score_prompt
from whisper_transcribe import WhisperTranscription, WhisperWord as W
from glm_client import call_glm
import main


WORDS = [W('I', 0, .2), W('prefer', .3, .7), W('studying', .8, 1.2), W('alone.', 1.3, 2), W('It', 7, 7.3), W('helps.', 7.4, 8)]
TRANSCRIPT = ' '.join(w.word for w in WORDS)
SCORES = {'topic': 4, 'pace': 2, 'pronunciation': 3, 'grammar': 5}


def content(evidence='I prefer studying alone.'):
    return {'problem': 'The reason is not explained.', 'evidence': evidence,
            'why_it_matters': 'The causal link is missing.',
            'imitable_improvement': 'I can control my pace and spend more time on difficult topics.'}


def language(original='It helps.'):
    return {'original': original, 'problem': 'The benefit is vague.',
            'better_version': 'It helps me concentrate.', 'pattern_to_imitate': 'help someone + verb'}


def feedback():
    return {
        'content_feedback': {'on_topic': {'issues': []}, 'reasoning': {'issues': [content()]}, 'example_detail': {'issues': []}},
        'language_feedback': {'issues': []},
        'hesitation_recovery': {'detected': True, 'timestamp': 999, 'context_before_hesitation': 'Invented', 'continuation_options': [
            {'strategy': 'explain_why', 'text': 'I can choose how much time to spend on each topic.'},
            {'strategy': 'give_consequence', 'text': 'As a result, I have more time for difficult topics.'},
            {'strategy': 'give_example', 'text': 'For example, I could review a difficult chapter twice.'},
        ]},
    }


class DetectionTests(unittest.TestCase):
    def test_threshold_and_context(self):
        event = detect_hesitation(WORDS)
        self.assertEqual(event['timestamp'], 2)
        self.assertEqual(event['duration_seconds'], 5)
        self.assertEqual(event['context_before_hesitation'], 'I prefer studying alone.')
        self.assertNotIn('helps', event['context_before_hesitation'])
        self.assertIsNone(detect_hesitation(WORDS[:4] + [W('It', 6.99, 7.1)]))

    def test_no_guess_without_timing(self):
        self.assertIsNone(detect_hesitation([W(t) for t in 'I prefer studying alone um um um um um'.split()]))
        self.assertIsNone(detect_hesitation(WORDS[:4] + [W('untimed')] + WORDS[4:]))

    def test_timed_filler_sequence(self):
        words = WORDS[:4] + [W('um', 2.1, 3.7), W('uh', 3.8, 5.4), W('you', 5.5, 5.8), W('know', 5.8, 7.2)]
        event = detect_hesitation(words)
        self.assertEqual(event['kind'], 'fillers')
        self.assertAlmostEqual(event['duration_seconds'], 5.1)
        self.assertEqual(event['context_before_hesitation'], 'I prefer studying alone.')

    def test_short_fillers_and_lexical_like(self):
        self.assertIsNone(detect_hesitation(WORDS[:4] + [W('um', 2.1, 2.4), W('uh', 2.5, 2.8)]))
        self.assertIsNone(detect_hesitation(WORDS[:4] + [W('like', 2.1, 7.3), W('math', 7.4, 8)]))

    def test_fillers_separated_by_content_are_not_a_run(self):
        self.assertIsNone(detect_hesitation(WORDS[:4] + [W('um', 2.1, 3.5), W('math', 3.6, 4), W('uh', 4.1, 7.2)]))

    def test_only_strongest_event(self):
        event = detect_hesitation(WORDS + [W('For', 16, 16.3), W('example', 16.4, 17)])
        self.assertEqual(event['timestamp'], 8)
        self.assertEqual(event['duration_seconds'], 8)

    def test_bad_chronology_nonfinite_and_zero_times(self):
        for word in [W('x', float('nan'), 99), W('x', 7, float('inf')), W('x', -1, 8), W('x', 7, 7)]:
            with self.subTest(word=word):
                self.assertIsNone(detect_hesitation(WORDS[:4] + [word]))
        self.assertIsNone(detect_hesitation([WORDS[1], WORDS[0]] + WORDS[2:]))

    def test_initial_idle_and_end_of_recording_not_detected(self):
        self.assertIsNone(detect_hesitation([W('Hello', 10, 11), W('there', 11.1, 12)]))
        self.assertIsNone(detect_hesitation(WORDS[:4]))
        self.assertIsNone(detect_hesitation([W('um', 0, 2), W('uh', 2.1, 5.3)]))


class NormalizationTests(unittest.TestCase):
    def test_caps_and_evidence(self):
        raw = feedback()
        quotes = ['I', 'prefer', 'studying', 'alone.', 'It']
        for group in raw['content_feedback'].values():
            group['issues'] = [content(q) for q in quotes]
        raw['language_feedback']['issues'] = [language(q) for q in quotes]
        result = normalize_interview_feedback(raw, transcript=TRANSCRIPT, hesitation=None)
        self.assertTrue(all(len(g['issues']) == 2 for g in result['content_feedback'].values()))
        self.assertEqual(len(result['language_feedback']['issues']), 3)
        self.assertFalse(result['hesitation_recovery']['detected'])

    def test_empty_is_complete_missing_is_unavailable(self):
        valid = normalize_interview_feedback(feedback(), transcript=TRANSCRIPT, hesitation=None)
        self.assertEqual(valid['content_feedback']['on_topic']['status'], 'complete')
        for bad in [None, [], 'oops', {'content_feedback': None, 'language_feedback': {'issues': 'bad'}}]:
            result = normalize_interview_feedback(bad, transcript=TRANSCRIPT, hesitation=None)
            self.assertEqual(result['content_feedback']['on_topic']['status'], 'unavailable')
            self.assertEqual(result['language_feedback']['status'], 'unavailable')
            main.InterviewFeedbackBlock(**result)

    def test_invalid_or_invented_quotes_not_displayed(self):
        raw = feedback()
        raw['content_feedback']['reasoning']['issues'] += [content('invented quote'), {'problem': 'incomplete'}, None]
        raw['language_feedback']['issues'] = [dict(language(), pattern_to_imitate=['not', 'text'])]
        result = normalize_interview_feedback(raw, transcript=TRANSCRIPT, hesitation=None)
        self.assertEqual(len(result['content_feedback']['reasoning']['issues']), 1)
        self.assertEqual(result['content_feedback']['reasoning']['status'], 'unavailable')
        self.assertEqual(result['language_feedback']['issues'], [])

    def test_server_owns_timing_and_context(self):
        result = normalize_interview_feedback(feedback(), transcript=TRANSCRIPT, hesitation=detect_hesitation(WORDS))
        recovery = result['hesitation_recovery']
        self.assertEqual(recovery['timestamp'], 2)
        self.assertEqual(recovery['context_before_hesitation'], 'I prefer studying alone.')
        self.assertEqual(len(recovery['continuation_options']), 3)

    def test_bad_options_do_not_break_scores_or_fabricate_advice(self):
        raw = feedback()
        raw['hesitation_recovery']['continuation_options'] = [None, {'strategy': 'explain_why', 'text': 'One. Two. Three.'}]
        recovery = normalize_interview_feedback(raw, transcript=TRANSCRIPT, hesitation=detect_hesitation(WORDS))['hesitation_recovery']
        self.assertTrue(recovery['detected'])
        self.assertEqual(recovery['continuation_options'], [])


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payload = {**SCORES, 'scoreSummary': 'Your pace was too slow.', 'feedback': feedback(),
                        'paceFeedback': {'summary': 'Unwanted delivery advice'},
                        'pronunciationFeedback': {'summary': 'Unwanted pronunciation advice'}}
        self.client = MagicMock()
        self.client.chat.completions.create.side_effect = lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload)))])
        self.patches = [patch('glm_client.OpenAI', return_value=self.client),
                        patch('main.resolve_glm_api_key', return_value='test-only'),
                        patch('main.fetch_audio', new=AsyncMock(return_value=(b'fixture', 'audio/webm', 7))),
                        patch('main.transcribe_audio', new=AsyncMock(return_value=WhisperTranscription(TRANSCRIPT, WORDS, duration=8)))]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.body = main.InterviewRequest(audio_url='https://example.com/test.webm', prompt='Do you prefer studying alone?', duration_ms=8000)

    async def test_normal_benchmark_and_async_job_preserve_all_scores(self):
        normal = await main.run_interview_analysis(self.body)
        benchmark = await main._run_interview_timed(main.BenchmarkInterviewItem(**self.body.model_dump(), title='fixture'))
        job = await main.job_store.create('interview', self.body.model_dump(mode='json'))
        await main._run_interview_job(job.id, self.body)
        for result in [normal.model_dump(), benchmark.result, job.result]:
            self.assertEqual(result['scores'], SCORES)
            self.assertEqual(result['transcript'], TRANSCRIPT)
            self.assertEqual(result['feedback']['hesitation_recovery']['timestamp'], 2)
            self.assertEqual(len(result['feedback']['hesitation_recovery']['continuation_options']), 3)
            self.assertIsNone(result['pace_feedback'])
            self.assertIsNone(result['pronunciation_feedback'])
            self.assertEqual(result['score_summary'], 'All four dimensions have been scored.')
        self.assertEqual(job.status, 'done')
        self.assertEqual(self.client.chat.completions.create.call_count, 3)
        user = json.loads(self.client.chat.completions.create.call_args.kwargs['messages'][1]['content'])
        self.assertEqual(user['hesitation_event']['context_before_hesitation'], 'I prefer studying alone.')
        self.assertEqual(user['behavior_metrics'], main.features_to_dict(main.behavior_features_from_transcription(WhisperTranscription(TRANSCRIPT, WORDS, duration=8), duration_hint=8)))

    async def test_malformed_feedback_preserves_scoring(self):
        for malformed in [None, [], {}, {'content_feedback': {'on_topic': {'issues': [False]}}, 'hesitation_recovery': 'bad'}]:
            self.payload['feedback'] = malformed
            result = await main.run_interview_analysis(self.body)
            self.assertEqual(result.scores.model_dump(), SCORES)
            self.assertEqual(result.feedback.content_feedback.on_topic.status, 'unavailable')

    def test_listen_repeat_output_unchanged(self):
        self.payload = {'score': 4, 'scoreSummary': 'Good match.', 'feedback': {'summary': 'Good match.', 'sections': [{'title': 'Fluency', 'content': 'Keep a steady pace.'}]}}
        prompt = get_toefl_score_prompt(task='listen_repeat', transcript='Hello.', reference_text='Hello.')
        result = call_glm(prompt, api_key='test-only')
        self.assertEqual(result.scores, {'score': 4})
        self.assertEqual(result.feedback, self.payload['feedback'])
        self.assertNotIn('hesitation_event', json.loads(prompt.user))


if __name__ == '__main__':
    unittest.main()
