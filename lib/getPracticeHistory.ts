import {
  ensureDataRoot,
  listJsonFiles,
  practiceDir,
  readStoreJson,
} from "@/lib/fileStore";
import type {
  PracticeHistoryAudio,
  PracticeHistoryItem,
  PracticeHistoryQuery,
  PracticeHistoryResponse,
  PracticeHistoryScore,
} from "@/lib/history-types";
import type { StoredPracticeRecord } from "@/lib/practiceStore";
import type { PracticeSessionRecord } from "@/lib/session-types";

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 100;

export function normalizeHistoryQuery(
  query: PracticeHistoryQuery
): Required<Pick<PracticeHistoryQuery, "limit" | "offset">> &
  Pick<PracticeHistoryQuery, "status" | "taskNumber"> {
  const limit = Math.min(
    MAX_LIMIT,
    Math.max(1, Math.floor(Number.isFinite(query.limit) ? query.limit! : DEFAULT_LIMIT))
  );
  const offset = Math.max(0, Math.floor(Number.isFinite(query.offset) ? query.offset! : 0));

  return {
    limit,
    offset,
    status: query.status,
    taskNumber: query.taskNumber,
  };
}

function toSession(record: StoredPracticeRecord): PracticeSessionRecord {
  return {
    id: record.id,
    userId: record.userId,
    taskNumber: record.taskNumber,
    taskType: "independent",
    promptText: record.promptText,
    readingPassage: null,
    listeningTranscript: null,
    audioPromptUrl: null,
    prepTimeSeconds: 15,
    responseTimeSeconds: (record.responseSeconds === 60 ? 60 : 45) as 45 | 60,
    status: record.status === "completed" ? "completed" : "pending",
    prepStartedAt: null,
    recordingStartedAt: null,
    completedAt: record.status === "completed" ? record.createdAt : null,
    createdAt: record.createdAt,
    updatedAt: record.createdAt,
    promptId: record.promptId ?? record.questionId,
  };
}

function toAudio(record: StoredPracticeRecord): PracticeHistoryAudio | null {
  if (!record.storagePath) return null;
  return {
    id: record.id,
    transcript: record.transcript,
    durationSeconds: record.durationSeconds,
    audioUrl: record.audioUrl,
    storagePath: record.storagePath,
    createdAt: record.createdAt,
  };
}

function toScore(record: StoredPracticeRecord): PracticeHistoryScore | null {
  if (record.scaledScore === undefined) return null;
  return {
    id: record.id,
    scaledScore: record.scaledScore,
    interviewScores: record.interviewScores,
    feedback: record.feedback,
    deliveryScore: record.deliveryScore ?? 0,
    languageUseScore: record.languageUseScore ?? 0,
    topicDevelopmentScore: record.topicDevelopmentScore ?? 0,
    rawTotalScore: record.listenRepeatScore ?? null,
    overallFeedback: record.feedback?.summary ?? record.scoreSummary ?? null,
    aiModel: record.aiModel ?? "python-api",
    scoring: record.scoring,
    createdAt: record.createdAt,
  };
}

function toHistoryItem(record: StoredPracticeRecord): PracticeHistoryItem {
  return {
    kind: record.kind,
    session: toSession(record),
    audio: toAudio(record),
    score: toScore(record),
  };
}

export async function getPracticeHistory(
  userId: string,
  queryInput: PracticeHistoryQuery = {}
): Promise<PracticeHistoryResponse> {
  const { limit, offset, status, taskNumber } =
    normalizeHistoryQuery(queryInput);

  await ensureDataRoot();
  const files = await listJsonFiles(practiceDir(userId));
  const records: StoredPracticeRecord[] = [];

  for (const file of files) {
    const row = await readStoreJson<StoredPracticeRecord>(file);
    if (!row) continue;
    if (status && row.status !== status) continue;
    if (taskNumber && row.taskNumber !== taskNumber) continue;
    records.push(row);
  }

  records.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  const total = records.length;
  const page = records.slice(offset, offset + limit);

  return {
    items: page.map(toHistoryItem),
    total,
    limit,
    offset,
  };
}
