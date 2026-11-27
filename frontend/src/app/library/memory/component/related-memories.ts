import type { TranslationKey } from "../../../i18n";

/** Display order for relation reasons; unknown reasons are dropped. */
export const RELATED_REASON_ORDER = ["similar", "keyword", "summary", "nearby"] as const;

export type RelatedReason = (typeof RELATED_REASON_ORDER)[number];

const REASON_KEYS: Record<RelatedReason, TranslationKey> = {
  similar: "memory.related.reason.similar",
  keyword: "memory.related.reason.keyword",
  summary: "memory.related.reason.summary",
  nearby: "memory.related.reason.nearby",
};

function isRelatedReason(value: string): value is RelatedReason {
  return (RELATED_REASON_ORDER as readonly string[]).includes(value);
}

/** Normalize API reasons into a stable, de-duplicated display order. */
export function orderRelatedReasons(reasons: readonly string[]): RelatedReason[] {
  const present = new Set(reasons.filter(isRelatedReason));
  return RELATED_REASON_ORDER.filter((reason) => present.has(reason));
}

/** The chip label key for one reason. */
export function relatedReasonKey(reason: RelatedReason): TranslationKey {
  return REASON_KEYS[reason];
}

/** A two-line preview: collapse whitespace and clip at a word boundary. */
export function clipRelatedPreview(content: string, limit = 180): string {
  const compact = content.replace(/\s+/g, " ").trim();
  if (compact.length <= limit) {
    return compact;
  }
  const slice = compact.slice(0, limit);
  const lastSpace = slice.lastIndexOf(" ");
  const cut = lastSpace > limit * 0.6 ? slice.slice(0, lastSpace) : slice;
  return `${cut.trimEnd()}…`;
}
