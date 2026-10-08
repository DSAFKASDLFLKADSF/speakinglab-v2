import type { ComparisonWord } from "@/components/ComparisonText";
import type { FeedbackSection } from "@/components/FeedbackCard";
import type { ListenRepeatScore } from "@/components/ScoreCard";
import type { PronunciationMetrics } from "@/lib/pronunciationMetrics";

export interface AnalyzeSpeechRequest {
  audioUrl: string;
  storagePath: string;
  original: string;
  promptId?: string;
}

export interface AnalyzeSpeechResponse {
  transcript: string;
  score: ListenRepeatScore;
  scoreSummary: string;
  words: ComparisonWord[];
  feedback: {
    summary: string;
    sections: FeedbackSection[];
  };
  pronunciationMetrics?: PronunciationMetrics;
  storagePath: string;
  persisted: boolean;
  sessionId?: string;
  audioResponseId?: string;
  scoreId?: string;
  persistError?: string;
}

export interface AnalyzeSpeechError {
  error: string;
}
