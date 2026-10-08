import { randomUUID } from "crypto";
import type { FeedbackSection } from "@/components/FeedbackCard";
import type { ListenRepeatScore } from "@/components/ScoreCard";
import {
  ensureDataRoot,
  practiceFilePath,
  writeStoreJson,
} from "@/lib/fileStore";
import type { StoredPracticeRecord } from "@/lib/practiceStore";

export interface SaveListenRepeatInput {
  analysisId?: string;
  userId: string;
  audioUrl: string;
  storagePath: string;
  original: string;
  promptId?: string;
  transcript: string;
  score: ListenRepeatScore;
  scoreSummary: string;
  feedback: {
    summary: string;
    sections: FeedbackSection[];
  };
  durationSeconds: number;
  mimeType?: string;
  fileSizeBytes?: number;
  aiModel?: string;
  deliveryScore?: number;
  languageUseScore?: number;
  topicDevelopmentScore?: number;
}

export interface SavedListenRepeatRecord {
  sessionId: string;
  audioResponseId: string;
  scoreId: string;
}

function clampEtsScore(value: number): number {
  return Math.min(4, Math.max(0, Math.round(value * 10) / 10));
}

function listenRepeatToEts(score: ListenRepeatScore) {
  const normalized = clampEtsScore((score / 5) * 4);
  return {
    deliveryScore: normalized,
    languageUseScore: normalized,
    topicDevelopmentScore: normalized,
    scaledScore: Math.round((score / 5) * 30),
  };
}

export async function saveListenRepeatAnalysis(
  input: SaveListenRepeatInput
): Promise<SavedListenRepeatRecord> {
  const ets =
    input.deliveryScore !== undefined &&
    input.languageUseScore !== undefined &&
    input.topicDevelopmentScore !== undefined
      ? {
          deliveryScore: clampEtsScore(input.deliveryScore),
          languageUseScore: clampEtsScore(input.languageUseScore),
          topicDevelopmentScore: clampEtsScore(input.topicDevelopmentScore),
          scaledScore: Math.round(
            ((input.deliveryScore +
              input.languageUseScore +
              input.topicDevelopmentScore) /
              12) *
              30
          ),
        }
      : listenRepeatToEts(input.score);

  const now = new Date().toISOString();
  const id = input.analysisId ?? randomUUID();
  const record: StoredPracticeRecord = {
    id,
    userId: input.userId,
    kind: "listen_repeat",
    createdAt: now,
    promptId: input.promptId,
    promptText: input.original,
    transcript: input.transcript,
    audioUrl: input.audioUrl,
    storagePath: input.storagePath,
    mimeType: input.mimeType ?? "audio/webm",
    fileSizeBytes: input.fileSizeBytes ?? null,
    durationSeconds: Math.max(0.1, input.durationSeconds),
    listenRepeatScore: input.score,
    scoreSummary: input.scoreSummary,
    feedback: input.feedback,
    deliveryScore: ets.deliveryScore,
    languageUseScore: ets.languageUseScore,
    topicDevelopmentScore: ets.topicDevelopmentScore,
    scaledScore: ets.scaledScore,
    aiModel: input.aiModel ?? "python-api",
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
