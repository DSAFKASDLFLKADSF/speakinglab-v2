import type {
  AnalyzeInterviewRequest,
  AnalyzeInterviewResponse,
  InterviewSegmentIssue,
  InterviewTranscriptSegment,
} from "@/lib/analyze-interview-types";
import type { PythonAnalyzeInterviewResponse } from "@/lib/pythonSpeechApi";
import { isInterviewAnalysisResult, PythonSpeechApiError } from "@/lib/pythonSpeechApi";
import { saveInterviewAnalysis } from "@/lib/saveInterviewAnalysis";
import { isDatabaseConfigured } from "@/lib/db";
import { normalizeInterviewFeedback } from "@/lib/interviewDetailedFeedback";
import { mapPronunciationMetrics } from "@/lib/pronunciationMetrics";

function mapIssue(
  raw:
    | {
        what_needs_improvement: string;
        why_it_matters: string;
        knowledge_point?: string | null;
      }
    | null
    | undefined
): InterviewSegmentIssue | undefined {
  if (!raw) return undefined;
  const whatNeedsImprovement = raw.what_needs_improvement?.trim() ?? "";
  const whyItMatters = raw.why_it_matters?.trim() ?? "";
  if (!whatNeedsImprovement && !whyItMatters) return undefined;
  const knowledgePoint = raw.knowledge_point?.trim();
  return {
    whatNeedsImprovement,
    whyItMatters,
    ...(knowledgePoint ? { knowledgePoint } : {}),
  };
}

function mapSegments(
  pythonResult: PythonAnalyzeInterviewResponse
): InterviewTranscriptSegment[] | undefined {
  if (Array.isArray(pythonResult.transcript_segments) && pythonResult.transcript_segments.length) {
    return pythonResult.transcript_segments.map((seg) => ({
      text: seg.text,
      hasIssue: Boolean(seg.has_issue),
      topicDevelopment: mapIssue(seg.topic_development),
      grammarVocabulary: mapIssue(seg.grammar_vocabulary),
      conciseness: mapIssue(seg.conciseness),
      improvedVersion: seg.improved_version?.trim() || undefined,
    }));
  }
  if (Array.isArray(pythonResult.transcript_review) && pythonResult.transcript_review.length) {
    return pythonResult.transcript_review.map((span) => {
      if (span.kind === "strong") {
        return { text: span.text, hasIssue: false };
      }
      const base = { text: span.text, hasIssue: true as const };
      if (span.kind === "grammar") {
        return {
          ...base,
          grammarVocabulary: {
            whatNeedsImprovement: span.note ?? "",
            whyItMatters: "",
          },
        };
      }
      return {
        ...base,
        topicDevelopment: {
          whatNeedsImprovement: span.note ?? "",
          whyItMatters: "",
        },
      };
    });
  }
  return undefined;
}

export async function finalizeInterviewAnalysis(
  body: AnalyzeInterviewRequest,
  pythonResult: PythonAnalyzeInterviewResponse,
  userId?: string | null,
  analysisId?: string
): Promise<AnalyzeInterviewResponse> {
  if (!isInterviewAnalysisResult(pythonResult)) {
    throw new PythonSpeechApiError("The analysis service returned invalid scores or transcript. Please retry.", 502);
  }
  const {
    audioUrl,
    storagePath,
    prompt,
    questionId,
    responseSeconds,
    durationMs,
  } = body;

  const feedback = normalizeInterviewFeedback(pythonResult.feedback);

  let persisted = false;
  let sessionId: string | undefined;
  let persistError: string | undefined;

  if (userId && isDatabaseConfigured()) {
    try {
      const saved = await saveInterviewAnalysis({
        analysisId,
        userId,
        audioUrl,
        storagePath,
        question: prompt,
        questionId,
        transcript: pythonResult.transcript,
        scores: pythonResult.scores,
        scoreSummary: pythonResult.score_summary,
        feedback,
        metrics: pythonResult.metrics,
        durationSeconds:
          (durationMs ?? 0) > 0
            ? durationMs! / 1000
            : pythonResult.duration_seconds ?? 0,
        responseSeconds: responseSeconds ?? 45,
        aiModel: pythonResult.model ?? "python-api",
      });
      persisted = true;
      sessionId = saved.sessionId;
    } catch (err) {
      persistError =
        err instanceof Error ? err.message : "Failed to save interview analysis.";
    }
  }

  const transcriptSegments = mapSegments(pythonResult);

  return {
    transcript: pythonResult.transcript,
    transcriptSegments,
    scores: pythonResult.scores,
    scoreSummary: pythonResult.score_summary,
    metrics: {
      speakingRateWpm: pythonResult.metrics.speaking_rate_wpm,
      pauseCount: pythonResult.metrics.pause_count,
      fillerWordCount: pythonResult.metrics.filler_word_count,
      longestPauseSeconds: pythonResult.metrics.longest_pause_seconds,
    },
    feedback,
    pronunciationMetrics: mapPronunciationMetrics(pythonResult.pronunciation_metrics),
    storagePath,
    persisted,
    sessionId,
    ...(persistError ? { persistError } : {}),
  };
}
