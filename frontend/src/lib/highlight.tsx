import type { ReactNode } from "react";

const MAX_SNIPPET = 420;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function queryTerms(query: string): string[] {
  return Array.from(
    new Set(
      query
        .split(/\s+/)
        .map((term) => term.trim())
        .filter((term) => term.length > 0),
    ),
  ).sort((left, right) => right.length - left.length);
}

/**
 * Returns a short passage around the first query term so a result can show the
 * matching grain without rendering an entire 800-character chunk.
 */
export function snippetAround(text: string, query: string, limit = MAX_SNIPPET): string {
  const compact = text.replace(/\s+/g, " ").trim();
  if (compact.length <= limit) {
    return compact;
  }
  const lower = compact.toLowerCase();
  const first = queryTerms(query)
    .map((term) => lower.indexOf(term.toLowerCase()))
    .filter((index) => index >= 0)
    .sort((left, right) => left - right)[0];
  const start = first === undefined ? 0 : Math.max(0, first - Math.floor(limit / 3));
  const end = Math.min(compact.length, start + limit);
  const prefix = start > 0 ? "\u2026" : "";
  const suffix = end < compact.length ? "\u2026" : "";
  return `${prefix}${compact.slice(start, end).trim()}${suffix}`;
}

/**
 * Splits text into React nodes and wraps query matches in `<mark>`. React
 * escapes the text, so no HTML from a file or memory can execute.
 */
export function highlightTerms(text: string, query: string): ReactNode {
  const terms = queryTerms(query);
  if (terms.length === 0) {
    return text;
  }
  // Terms are escaped above, so the dynamic alternation cannot inject syntax.
  // eslint-disable-next-line security/detect-non-literal-regexp
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
  // eslint-disable-next-line security/detect-non-literal-regexp
  const matcher = new RegExp(`^(?:${terms.map(escapeRegExp).join("|")})$`, "i");
  const parts = text.split(pattern);
  return parts.map((part, index) =>
    matcher.test(part) ? (
      <mark className="search-mark" key={`${part}-${index}`}>
        {part}
      </mark>
    ) : (
      part
    ),
  );
}
