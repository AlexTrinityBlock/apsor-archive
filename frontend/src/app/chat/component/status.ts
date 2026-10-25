import type { BadgeTone } from "../../type/ui";
import type { Translate, TranslationKey } from "../../i18n";

const TOOL_STATUS_KEYS: Readonly<Record<string, TranslationKey>> = {
  running: "chat.status.running",
  pending: "chat.status.pending",
  ok: "chat.status.ok",
  success: "chat.status.success",
  completed: "chat.status.completed",
  error: "chat.status.error",
  failed: "chat.status.failed",
  cancelled: "chat.status.cancelled",
  canceled: "chat.status.cancelled",
  "awaiting result": "chat.status.awaitingResult",
  writing: "chat.status.writing",
  recorded: "chat.common.recorded",
};

/** Localizes a recorded tool status; unknown values stay verbatim. */
export function toolStatusLabel(
  status: string | null | undefined,
  t: Translate,
  fallback: string,
): string {
  if (!status) {
    return fallback;
  }
  const key = TOOL_STATUS_KEYS[status.toLowerCase()];
  return key ? t(key) : status;
}

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
