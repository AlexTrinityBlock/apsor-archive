/** URL helpers shared by the search controls and the debounced query sync. */

export const DEFAULT_RESULT_NUMBER = 2;

const MIN_RESULT_NUMBER = 1;
const MAX_RESULT_NUMBER = 10;

/** Clamps any numeric value into the 1–10 range the UI exposes. */
export function clampResultNumber(value: number): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_RESULT_NUMBER;
  }
  return Math.min(MAX_RESULT_NUMBER, Math.max(MIN_RESULT_NUMBER, Math.round(value)));
}

/** Reads a result number from the URL and clamps it to the supported range. */
export function parseResultNumber(value: string | null): number {
  if (value === null || value.trim().length === 0) {
    return DEFAULT_RESULT_NUMBER;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_RESULT_NUMBER;
  }
  return clampResultNumber(parsed);
}

function clone(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams();
  const query = params.get("query");
  if (query !== null && query.trim().length > 0) {
    next.set("query", query.trim());
  }
  const resultNumber = params.get("result_number");
  if (resultNumber !== null) {
    const parsed = Number.parseInt(resultNumber, 10);
    if (Number.isFinite(parsed) && clampResultNumber(parsed) !== DEFAULT_RESULT_NUMBER) {
      next.set("result_number", String(clampResultNumber(parsed)));
    }
  }
  if (params.get("include_history") === "true") {
    next.set("include_history", "true");
  }
  return next;
}

/** Writes only the query into an existing search URL, trimming it. */
export function withQuery(params: URLSearchParams, query: string): URLSearchParams {
  const next = clone(params);
  const trimmed = query.trim();
  if (trimmed.length > 0) {
    next.set("query", trimmed);
  } else {
    next.delete("query");
  }
  return next;
}

/** Writes only the per-kind result count, omitting the default. */
export function withResultNumber(
  params: URLSearchParams,
  resultNumber: number,
): URLSearchParams {
  const next = clone(params);
  const clamped = clampResultNumber(resultNumber);
  if (clamped === DEFAULT_RESULT_NUMBER) {
    next.delete("result_number");
  } else {
    next.set("result_number", String(clamped));
  }
  return next;
}

/** Writes only the include-history flag, omitting the default. */
export function withIncludeHistory(
  params: URLSearchParams,
  includeHistory: boolean,
): URLSearchParams {
  const next = clone(params);
  if (includeHistory) {
    next.set("include_history", "true");
  } else {
    next.delete("include_history");
  }
  return next;
}
