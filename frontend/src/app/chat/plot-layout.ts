/**
 * Width hints for an inline Plotly chart.
 *
 * The chat card is narrower than most charts assume. When the model supplies
 * long category labels and pins a tick angle, Plotly cannot auto-rotate them,
 * so the fixed angle makes the labels collide. The hint below gives those
 * charts enough width for their labels; the card scrolls horizontally instead
 * of compressing the plotting area.
 */

import type { PlotSpec } from "./plot";
import { isRecord } from "./types";

/** A label wider than this no longer fits a typical chat card unaided. */
const LONG_LABEL_PX = 48;
/** Approximate width of one CJK character at the 11px tick font. */
const WIDE_CHAR_PX = 11;
/** Approximate width of one Latin character at the 11px tick font. */
const NARROW_CHAR_PX = 6;
/** A chart wider than this scrolls; it never asks for an unbounded canvas. */
const MAX_CHART_WIDTH = 1200;
/** Plotly's default margins when the figure does not set one. */
const DEFAULT_LEFT_MARGIN = 80;
const DEFAULT_RIGHT_MARGIN = 80;
/** A vertical axis still needs room for its numeric labels and title. */
const MIN_LEFT_MARGIN = 80;
const MIN_RIGHT_MARGIN = 16;
/** A right-side legend takes its own column inside the chart. */
const LEGEND_MIN_WIDTH = 80;
const LEGEND_MAX_WIDTH = 260;
/** Room for the plotting area beside a horizontal bar's category labels. */
const HORIZONTAL_PLOT_FLOOR = 300;
const HORIZONTAL_LABEL_PAD = 24;
const HORIZONTAL_LABEL_MAX = 280;

function characterWidth(character: string): number {
  const codePoint = character.codePointAt(0) ?? 0;
  if (
    (codePoint >= 0x1100 && codePoint <= 0x115f) ||
    (codePoint >= 0x2e80 && codePoint <= 0xa4cf) ||
    (codePoint >= 0xac00 && codePoint <= 0xd7a3) ||
    (codePoint >= 0xf900 && codePoint <= 0xfaff) ||
    (codePoint >= 0xfe30 && codePoint <= 0xfe6f) ||
    (codePoint >= 0xff00 && codePoint <= 0xff60) ||
    (codePoint >= 0xffe0 && codePoint <= 0xffe6) ||
    codePoint >= 0x1f000
  ) {
    return WIDE_CHAR_PX;
  }
  return NARROW_CHAR_PX;
}

function labelWidth(label: string): number {
  let width = 0;
  for (const character of label) {
    width += characterWidth(character);
  }
  return width;
}

function longestLabel(labels: readonly string[]): number {
  let longest = 0;
  for (const label of labels) {
    longest = Math.max(longest, labelWidth(label));
  }
  return longest;
}

/** Collect unique string values on one axis; numbers stay off the cat axis. */
function categoryLabels(
  traces: ReadonlyArray<Record<string, unknown>>,
  axis: "x" | "y",
): string[] {
  const labels = new Set<string>();
  for (const trace of traces) {
    const values = trace[axis];
    if (!Array.isArray(values)) {
      continue;
    }
    for (const value of values) {
      if (typeof value === "string") {
        labels.add(value);
      }
    }
  }
  return [...labels];
}

function effectiveMargin(
  layout: Record<string, unknown> | undefined,
  side: "l" | "r",
): number {
  const fallback = side === "l" ? DEFAULT_LEFT_MARGIN : DEFAULT_RIGHT_MARGIN;
  const margin = layout?.margin;
  if (!isRecord(margin)) {
    return fallback;
  }
  const value = margin[side];
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : fallback;
}

/** Room a vertical legend needs beside the plotting area, if it exists. */
function rightLegendWidth(
  traces: ReadonlyArray<Record<string, unknown>>,
  layout: Record<string, unknown> | undefined,
): number {
  const showLegend = layout?.showlegend;
  if (showLegend === false || (showLegend === undefined && traces.length < 2)) {
    return 0;
  }
  const legend = layout?.legend;
  if (isRecord(legend) && legend.orientation === "h") {
    return 0;
  }
  let longest = 0;
  for (const trace of traces) {
    const name = trace.name;
    if (typeof name === "string") {
      longest = Math.max(longest, labelWidth(name));
    }
  }
  return Math.min(
    Math.max(LEGEND_MIN_WIDTH, longest + 40),
    LEGEND_MAX_WIDTH,
  );
}

function tickAngle(
  layout: Record<string, unknown> | undefined,
  axis: "xaxis" | "yaxis",
): number | null {
  const axisLayout = layout?.[axis];
  if (!isRecord(axisLayout)) {
    return null;
  }
  const value = axisLayout.tickangle;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** A horizontal bar puts its categories on the y axis. */
function hasHorizontalBars(
  traces: ReadonlyArray<Record<string, unknown>>,
): boolean {
  return traces.some(
    (trace) =>
      trace.orientation === "h" &&
      (trace.type === "bar" || trace.type === undefined),
  );
}

function xAxisWidth(
  labels: readonly string[],
  angle: number | null,
  leftMargin: number,
  rightMargin: number,
): number {
  if (angle === null) {
    // Plotly auto-rotates unpinned category labels to fit the available width.
    return 0;
  }
  const longest = longestLabel(labels);
  const denseUnrotated = Math.abs(angle) % 180 === 0 && labels.length > 6;
  if (longest < LONG_LABEL_PX && !denseUnrotated) {
    // Short labels fit side by side at the pinned angle.
    return 0;
  }
  // A pinned 0-degree axis has no auto-rotation to save it, so it gets a
  // full-width slot per label. Rotated labels only need their projection.
  const degrees = Math.abs(angle) % 180;
  const radians = (degrees * Math.PI) / 180;
  const slot =
    degrees === 0
      ? longest + 18
      : Math.max(22, Math.cos(radians) * longest + 14);
  return leftMargin + labels.length * slot + rightMargin;
}

function yAxisWidth(
  labels: readonly string[],
  leftMargin: number,
  rightMargin: number,
): number {
  const longest = longestLabel(labels);
  if (longest < LONG_LABEL_PX) {
    return 0;
  }
  const labelSpace = Math.min(
    longest + HORIZONTAL_LABEL_PAD,
    HORIZONTAL_LABEL_MAX,
  );
  const left = Math.max(leftMargin, labelSpace);
  return left + HORIZONTAL_PLOT_FLOOR + rightMargin;
}

/**
 * Minimum plot width that keeps a chart's category labels readable.
 *
 * Returns `0` when the chart can fit the chat card as-is. A positive value is
 * a pixel width for the plotting target; the card becomes horizontally
 * scrollable when that width is wider than its viewport.
 */
export function plotMinimumWidth(spec: PlotSpec): number {
  const traces = spec.figure.data;
  if (traces.length === 0) {
    return 0;
  }
  const xLabels = categoryLabels(traces, "x");
  const yLabels = categoryLabels(traces, "y");
  const layout = spec.figure.layout;
  // A heatmap or a two-category chart also uses long text on the y axis.
  const yLabelSpace =
    yLabels.length > 0
      ? Math.min(
          longestLabel(yLabels) + HORIZONTAL_LABEL_PAD,
          HORIZONTAL_LABEL_MAX,
        )
      : 0;
  const leftMargin = Math.max(
    effectiveMargin(layout, "l"),
    MIN_LEFT_MARGIN,
    yLabelSpace,
  );
  const rightMargin = Math.max(
    effectiveMargin(layout, "r"),
    MIN_RIGHT_MARGIN,
    rightLegendWidth(traces, layout),
  );
  let width = 0;
  if (hasHorizontalBars(traces) && yLabels.length > 0) {
    width = yAxisWidth(yLabels, leftMargin, rightMargin);
  } else if (xLabels.length > 0) {
    width = xAxisWidth(
      xLabels,
      tickAngle(layout, "xaxis"),
      leftMargin,
      rightMargin,
    );
  } else if (yLabels.length > 0) {
    width = yAxisWidth(yLabels, leftMargin, rightMargin);
  }
  if (width <= 0) {
    return 0;
  }
  return Math.min(Math.round(width), MAX_CHART_WIDTH);
}
