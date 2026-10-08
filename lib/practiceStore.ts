import type { InterviewFeedback } from "@/lib/interviewDetailedFeedback";
import type { InterviewScores } from "@/components/InterviewScoreCard";
import type { ListenRepeatScore } from "@/components/ScoreCard";

/** One scored practice item stored under data/practices/{userId}/{id}.json */
export interface StoredPracticeRecord {
  id: string;
  userId: string;
  kind: "listen_repeat" | "interview";
  createdAt: string;
  status: "pending" | "completed" | "abandoned";
  taskNumber: "1" | "2" | "3" | "4";
  promptId?: string;
  questionId?: string;
  promptText: string;
  transcript: string | null;
  audioUrl: string | null;
  storagePath: string;
  mimeType?: string;
  fileSizeBytes?: number | null;
  durationSeconds: number;
  responseSeconds?: number;
  listenRepeatScore?: ListenRepeatScore | number;
  interviewScores?: InterviewScores;
  scoreSummary?: string;
  feedback?: InterviewFeedback;
  deliveryScore?: number;
  languageUseScore?: number;
  topicDevelopmentScore?: number;
  scaledScore?: number;
  aiModel?: string;
  metrics?: unknown;
}
