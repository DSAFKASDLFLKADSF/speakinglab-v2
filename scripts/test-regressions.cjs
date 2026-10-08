require('./test-register.cjs');
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { analysisRequestError } = require('../lib/validateAnalysisRequest');
const { finalizeInterviewAnalysis } = require('../lib/finalizeInterviewAnalysis');
const { getPracticeHistory } = require('../lib/getPracticeHistory');
const { interviewScoresFromCloud } = require('../lib/unifiedHistory');
const { computeStreak } = require('../lib/growthStats');
const { buildAudioStoragePath } = require('../lib/audioStorage');
const { sanitizeRestoredStage } = require('../lib/examSessionPersistence');
const { formatAnalysisError } = require('../lib/examRecordings');
const { pollAnalysisJob } = require('../lib/pollAnalysisJob');
const { addLocalHistoryEntry, getLocalHistory } = require('../lib/localHistory');
const { InterviewDetailedFeedback } = require('../components/interview/InterviewDetailedFeedback');
const { HistoryEntryDetail } = require('../components/dashboard/HistoryEntryDetail');

const scores = { topic: 4, pace: 2, pronunciation: 3, grammar: 5 };
const result = { transcript: 'I prefer studying alone.', duration_seconds: 45, scores,
  score_summary: 'All four dimensions have been scored.', metrics: { speaking_rate_wpm: 120, pause_count: 1, filler_word_count: 0, longest_pause_seconds: 5 },
  feedback: { content_feedback: { on_topic: { status: 'complete', issues: [] } } } };
const body = { audioUrl: 'http://localhost:3001/api/audio/file?path=test.webm', storagePath: 'test.webm', prompt: 'How do you study?', responseSeconds: 45, durationMs: 0 };

test('invalid request bodies receive 400 before contacting the analysis service', async () => {
  for (const name of ['analyze-interview', 'analyze-speech']) {
    const { POST } = require(`../app/api/${name}/route`);
    for (const raw of ['null', '[]', '{', '{"audioUrl":42}', '{}']) {
      const res = await POST(new Request('http://localhost/api/test', { method: 'POST', body: raw }));
      assert.equal(res.status, 400);
    }
  }
});

test('analysis input rejects invalid durations and non-HTTP URLs', () => {
  assert.equal(analysisRequestError(body, 'interview'), null);
  for (const change of [{ durationMs: NaN }, { durationMs: -1 }, { responseSeconds: 0 }, { responseSeconds: 4.5 }, { audioUrl: 'file:///secret' }]) {
    assert.ok(analysisRequestError({ ...body, ...change }, 'interview'));
  }
});

test('missing scores, nonfinite metrics, and empty transcripts cannot become a grade', async () => {
  for (const bad of [null, {}, { ...result, scores: { topic: 4 } }, { ...result, transcript: '' }, { ...result, metrics: { ...result.metrics, speaking_rate_wpm: Infinity } }]) {
    await assert.rejects(finalizeInterviewAnalysis(body, bad), /invalid scores or transcript/);
  }
});

test('repeated finalization saves one record, preserving all dimensions, duration and feedback', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'speaking-v2-test-'));
  const old = process.env.DATA_DIR;
  process.env.DATA_DIR = dir;
  try {
    await Promise.all([1, 2].map(() => finalizeInterviewAnalysis(body, result, 'test-user', 'same-job')));
    const history = await getPracticeHistory('test-user');
    assert.equal(history.total, 1);
    assert.equal(history.items[0].audio.durationSeconds, 45);
    assert.deepEqual(interviewScoresFromCloud(history.items[0]), scores);
    assert.equal(history.items[0].score.feedback.content_feedback.on_topic.status, 'complete');
    assert.equal(interviewScoresFromCloud({ ...history.items[0], kind: 'listen_repeat' }), null);
  } finally {
    if (old === undefined) delete process.env.DATA_DIR; else process.env.DATA_DIR = old;
    await fs.rm(dir, { recursive: true, force: true });
  }
});

test('full or disabled local storage does not crash results; corrupt rows are ignored', () => {
  global.window = { localStorage: { getItem: () => '[null,1,{}]', setItem: () => { throw new Error('QuotaExceeded'); } } };
  try {
    assert.deepEqual(getLocalHistory(), []);
    assert.doesNotThrow(() => addLocalHistoryEntry({ mode: 'interview', title: 'Test', summary: 'Scored', interviewScores: scores }));
  } finally { delete global.window; }
});

test('re-scoring the same attempt replaces its local history entry', () => {
  let value = '[]';
  global.window = { localStorage: { getItem: () => value, setItem: (_key, next) => { value = next; } } };
  try {
    for (const summary of ['first', 'second']) addLocalHistoryEntry({ id: 'same-attempt', mode: 'interview', title: 'Test', summary, interviewScores: scores });
    assert.equal(getLocalHistory().length, 1);
    assert.equal(getLocalHistory()[0].summary, 'second');
  } finally { delete global.window; }
});

test('refresh during an unfinished question returns to its instructions, not the next question', () => {
  for (const kind of ['iv', 'lr']) {
    const stage = sanitizeRestoredStage(`${kind}_recording`, [{ kind: kind === 'iv' ? 'interview' : 'listen_repeat', questionId: 'one', promptId: 'one' }], null, { mode: kind === 'iv' ? 'interview' : 'listen_repeat', lrIndex: 1, ivIndex: 1, lrTotal: 7, ivTotal: 4 });
    assert.equal(stage, `${kind}_instruction`);
  }
});

test('file names and session IDs cannot write outside the audio directory', async () => {
  const { POST } = require('../app/api/audio/upload/route');
  for (const bad of ['../../escape', '..\\escape', '/absolute', '.', 'a\0b']) {
    assert.throws(() => buildAudioStoragePath('anonymous', undefined, bad, 'audio/webm'));
    const form = new FormData(); form.append('file', new Blob(['test'], { type: 'audio/webm' }), 'test.webm');
    form.append('fileName', bad); form.append('allowAnonymous', 'true');
    assert.equal((await POST(new Request('http://localhost/api/audio/upload', { method: 'POST', body: form }))).status, 400);
  }
});

test('a gap in practice days breaks the streak', () => {
  const day = (ago) => { const d = new Date(); d.setDate(d.getDate() - ago); return d; };
  assert.equal(computeStreak([day(0), day(2), day(4)]), 1);
  assert.equal(computeStreak([day(0), day(1), day(2), day(4)]), 3);
  assert.equal(computeStreak([day(1), day(2)]), 2);
  assert.equal(computeStreak([day(3)]), 0);
});

test('authentication and timeout errors are not mislabeled as a quiet recording', () => {
  assert.match(formatAnalysisError('AI scoring account: insufficient balance (1113)'), /credits/);
  assert.doesNotMatch(formatAnalysisError('AI scoring account: insufficient balance (1113)'), /busy/);
  assert.match(formatAnalysisError('AssemblyAI authentication failed (401)'), /configuration/);
  assert.match(formatAnalysisError('AssemblyAI transcription timed out.'), /too long/);
  assert.doesNotMatch(formatAnalysisError('GLM invalid scores'), /busy/);
});

test('a completed job without a result fails immediately instead of polling indefinitely', async () => {
  const old = global.fetch;
  try {
    for (const payload of [null, {}, { status: 'done', result: null }]) {
      global.fetch = async () => Response.json(payload);
      await assert.rejects(pollAnalysisJob('/job', { intervalMs: 1, maxWaitMs: 50 }), /invalid status|result is missing/);
    }
  } finally { global.fetch = old; }
});

test('local startup keeps playback and Python downloads on the chosen port', async () => {
  const { developmentConfig } = await import('./dev-with-speech.mjs');
  const config = developmentConfig({ PORT: '3107', NEXT_PUBLIC_APP_URL: 'http://localhost:3000' });
  assert.equal(config.env.NEXT_PUBLIC_APP_URL, 'http://localhost:3107');
  assert.equal(config.env.INTERNAL_APP_URL, 'http://127.0.0.1:3107');
  for (const port of ['abc', '-1', '70000', '1.5']) assert.throws(() => developmentConfig({ PORT: port }));
  const { default: nextConfig } = await import('../next.config.mjs');
  assert.notEqual(nextConfig('phase-development-server').distDir, nextConfig('phase-production-build').distDir);
});

test('hesitation timestamp rounding carries into the next minute', () => {
  const feedback = { hesitation_recovery: { detected: true, timestamp: 59.99, duration_seconds: 5, kind: 'pause', timing_source: 'word_timestamps', context_before_hesitation: 'I enjoy studying alone.', continuation_options: [] } };
  const html = renderToStaticMarkup(React.createElement(InterviewDetailedFeedback, { feedback }));
  assert.match(html, /1:00.0/); assert.doesNotMatch(html, /0:60.0/);
});

test('saved interview history retains playback and never displays an unattempted section as zero', async () => {
  const analysis = await finalizeInterviewAnalysis(body, result);
  const entry = { mode: 'mock_exam', mockExam: { overallScore: 4, interviewAvg: 4, listenRepeatAvg: 0, listenRepeat: [], interview: [{ questionId: 'q1', scores, promptText: body.prompt, audioUrl: body.audioUrl, analysis }] } };
  const html = renderToStaticMarkup(React.createElement(HistoryEntryDetail, { entry }));
  assert.match(html, /<audio/); assert.match(html, /localhost:3001/); assert.doesNotMatch(html, /0.0\/6/);
});

test('browser speech failure fires one callback; cancellation prevents late playback', async () => {
  const { speakText, cancelSpeech } = require('../lib/speechSynthesis');
  let played = 0, ended = 0, errors = 0;
  global.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
  global.window = { speechSynthesis: {
    getVoices: () => [{ lang: 'en-US', name: 'Samantha', localService: true }],
    cancel() {},
    speak(utterance) { played++; utterance.onerror(); },
  } };
  try {
    await speakText('Hello.', { onEnd: () => ended++, onError: () => errors++ });
    assert.equal(errors, 1); assert.equal(ended, 0); assert.equal(played, 1);
    const pending = speakText('This playback should be cancelled.');
    cancelSpeech(); await pending;
    assert.equal(played, 1);
  } finally { cancelSpeech(); delete global.window; delete global.SpeechSynthesisUtterance; }
});
