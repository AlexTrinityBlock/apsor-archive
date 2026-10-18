import type { BadgeTone } from "../../type/ui";

/** Shared badge tones for tool outcomes and assistant finish reasons. */
export function toolStatusTone(status: string | null): BadgeTone {
  const normalized = status?.toLowerCase() ?? "";
  if (
    normalized === "ok" ||
    normalized === "success" ||
    normalized === "completed"
  ) {
    return "moss";
  }
  if (
    normalized === "error" ||
    normalized === "failed" ||
    normalized === "cancelled"
  ) {
    return "vermilion";
  }
  return "ochre";
}

export function finishReasonTone(reason: string | null): BadgeTone {
  const normalized = reason?.toLowerCase() ?? "";
  if (normalized === "stop") {
    return "moss";
  }
  if (normalized === "tool_calls") {
    return "ochre";
  }
  if (
    normalized === "error" ||
    normalized === "length" ||
    normalized === "content_filter"
  ) {
    return "vermilion";
  }
  return "neutral";
}
