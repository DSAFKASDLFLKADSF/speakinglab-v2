/** Normalized pronunciation output shared by the Python API and the web app. */
export interface PythonPronunciationWord {
  word: string;
  score: number | null;
  status: "ok" | "needs_review" | "missing" | "unknown";
  start?: number | null;
  end?: number | null;
}

export interface PythonPronunciationMetrics {
  pronunciation_accuracy: number | null;
  pronunciation_fluency: number | null;
  completeness: number | null;
  words: PythonPronunciationWord[];
  provider: string;
  model: string;
}

export interface PronunciationWord {
  word: string;
  score: number | null;
  status: "ok" | "needs_review" | "missing" | "unknown";
  start?: number | null;
  end?: number | null;
}

export interface PronunciationMetrics {
  pronunciationAccuracy: number | null;
  pronunciationFluency: number | null;
  completeness: number | null;
  words: PronunciationWord[];
  provider: string;
  model: string;
}

export function mapPronunciationMetrics(
  raw: PythonPronunciationMetrics | null | undefined
): PronunciationMetrics | undefined {
  if (!raw) return undefined;
  return {
    pronunciationAccuracy: raw.pronunciation_accuracy,
    pronunciationFluency: raw.pronunciation_fluency,
    completeness: raw.completeness,
    words: Array.isArray(raw.words)
      ? raw.words.map((word) => ({
          word: word.word,
          score: word.score,
          status: word.status,
          ...(word.start === undefined ? {} : { start: word.start }),
          ...(word.end === undefined ? {} : { end: word.end }),
        }))
      : [],
    provider: raw.provider,
    model: raw.model,
  };
}
