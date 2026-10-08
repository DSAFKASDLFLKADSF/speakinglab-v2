/** Phase 4 objective delivery and subjective language score breakdown. */
export interface PythonScoringBreakdown {
  scoring_version: string;
  objective: {
    pace: number;
    pronunciation: number;
    fluency: number;
  };
  language: {
    content: number;
    grammar_vocabulary: number;
  };
  overall: number;
}

export interface ScoringBreakdown {
  scoringVersion: string;
  objective: {
    pace: number;
    pronunciation: number;
    fluency: number;
  };
  language: {
    content: number;
    grammarVocabulary: number;
  };
  overall: number;
}

function isScore(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 1 && value <= 5;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function mapScoringBreakdown(
  raw: PythonScoringBreakdown | null | undefined
): ScoringBreakdown | undefined {
  if (!isRecord(raw)) return undefined;
  const objective = raw.objective;
  const language = raw.language;
  if (
    typeof raw.scoring_version !== "string" ||
    raw.scoring_version.trim().length === 0 ||
    !isRecord(objective) ||
    !isRecord(language) ||
    !isScore(objective.pace) ||
    !isScore(objective.pronunciation) ||
    !isScore(objective.fluency) ||
    !isScore(language.content) ||
    !isScore(language.grammar_vocabulary) ||
    !isScore(raw.overall)
  ) {
    return undefined;
  }
  return {
    scoringVersion: raw.scoring_version,
    objective: {
      pace: objective.pace,
      pronunciation: objective.pronunciation,
      fluency: objective.fluency,
    },
    language: {
      content: language.content,
      grammarVocabulary: language.grammar_vocabulary,
    },
    overall: raw.overall,
  };
}
