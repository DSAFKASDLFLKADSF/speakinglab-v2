/** Validate JSON before calling the paid analysis service. */
export function analysisRequestError(raw: unknown, kind: "interview" | "listen_repeat"): string | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return "A JSON object is required.";
  const body = raw as Record<string, unknown>;
  for (const field of ["audioUrl", "storagePath", kind === "interview" ? "prompt" : "original"]) {
    if (typeof body[field] !== "string" || !(body[field] as string).trim()) return `${field} is required and must be text.`;
  }
  try {
    const url = new URL(body.audioUrl as string);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return "audioUrl must be an HTTP(S) audio URL.";
  } catch { return "audioUrl must be an HTTP(S) audio URL."; }
  for (const field of ["questionId", "promptId"]) {
    if (body[field] != null && typeof body[field] !== "string") return `${field} must be text.`;
  }
  if (kind === "interview") {
    if (body.responseSeconds != null && (!Number.isInteger(body.responseSeconds) || Number(body.responseSeconds) < 1 || Number(body.responseSeconds) > 120)) return "responseSeconds must be an integer between 1 and 120.";
    if (body.durationMs != null && (!Number.isSafeInteger(body.durationMs) || Number(body.durationMs) < 0)) return "durationMs must be a nonnegative integer.";
  }
  return null;
}
