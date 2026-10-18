/** URL helpers shared by the search controls and the suggested-query links. */

export const DEFAULT_RESULT_NUMBER = 2;

const MIN_RESULT_NUMBER = 1;
const MAX_RESULT_NUMBER = 10;

/** Reads a result number from the URL and clamps it to the supported range. */
export function parseResultNumber(value: string | null): number {
  const parsed = Number.parseInt(value ?? "", 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_RESULT_NUMBER;
  }
  return Math.min(MAX_RESULT_NUMBER, Math.max(MIN_RESULT_NUMBER, parsed));
}

/**
 * Rebuilds the search query string from the whitelisted view state, omitting
 * defaults so a clean search keeps a clean URL.
 */
export function buildSearchParams(
  query: string,
  resultNumber: number,
  includeHistory: boolean,
): URLSearchParams {
  const params = new URLSearchParams();
  const trimmed = query.trim();
  if (trimmed.length > 0) {
    params.set("query", trimmed);
  }
  if (resultNumber !== DEFAULT_RESULT_NUMBER) {
    params.set("result_number", String(resultNumber));
  }
  if (includeHistory) {
    params.set("include_history", "true");
  }
  return params;
}

/** Builds an encoded search URL for links and suggestions. */
export function buildSearchUrl(
  query: string,
  resultNumber = DEFAULT_RESULT_NUMBER,
  includeHistory = false,
): string {
  const params = buildSearchParams(query, resultNumber, includeHistory).toString();
  return params.length > 0 ? `/search?${params}` : "/search";
}
