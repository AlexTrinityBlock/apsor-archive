/**
 * Classifies a tool result by what the reader should see immediately.
 *
 * A chart or a presented resource is the model's output to the reader, so the
 * transcript renders it outside the collapsed tool details. Every other result
 * is diagnostic and stays folded until the reader asks for it.
 */
import { readPlotSpec } from "./plot";
import type { ToolResultMeta } from "./types";

export interface ToolOutput {
  readonly hasPlot: boolean;
  readonly hasResource: boolean;
  readonly presented: boolean;
}

export function readToolOutput(
  meta: Pick<ToolResultMeta, "data" | "resource">,
): ToolOutput {
  const hasPlot = readPlotSpec(meta.data) !== null;
  const hasResource = meta.resource !== null;
  return {
    hasPlot,
    hasResource,
    presented: hasPlot || hasResource,
  };
}
