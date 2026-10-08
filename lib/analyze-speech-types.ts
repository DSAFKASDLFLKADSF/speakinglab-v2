import type { ComparisonWord } from "@/components/ComparisonText";
import type { FeedbackSection } from "@/components/FeedbackCard";
import type { ListenRepeatScore } from "@/components/ScoreCard";
import type { PronunciationMetrics } from "@/lib/pronunciationMetrics";
import type { AcousticMetrics } from "@/lib/acousticMetrics";

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
  acousticMetrics?: AcousticMetrics;
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
