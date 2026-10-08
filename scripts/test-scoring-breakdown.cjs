/* Phase 4 scoring contract tests. */
const assert = require('node:assert/strict');
const test = require('node:test');
require('./test-register.cjs');
const { mapScoringBreakdown } = require('../lib/scoringBreakdown');
const { finalizeInterviewAnalysis } = require('../lib/finalizeInterviewAnalysis');

const raw = {
  scoring_version: 'delivery-v1',
  objective: { pace: 4.2, pronunciation: 4.6, fluency: 3.7 },
  language: { content: 4, grammar_vocabulary: 3.5 },
  overall: 4.1,
};
const mapped = {
  scoringVersion: 'delivery-v1',
  objective: { pace: 4.2, pronunciation: 4.6, fluency: 3.7 },
  language: { content: 4, grammarVocabulary: 3.5 },
  overall: 4.1,
};

const interviewBody = {
  audioUrl: 'https://example.com/interview.webm', storagePath: 'interview.webm',
  prompt: 'How do you study?', responseSeconds: 45, durationMs: 10000,
};
const interviewResult = {
  transcript: 'I prefer studying alone.',
  scores: { topic: 4, pace: 2, pronunciation: 3, grammar: 5 },
  score_summary: 'All four dimensions have been scored.',
  metrics: { speaking_rate_wpm: 120, pause_count: 2, filler_word_count: 1, longest_pause_seconds: 1.2 },
  feedback: { summary: 'Review content and language.', sections: [] },
  scoring: raw,
};

test('scoring mapper normalizes the Phase 4 nested contract', () => {
  assert.deepEqual(mapScoringBreakdown(raw), mapped);
  for (const value of [undefined, null, {}, { ...raw, overall: 7 }, { ...raw, objective: {} }]) {
    assert.equal(mapScoringBreakdown(value), undefined);
  }
});

test('interview finalizer exposes and persists the scoring breakdown', async () => {
  const result = await finalizeInterviewAnalysis(interviewBody, interviewResult);
  assert.deepEqual(result.scoring, mapped);
  assert.deepEqual(result.scores, interviewResult.scores);
  assert.equal(result.persisted, false);
});
