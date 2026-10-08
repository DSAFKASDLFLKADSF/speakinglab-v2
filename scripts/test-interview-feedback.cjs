/* Offline tests using the project's existing TypeScript and React dependencies. */
const assert = require('node:assert/strict');
const test = require('node:test');
require('./test-register.cjs');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { normalizeInterviewFeedback } = require('../lib/interviewDetailedFeedback');
const { finalizeInterviewAnalysis } = require('../lib/finalizeInterviewAnalysis');
const { InterviewFeedbackPanel } = require('../components/exam/InterviewFeedbackPanel');
const { BenchmarkScoreResult } = require('../components/admin/BenchmarkScoreResult');
const { interviewScoresToBand } = require('../components/InterviewScoreCard');
const { rawScoreToSpeakingBand } = require('../lib/toeflSpeakingBand');

const scores = { topic: 4, pace: 2, pronunciation: 3, grammar: 5 };
const metrics = { speaking_rate_wpm: 120, pause_count: 1, filler_word_count: 0, longest_pause_seconds: 5 };
const body = { audioUrl: 'https://example.com/audio.webm', storagePath: 'test.webm', prompt: 'Do you prefer studying alone?', responseSeconds: 45, durationMs: 12000 };
const issue = { problem: 'The causal link is missing.', evidence: 'Studying alone is efficient.', why_it_matters: 'The listener needs to understand why.', imitable_improvement: 'I can choose how much time to spend on each topic.' };
const feedback = {
  summary: 'Review content and language.', sections: [],
  content_feedback: { on_topic: { status: 'complete', issues: [] }, reasoning: { status: 'complete', issues: [issue] }, example_detail: { status: 'complete', issues: [] } },
  language_feedback: { status: 'complete', issues: [{ original: 'It let me study.', problem: 'Use the correct verb form.', better_version: 'It lets me study.', pattern_to_imitate: 'It lets me + verb' }] },
  hesitation_recovery: { detected: true, timestamp: 7.5, duration_seconds: 5.2, kind: 'pause', timing_source: 'word_timestamps', context_before_hesitation: 'Studying alone is efficient.', continuation_options: [{ strategy: 'explain_why', text: 'I can work at my own pace.' }, { strategy: 'give_example', text: 'For example, I could review a difficult chapter twice.' }] },
};
function pythonResult(value = feedback) {
  return { transcript: 'Studying alone is efficient. It let me study.', scores, score_summary: 'All four dimensions have been scored.', metrics, feedback: value };
}
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));

test('finalizer retains full scores, metrics, transcript and new fields', async () => {
  const result = await finalizeInterviewAnalysis(body, pythonResult());
  assert.deepEqual(result.scores, scores);
  assert.equal(result.transcript, pythonResult().transcript);
  assert.equal(result.metrics.longestPauseSeconds, 5);
  assert.equal(result.feedback.content_feedback.reasoning.issues.length, 1);
  assert.equal(result.feedback.hesitation_recovery.continuation_options.length, 2);
  assert.equal(result.persisted, false);
  assert.equal(interviewScoresToBand(result.scores), 4);
  // Both delivery scores continue to influence the overall band.
  assert.notEqual(interviewScoresToBand({ ...scores, pace: 5 }), interviewScoresToBand(scores));
  assert.notEqual(interviewScoresToBand({ ...scores, pronunciation: 1 }), interviewScoresToBand(scores));
});

test('existing band conversion boundaries are preserved', () => {
  assert.equal(rawScoreToSpeakingBand(1), 1);
  assert.equal(rawScoreToSpeakingBand(3), 3.5);
  assert.equal(rawScoreToSpeakingBand(5), 6);
});

test('page retains all score bars, transcript and playback; only requested diagnostics appear', async () => {
  const result = await finalizeInterviewAnalysis(body, pythonResult());
  result.paceFeedback = { summary: 'Your pace was too slow.', suggestion: 'Speak faster.' };
  result.pronunciationFeedback = { summary: 'Your intonation was unnatural.', suggestion: 'Change your rhythm.' };
  const html = render(InterviewFeedbackPanel, { question: body.prompt, analysis: result, audioUrl: body.audioUrl, defaultOpen: true });
  for (const text of ['Topic Development', 'Pace &amp; Pauses', 'Pronunciation &amp; Rhythm', 'Grammar &amp; Vocabulary', 'What you said', result.transcript, '<audio', 'Problem', 'Evidence', 'Why it matters', 'Imitable improvement', 'Original', 'Better version', 'Pattern to imitate', 'How you could continue', '0:07.5']) assert.ok(html.includes(text), text);
  assert.ok(html.indexOf('A. On-topic') < html.indexOf('B. Reasoning'));
  assert.ok(html.indexOf('B. Reasoning') < html.indexOf('C. Example'));
  assert.ok(!html.includes('Speak faster'));
  assert.ok(!html.includes('intonation was unnatural'));
  assert.ok(!html.includes('Review pace'));
});

test('malformed and legacy feedback cannot crash or fabricate a clean assessment', async () => {
  for (const bad of [undefined, null, [], 'bad', {}, { content_feedback: { on_topic: { issues: [null, 1, {}], status: 'complete' } }, language_feedback: { issues: 'bad' } }]) {
    const result = await finalizeInterviewAnalysis(body, pythonResult(bad));
    // Explicit assignment covers undefined rather than the fixture's default argument.
    result.feedback = bad;
    const html = render(InterviewFeedbackPanel, { question: body.prompt, analysis: result });
    assert.ok(html.includes('unavailable for this attempt'));
    assert.ok(html.includes('Pace &amp; Pauses'));
    assert.ok(!html.includes('How you could continue'));
    assert.deepEqual(result.scores, scores);
  }
});

test('empty reviewed groups report no major issues; absent groups do not', () => {
  const normalized = normalizeInterviewFeedback(feedback);
  assert.equal(normalized.content_feedback.on_topic.status, 'complete');
  assert.equal(normalizeInterviewFeedback({}).content_feedback.on_topic.status, 'unavailable');
});

test('UI bounds issues and rejects malformed hesitation metadata', () => {
  const raw = structuredClone(feedback);
  raw.content_feedback.reasoning.issues = Array(8).fill(issue);
  raw.language_feedback.issues = Array(8).fill(raw.language_feedback.issues[0]);
  assert.equal(normalizeInterviewFeedback(raw).content_feedback.reasoning.issues.length, 2);
  assert.equal(normalizeInterviewFeedback(raw).language_feedback.issues.length, 3);
  for (const event of [{ detected: true }, { ...raw.hesitation_recovery, duration_seconds: 4.99 }, { ...raw.hesitation_recovery, timestamp: NaN }, { ...raw.hesitation_recovery, detected: false }]) {
    assert.equal(normalizeInterviewFeedback({ ...raw, hesitation_recovery: event }).hesitation_recovery.detected, false);
  }
});

test('detected event with bad AI options has honest fallback', async () => {
  const raw = structuredClone(feedback);
  raw.hesitation_recovery.continuation_options = [null, { strategy: 'explain_why', text: ['bad'] }];
  const result = await finalizeInterviewAnalysis(body, pythonResult(raw));
  const html = render(InterviewFeedbackPanel, { question: body.prompt, analysis: result });
  assert.ok(html.includes('How you could continue'));
  assert.ok(html.includes('Continuation suggestions are unavailable'));
});

test('benchmark uses same diagnostic view and preserves all raw scores', () => {
  const html = render(BenchmarkScoreResult, { kind: 'interview', result: pythonResult() });
  for (const text of ['Topic 4/5', 'Pace 2/5', 'Pronunciation 3/5', 'Grammar 5/5', 'How you could continue', 'Imitable improvement']) assert.ok(html.includes(text), text);
});

const { ExamScoreSummary } = require('../components/exam/ExamScoreSummary');
const { formatAnalysisError, buildBatchAnalysisErrorMessage } = require('../lib/examRecordings');
const emptySummary = { sessionId: 'test', sessionTheme: 'Test', listenRepeat: [], interview: [], listenRepeatAvg: 0, interviewAvg: 0, overallScore: 0 };

test('all-failed analysis and old zero-score summaries never display a zero grade', () => {
  for (const summary of [null, emptySummary]) {
    const html = render(ExamScoreSummary, { summary, scoringRequested: true, recordingCount: 4, missingAnalysisCount: 4 });
    assert.ok(html.includes('Scores and feedback unavailable'));
    assert.ok(html.includes('4 recordings saved'));
    assert.ok(!html.includes('0.0/6'));
    assert.ok(!html.includes('Scoring was not requested'));
  }
});

test('unrequested scoring and partial/complete scores have different honest labels', () => {
  const unrequested = render(ExamScoreSummary, { summary: null, scoringRequested: false, recordingCount: 4, missingAnalysisCount: 4 });
  assert.ok(unrequested.includes('Scoring was not requested'));
  const summary = { ...emptySummary, interview: [{}], interviewAvg: 4.5, overallScore: 4.5 };
  const partial = render(ExamScoreSummary, { summary, scoringRequested: true, recordingCount: 4, missingAnalysisCount: 3 });
  assert.ok(partial.includes('Partial Speaking score'));
  assert.ok(partial.includes('4.5/6'));
  assert.ok(!partial.includes('Overall Speaking'));
  const complete = render(ExamScoreSummary, { summary, scoringRequested: true, recordingCount: 1, missingAnalysisCount: 0 });
  assert.ok(complete.includes('Overall Speaking'));
  assert.ok(complete.includes('4.5/6'));
});

test('service failure is described once without question-type headings', () => {
  const names = ['Personal Recall', 'Preference', 'Opinion', 'Policy'];
  const raw = 'Cannot reach Python API at http://localhost:8000. Start it: cd python && uvicorn main:app';
  const message = buildBatchAnalysisErrorMessage(names.map(title => ({ title, message: raw })), 0, 4);
  assert.ok(message.startsWith('0 of 4 questions scored.'));
  assert.equal(message.split('analysis service could not be reached').length, 2);
  assert.ok(names.every(name => !message.includes(name)));
  assert.ok(!message.includes('8000'));
  assert.equal(formatAnalysisError(formatAnalysisError(raw)), formatAnalysisError(raw));
  assert.ok(formatAnalysisError('PYTHON_SPEECH_API_URL is not configured.').includes('analysis service could not be reached'));
});

test('the two exact feedback criteria are headings, with full scoring kept separately', async () => {
  const analysis = await finalizeInterviewAnalysis(body, pythonResult());
  const html = render(InterviewFeedbackPanel, { question: body.prompt, analysis, defaultOpen: true });
  for (const text of ['The response is on topic and well elaborated.', 'A range of accurate grammar and vocabulary allows clear expression of precise meanings.']) {
    assert.ok(html.includes(`>${text}</h4>`));
  }
  assert.ok(html.indexOf('Feedback criterion 1') < html.indexOf('View all scoring dimensions'));
  assert.ok(html.includes('<summary class="cursor-pointer text-sm font-medium text-slate-700">View all scoring dimensions</summary>'));
});

test('local startup handles loopback and remote configuration without changing deployment settings', async () => {
  const { speechServiceConfig, speechServiceReady } = await import('./dev-with-speech.mjs');
  assert.equal(speechServiceConfig('http://localhost:8000').baseUrl, 'http://127.0.0.1:8000');
  assert.equal(speechServiceConfig('http://localhost:8000').canStartLocally, true);
  assert.equal(speechServiceConfig('https://api.example.com/speech').canStartLocally, false);
  assert.equal(speechServiceConfig('https://api.example.com/speech').healthUrl, 'https://api.example.com/speech/health');
  assert.throws(() => speechServiceConfig('ftp://localhost:8000'));
  assert.throws(() => speechServiceConfig('http://user:secret@localhost:8000'));
  const config = speechServiceConfig();
  assert.equal(await speechServiceReady(config, async () => ({ ok: true, json: async () => ({ status: 'ok', service: 'ai-speaking-trainer-python' }) })), true);
  assert.equal(await speechServiceReady(config, async () => ({ ok: true, json: async () => ({ status: 'ok', service: 'other' }) })), false);
  assert.equal(await speechServiceReady(config, async () => { throw new Error('ECONNREFUSED'); }), false);
});
