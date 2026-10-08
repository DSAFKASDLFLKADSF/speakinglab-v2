/* Offline contract tests using the project's existing TypeScript loader. */
const assert = require('node:assert/strict');
const test = require('node:test');
require('./test-register.cjs');
const { mapAcousticMetrics } = require('../lib/acousticMetrics');
const { finalizeInterviewAnalysis } = require('../lib/finalizeInterviewAnalysis');
const { finalizeListenRepeatAnalysis } = require('../lib/finalizeListenRepeatAnalysis');

const acoustic = {
  duration_seconds: 10,
  speech: { word_count: 20, wpm: 120, articulation_rate: 150 },
  pauses: { pause_count: 2, long_pause_count: 1, longest_pause: 1.2, total_pause_time: 2, pause_ratio: 0.2 },
  fillers: { count: 1 },
  prosody: { pitch_median: 180, pitch_variation: 20, energy_variation: null },
  source: 'waveform',
};
const mappedAcoustic = {
  durationSeconds: 10,
  speech: { wordCount: 20, wpm: 120, articulationRate: 150 },
  pauses: { pauseCount: 2, longPauseCount: 1, longestPause: 1.2, totalPauseTime: 2, pauseRatio: 0.2 },
  fillers: { count: 1 },
  prosody: { pitchMedian: 180, pitchVariation: 20, energyVariation: null },
  source: 'waveform',
};
const malformed = [
  [], 'bad', 42, {},
  { ...acoustic, speech: null },
  { ...acoustic, pauses: {} },
  { ...acoustic, fillers: undefined },
  { ...acoustic, prosody: 'bad' },
  { ...acoustic, duration_seconds: Infinity },
  { ...acoustic, speech: { ...acoustic.speech, wpm: NaN } },
  { ...acoustic, speech: { ...acoustic.speech, word_count: -1 } },
  { ...acoustic, pauses: { ...acoustic.pauses, pause_ratio: 1.1 } },
  { ...acoustic, prosody: { ...acoustic.prosody, pitch_median: '180' } },
];

const scores = { topic: 4, pace: 2, pronunciation: 3, grammar: 5 };
const behavior = { speaking_rate_wpm: 120, pause_count: 2, filler_word_count: 1, longest_pause_seconds: 1.2 };
const interviewBody = {
  audioUrl: 'https://example.com/interview.webm', storagePath: 'interview.webm',
  prompt: 'How do you study?', responseSeconds: 45, durationMs: 10000,
};
const interviewResult = {
  transcript: 'I prefer studying alone.', scores, score_summary: 'All four dimensions have been scored.',
  metrics: behavior, feedback: { summary: 'Review content and language.', sections: [] },
};
const repeatBody = {
  audioUrl: 'https://example.com/repeat.webm', storagePath: 'repeat.webm', original: 'Hello world.',
};
const repeatResult = {
  transcript: 'Hello world.', score: 4, score_summary: 'Accurate repetition.',
  words: [{ status: 'correct', original: 'Hello', user: 'Hello' }, { status: 'correct', original: 'world', user: 'world' }],
  feedback: { summary: 'Good repetition.', sections: [] }, duration_seconds: 10,
};

test('acoustic mapper keeps absent optional data absent', () => {
  for (const raw of [undefined, null]) assert.equal(mapAcousticMetrics(raw), undefined);
});

test('acoustic mapper maps nested fields and preserves unavailable prosody', () => {
  assert.deepEqual(mapAcousticMetrics(acoustic), mappedAcoustic);
});

test('malformed acoustic data is discarded without throwing', () => {
  for (const raw of malformed) {
    assert.doesNotThrow(() => mapAcousticMetrics(raw));
    assert.equal(mapAcousticMetrics(raw), undefined);
  }
});

test('both analysis finalizers pass through normalized acoustic metrics', async () => {
  const interview = await finalizeInterviewAnalysis(interviewBody, { ...interviewResult, acoustic_metrics: acoustic });
  const repeat = await finalizeListenRepeatAnalysis(repeatBody, { ...repeatResult, acoustic_metrics: acoustic });
  assert.deepEqual(interview.acousticMetrics, mappedAcoustic);
  assert.deepEqual(repeat.acousticMetrics, mappedAcoustic);
  assert.deepEqual(interview.scores, scores);
  assert.equal(repeat.score, 4);
  assert.equal(interview.persisted, false);
  assert.equal(repeat.persisted, false);
});

test('optional malformed acoustic data cannot prevent either scoring result', async () => {
  for (const raw of [undefined, null, ...malformed]) {
    const interview = await finalizeInterviewAnalysis(interviewBody, { ...interviewResult, acoustic_metrics: raw });
    const repeat = await finalizeListenRepeatAnalysis(repeatBody, { ...repeatResult, acoustic_metrics: raw });
    assert.equal(interview.acousticMetrics, undefined);
    assert.equal(repeat.acousticMetrics, undefined);
    assert.deepEqual(interview.scores, scores);
    assert.equal(interview.metrics.speakingRateWpm, 120);
    assert.equal(interview.transcript, interviewResult.transcript);
    assert.equal(repeat.score, 4);
    assert.equal(repeat.transcript, repeatResult.transcript);
  }
});
