// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { readToolOutput } from "./tool-output";
import type { ResourceMeta } from "./types";

const RESOURCE: ResourceMeta = {
  resourceType: "file",
  resourceId: 7,
  viewerUrl: "/viewer/file/7",
  title: "report.pdf",
  mimeType: "application/pdf",
  rawFilePath: "uploads/report.pdf",
  chunk: null,
};

function plotData(): Record<string, unknown> {
  return {
    tool: "render_plot",
    plot: {
      version: 1,
      format: "plotly",
      title: "Monthly totals",
      caption: null,
      figure: { data: [{ type: "bar", x: ["Jan"], y: [4] }] },
      stats: null,
    },
  };
}

describe("readToolOutput", () => {
  test("a valid chart is presented output", () => {
    const output = readToolOutput({ data: plotData(), resource: null });

    expect(output.hasPlot).toBe(true);
    expect(output.presented).toBe(true);
  });

  test("a presented resource is output even without a preview", () => {
    const output = readToolOutput({ data: null, resource: RESOURCE });

    expect(output.hasResource).toBe(true);
    expect(output.presented).toBe(true);
  });

  test("diagnostic tool results stay folded", () => {
    const output = readToolOutput({
      data: { tool: "web_search", results: [] },
      resource: null,
    });

    expect(output.hasPlot).toBe(false);
    expect(output.hasResource).toBe(false);
    expect(output.presented).toBe(false);
  });

  test("a malformed plot is not presented as a chart", () => {
    const output = readToolOutput({
      data: { tool: "render_plot", plot: { title: "Broken" } },
      resource: null,
    });

    expect(output.hasPlot).toBe(false);
    expect(output.presented).toBe(false);
  });
});
