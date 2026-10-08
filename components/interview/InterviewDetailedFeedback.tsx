import {
  normalizeInterviewFeedback,
  type ContentIssue,
  type IssueGroup,
} from "@/lib/interviewDetailedFeedback";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-medium text-slate-800">{label}</dt>
      <dd className="mt-1 whitespace-pre-wrap text-slate-600">{value}</dd>
    </div>
  );
}

function GroupStatus({ group }: { group: IssueGroup<unknown> }) {
  if (group.status !== "complete") {
    return <p className="text-sm text-slate-500">Some detailed feedback is unavailable for this attempt. Your scores are still available.</p>;
  }
  return group.issues.length === 0
    ? <p className="text-sm text-slate-600">No major issues were identified in this area.</p>
    : null;
}

function ContentGroup({ title, group }: { title: string; group: IssueGroup<ContentIssue> }) {
  return (
    <section className="space-y-3">
      <h5 className="text-sm font-semibold text-slate-800">{title}</h5>
      <GroupStatus group={group} />
      {group.issues.map((issue, index) => (
        <dl key={index} className="space-y-3 rounded-lg bg-slate-50 p-4 text-sm leading-relaxed">
          <Field label="Problem" value={issue.problem} />
          <Field label="Evidence" value={`“${issue.evidence}”`} />
          <Field label="Why it matters" value={issue.why_it_matters} />
          <Field label="Imitable improvement" value={issue.imitable_improvement} />
        </dl>
      ))}
    </section>
  );
}

const STRATEGIES = {
  explain_why: "Explain why",
  give_consequence: "Give a consequence",
  give_example: "Give an example",
};

function timestamp(seconds: number): string {
  const tenths = Math.round(seconds * 10);
  return `${Math.floor(tenths / 600)}:${((tenths % 600) / 10).toFixed(1).padStart(4, "0")}`;
}

export function InterviewDetailedFeedback({ feedback }: { feedback: unknown }) {
  const { content_feedback: content, language_feedback: language, hesitation_recovery: recovery } = normalizeInterviewFeedback(feedback);
  return (
    <div className="space-y-6">
      <section className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Feedback criterion 1</p>
        <h4 className="text-base font-semibold text-slate-900">The response is on topic and well elaborated.</h4>
        <ContentGroup title="A. On-topic / Relevance" group={content.on_topic} />
        <ContentGroup title="B. Reasoning / Logical Elaboration" group={content.reasoning} />
        <ContentGroup title="C. Example Detail" group={content.example_detail} />
      </section>

      <section className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Feedback criterion 2</p>
        <h4 className="text-base font-semibold text-slate-900">A range of accurate grammar and vocabulary allows clear expression of precise meanings.</h4>
        <GroupStatus group={language} />
        {language.issues.map((issue, index) => (
          <dl key={index} className="space-y-3 rounded-lg bg-slate-50 p-4 text-sm leading-relaxed">
            <Field label="Original" value={`“${issue.original}”`} />
            <Field label="Problem" value={issue.problem} />
            <Field label="Better version" value={issue.better_version} />
            <Field label="Pattern to imitate" value={issue.pattern_to_imitate} />
          </dl>
        ))}
      </section>

      {recovery.detected && (
        <section className="space-y-3 rounded-xl border border-blue-100 bg-blue-50/50 p-4">
          <h4 className="text-base font-semibold text-slate-900">How you could continue</h4>
          <p className="text-xs text-slate-600">
            Around {timestamp(recovery.timestamp!)} · {recovery.duration_seconds!.toFixed(1)}s {recovery.kind === "fillers" ? "filler sequence" : "gap between words"}
          </p>
          <p className="text-sm text-slate-700">Before this moment: “{recovery.context_before_hesitation}”</p>
          {recovery.continuation_options.length ? (
            <ol className="space-y-3">
              {recovery.continuation_options.map((option, index) => (
                <li key={option.strategy} className="rounded-lg bg-white p-3 text-sm">
                  <p className="font-medium text-slate-800">Option {index + 1} — {STRATEGIES[option.strategy]}</p>
                  <p className="mt-1 text-slate-600">{option.text}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-slate-500">Continuation suggestions are unavailable for this attempt.</p>
          )}
        </section>
      )}
    </div>
  );
}
