/**
 * Defensive readers for the plot and calculator tool payloads.
 *
 * Tool result `data` is open JSON: old entries, partial streams, or a manual
 * SQL edit can all put a shape here that the current UI does not expect. These
 * readers narrow every field and return `null` instead of throwing, so one bad
 * row can never crash the transcript.
 */

export interface PlotSpec {
  readonly version: 1;
  readonly format: "plotly";
  readonly title: string;
  readonly caption: string | null;
  readonly figure: {
    readonly data: ReadonlyArray<Record<string, unknown>>;
    readonly layout?: Record<string, unknown>;
  };
  readonly stats: {
    readonly traceCount: number;
    readonly pointCount: number;
  } | null;
}

export interface CalculationResult {
  readonly expression: string;
  readonly result: number;
  readonly formatted: string;
}

const PLOT_VERSION = 1;
const PLOT_FORMAT = "plotly";
const MAX_PLOT_TRACES = 12;
const CALCULATE_TOOL = "calculate";

function asRecord(value: unknown): Readonly<Record<string, unknown>> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  return value.trim().length > 0 ? value.trim() : null;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readStats(value: unknown): PlotSpec["stats"] {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  // The backend writes snake_case; accept camelCase for hand-seeded entries.
  const traceCount =
    finiteNumber(record.trace_count) ?? finiteNumber(record.traceCount);
  const pointCount =
    finiteNumber(record.point_count) ?? finiteNumber(record.pointCount);
  if (traceCount === null || pointCount === null) {
    return null;
  }
  return { traceCount, pointCount };
}

function readFigure(value: unknown): PlotSpec["figure"] | null {
  const figure = asRecord(value);
  if (!figure) {
    return null;
  }
  const rawTraces = figure.data;
  if (
    !Array.isArray(rawTraces) ||
    rawTraces.length < 1 ||
    rawTraces.length > MAX_PLOT_TRACES
  ) {
    return null;
  }
  const data: Record<string, unknown>[] = [];
  for (const item of rawTraces) {
    const trace = asRecord(item);
    if (!trace) {
      return null;
    }
    data.push({ ...trace });
  }

  const rawLayout = figure.layout;
  if (rawLayout === undefined || rawLayout === null) {
    return { data };
  }
  const layout = asRecord(rawLayout);
  if (!layout) {
    return null;
  }
  return { data, layout: { ...layout } };
}

/**
 * Read the inline plot from a tool result `data` payload.
 *
 * The persisted shape is `{ plot: PlotSpec, ...tool meta }`; a bare PlotSpec is
 * accepted too so a future caller can pass the plot object directly.
 */
export function readPlotSpec(data: unknown): PlotSpec | null {
  const record = asRecord(data);
  if (!record) {
    return null;
  }
  const wrapped = asRecord(record.plot);
  const candidate = wrapped ?? record;
  if (
    candidate.version !== PLOT_VERSION ||
    candidate.format !== PLOT_FORMAT
  ) {
    return null;
  }
  const title = nonEmptyString(candidate.title);
  if (!title) {
    return null;
  }
  const figure = readFigure(candidate.figure);
  if (!figure) {
    return null;
  }
  return {
    version: PLOT_VERSION,
    format: PLOT_FORMAT,
    title,
    caption: nonEmptyString(candidate.caption),
    figure,
    stats: readStats(candidate.stats),
  };
}

/** Read the calculator result from a `calculate` tool result `data` payload. */
export function readCalculationResult(data: unknown): CalculationResult | null {
  const record = asRecord(data);
  if (!record || record.tool !== CALCULATE_TOOL) {
    return null;
  }
  const expression = nonEmptyString(record.expression);
  const formatted = nonEmptyString(record.formatted);
  const result = finiteNumber(record.result);
  if (!expression || !formatted || result === null) {
    return null;
  }
  return { expression, result, formatted };
}
