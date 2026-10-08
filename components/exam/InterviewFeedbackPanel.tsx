"use client";

import { InterviewDetailedFeedback } from "@/components/interview/InterviewDetailedFeedback";
import { InterviewScoreCard } from "@/components/InterviewScoreCard";
import { RecordingAudioPlayer } from "@/components/RecordingAudioPlayer";
import type { AnalyzeInterviewResponse } from "@/lib/analyze-interview-types";

export interface InterviewFeedbackPanelProps {
  question: string;
  analysis: AnalyzeInterviewResponse;
  audioUrl?: string;
  title?: string;
  defaultOpen?: boolean;
}

export function InterviewFeedbackPanel({
  question,
  analysis,
  audioUrl,
  title,
  defaultOpen = false,
}: InterviewFeedbackPanelProps) {
  return (
    <details
      className="rounded-xl border border-slate-200 bg-white shadow-sm"
      open={defaultOpen}
    >
      <summary className="cursor-pointer list-none px-5 py-4 text-sm font-semibold text-slate-900 [&::-webkit-details-marker]:hidden">
        {title ?? "View detailed feedback"}
      </summary>
      <div className="space-y-5 border-t border-slate-100 px-5 pb-5 pt-4">
        {audioUrl ? <RecordingAudioPlayer src={audioUrl} /> : null}

        <div>
          <h4 className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Question
          </h4>
          <p className="mt-1 text-sm text-slate-800">{question}</p>
        </div>

        <section>
          <h4 className="text-xs font-medium uppercase tracking-wide text-slate-500">What you said</h4>
          <p className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-800">{analysis.transcript}</p>
        </section>

        <InterviewDetailedFeedback feedback={analysis.feedback} />

        <details className="rounded-lg border border-slate-200 p-4">
          <summary className="cursor-pointer text-sm font-medium text-slate-700">View all scoring dimensions</summary>
          <div className="mt-3">
            <InterviewScoreCard scores={analysis.scores} />
          </div>
        </details>
      </div>
    </details>
  );
}
