import type { LocalMockExamDetail } from "@/lib/localHistory";
import { formatSpeakingBand, SPEAKING_BAND_MAX } from "@/lib/toeflSpeakingBand";

export interface ExamScoreSummaryProps {
  summary: LocalMockExamDetail | null;
  scoringRequested: boolean;
  recordingCount: number;
  missingAnalysisCount: number;
}

/** An unsuccessful analysis is an unavailable result, never a zero score. */
export function ExamScoreSummary({
  summary,
  scoringRequested,
  recordingCount,
  missingAnalysisCount,
}: ExamScoreSummaryProps) {
  const scoredCount = (summary?.listenRepeat.length ?? 0) + (summary?.interview.length ?? 0);
  if (!scoringRequested || !summary || scoredCount === 0) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">
          {scoringRequested ? "Scores and feedback unavailable" : "Recordings saved"}
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          {scoringRequested
            ? "None of your recordings have been analyzed yet. There is no score or feedback to show."
            : "Scoring was not requested for this attempt."}
        </p>
        <p className="mt-2 text-sm text-slate-600">
          {recordingCount} recording{recordingCount === 1 ? "" : "s"} saved.
          {scoringRequested ? " You can retry analysis without recording again." : " Use Score recordings below to get feedback."}
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Scores</h2>
      {missingAnalysisCount > 0 && (
        <p className="mt-2 text-sm text-slate-600">
          Based on {scoredCount} analyzed question{scoredCount === 1 ? "" : "s"}. The remaining questions have no score yet.
        </p>
      )}
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {summary.listenRepeat.length > 0 && (
          <div className="rounded-lg bg-slate-50 p-4 text-center">
            <p className="text-xs text-slate-500">Listen &amp; Repeat</p>
            <p className="mt-1 text-2xl font-semibold">{formatSpeakingBand(summary.listenRepeatAvg)}/{SPEAKING_BAND_MAX}</p>
          </div>
        )}
        {summary.interview.length > 0 && (
          <div className="rounded-lg bg-slate-50 p-4 text-center">
            <p className="text-xs text-slate-500">Virtual Interview</p>
            <p className="mt-1 text-2xl font-semibold">{formatSpeakingBand(summary.interviewAvg)}/{SPEAKING_BAND_MAX}</p>
          </div>
        )}
        <div className="rounded-lg bg-slate-900 p-4 text-center text-white">
          <p className="text-xs text-slate-300">{missingAnalysisCount > 0 ? "Partial Speaking score" : "Overall Speaking"}</p>
          <p className="mt-1 text-2xl font-semibold">{formatSpeakingBand(summary.overallScore)}/{SPEAKING_BAND_MAX}</p>
        </div>
      </div>
    </section>
  );
}
