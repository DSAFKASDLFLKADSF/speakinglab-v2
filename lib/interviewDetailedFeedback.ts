/** Diagnostics are optional additions to the existing feedback payload, never scores. */
export interface ContentIssue {
  problem: string;
  evidence: string;
  why_it_matters: string;
  imitable_improvement: string;
}

export interface LanguageIssue {
  original: string;
  problem: string;
  better_version: string;
  pattern_to_imitate: string;
}

export interface IssueGroup<T> {
  status: "complete" | "unavailable";
  issues: T[];
}

export type ContinuationStrategy = "explain_why" | "give_consequence" | "give_example";

export interface HesitationRecovery {
  detected: boolean;
  timestamp?: number | null;
  duration_seconds?: number | null;
  kind?: "pause" | "fillers" | null;
  timing_source?: "word_timestamps" | null;
  context_before_hesitation?: string;
  continuation_options: Array<{ strategy: ContinuationStrategy; text: string }>;
}

export interface InterviewFeedback {
  summary: string;
  sections: Array<{ title: string; content: string }>;
  content_feedback?: {
    on_topic: IssueGroup<ContentIssue>;
    reasoning: IssueGroup<ContentIssue>;
    example_detail: IssueGroup<ContentIssue>;
  };
  language_feedback?: IssueGroup<LanguageIssue>;
  hesitation_recovery?: HesitationRecovery;
}

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function group<T>(raw: unknown, fields: readonly string[], limit: number): IssueGroup<T> {
  const source = object(raw);
  const items = Array.isArray(source.issues) ? source.issues : [];
  const valid = items.flatMap((item) => {
    const record = object(item);
    const entries = fields.map((field) => [field, text(record[field])] as const);
    return entries.every(([, value]) => value)
      ? [Object.fromEntries(entries) as T]
      : [];
  });
  return {
    status: source.status === "complete" && Array.isArray(source.issues) && valid.length === items.length
      ? "complete" : "unavailable",
    issues: valid.slice(0, limit),
  };
}

/** Defend the page against missing fields, old saved attempts, and malformed AI data. */
export function normalizeInterviewFeedback(raw: unknown): Required<InterviewFeedback> {
  const source = object(raw);
  const content = object(source.content_feedback);
  const contentFields = ["problem", "evidence", "why_it_matters", "imitable_improvement"];
  const recovery = object(source.hesitation_recovery);
  const validEvent = recovery.detected === true
    && typeof recovery.timestamp === "number" && Number.isFinite(recovery.timestamp) && recovery.timestamp >= 0
    && typeof recovery.duration_seconds === "number" && Number.isFinite(recovery.duration_seconds) && recovery.duration_seconds >= 5
    && recovery.timing_source === "word_timestamps"
    && (recovery.kind === "pause" || recovery.kind === "fillers")
    && Boolean(text(recovery.context_before_hesitation));
  const options: HesitationRecovery["continuation_options"] = [];
  if (validEvent && Array.isArray(recovery.continuation_options)) {
    for (const item of recovery.continuation_options) {
      const option = object(item);
      const strategy = option.strategy;
      const value = text(option.text);
      if ((strategy === "explain_why" || strategy === "give_consequence" || strategy === "give_example")
        && value && value.length <= 600 && value.split(/(?<=[.!?])\s+/).length <= 2
        && !options.some((existing) => existing.strategy === strategy)) {
        options.push({ strategy, text: value });
      }
    }
  }
  return {
    summary: "Review topic development and language use below.",
    sections: [],
    content_feedback: {
      on_topic: group<ContentIssue>(content.on_topic, contentFields, 2),
      reasoning: group<ContentIssue>(content.reasoning, contentFields, 2),
      example_detail: group<ContentIssue>(content.example_detail, contentFields, 2),
    },
    language_feedback: group<LanguageIssue>(source.language_feedback,
      ["original", "problem", "better_version", "pattern_to_imitate"], 3),
    hesitation_recovery: validEvent ? {
      detected: true,
      timestamp: recovery.timestamp as number,
      duration_seconds: recovery.duration_seconds as number,
      kind: recovery.kind as "pause" | "fillers",
      timing_source: "word_timestamps",
      context_before_hesitation: text(recovery.context_before_hesitation),
      continuation_options: options.length >= 2 ? options : [],
    } : { detected: false, continuation_options: [] },
  };
}
