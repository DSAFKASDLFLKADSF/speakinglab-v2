import { randomUUID } from "crypto";
import type { InterviewFeedback } from "@/lib/interviewDetailedFeedback";
import type { InterviewScores } from "@/components/InterviewScoreCard";
import {
  ensureDataRoot,
  practiceFilePath,
  writeStoreJson,
} from "@/lib/fileStore";
import type { StoredPracticeRecord } from "@/lib/practiceStore";
import type { PythonBehaviorMetrics } from "@/lib/pythonSpeechApi";

export interface SaveInterviewInput {
  analysisId?: string;
  userId: string;
  audioUrl: string;
  storagePath: string;
  question: string;
  questionId?: string;
  transcript: string;
  scores: InterviewScores;
  scoreSummary: string;
  feedback: InterviewFeedback;
  metrics: PythonBehaviorMetrics;
  durationSeconds: number;
  responseSeconds: number;
  aiModel?: string;
}

export interface SavedInterviewRecord {
  sessionId: string;
  audioResponseId: string;
  scoreId: string;
}

function clampEts(value: number): number {
  return Math.min(4, Math.max(0, Math.round(value * 10) / 10));
}

function interviewToEts(scores: InterviewScores) {
  const delivery = clampEts(((scores.pace + scores.pronunciation) / 2 / 5) * 4);
  const language = clampEts((scores.grammar / 5) * 4);
  const topic = clampEts((scores.topic / 5) * 4);
  const avg =
    (scores.topic + scores.pace + scores.pronunciation + scores.grammar) / 4;
  return {
    deliveryScore: delivery,
    languageUseScore: language,
    topicDevelopmentScore: topic,
    scaledScore: Math.round((avg / 5) * 30),
  };
}

export async function saveInterviewAnalysis(
  input: SaveInterviewInput
): Promise<SavedInterviewRecord> {
  const ets = interviewToEts(input.scores);
  const now = new Date().toISOString();
  const id = input.analysisId ?? randomUUID();
  const responseSeconds = input.responseSeconds === 60 ? 60 : 45;

  const record: StoredPracticeRecord = {
    id,
    userId: input.userId,
    kind: "interview",
    createdAt: now,
    questionId: input.questionId,
    promptText: input.question,
    transcript: input.transcript,
    audioUrl: input.audioUrl,
    storagePath: input.storagePath,
    durationSeconds: Math.max(0.1, input.durationSeconds),
    responseSeconds,
    interviewScores: input.scores,
    scoreSummary: input.scoreSummary,
    feedback: input.feedback,
    deliveryScore: ets.deliveryScore,
    languageUseScore: ets.languageUseScore,
    topicDevelopmentScore: ets.topicDevelopmentScore,
    scaledScore: ets.scaledScore,
    aiModel: input.aiModel ?? "python-api",
    metrics: input.metrics,
    status: "completed",
    taskNumber: "1",
  };

  await ensureDataRoot();
  await writeStoreJson(practiceFilePath(input.userId, id), record);

  return {
    sessionId: id,
    audioResponseId: id,
    scoreId: id,
  };
}
