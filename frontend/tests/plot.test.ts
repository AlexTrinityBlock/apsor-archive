import { describe, expect, test } from "bun:test";

import {
  readCalculationResult,
  readPlotSpec,
} from "../src/app/chat/plot";

const plot = {
  version: 1,
  format: "plotly",
  title: "Memories per month",
  caption: "Counts from the archive timeline.",
  figure: {
    data: [{ type: "bar", x: ["Jan", "Feb"], y: [3, 5] }],
    layout: { xaxis: { title: { text: "Month" } } },
  },
  stats: { trace_count: 1, point_count: 2, byte_size: 156 },
};

describe("readPlotSpec", () => {
  test("reads a plot from a tool result envelope", () => {
    const spec = readPlotSpec({
      plot,
      tool: "render_plot",
      status: "ok",
      duration_ms: 2,
    });
    expect(spec?.title).toBe("Memories per month");
    expect(spec?.caption).toBe("Counts from the archive timeline.");
    expect(spec?.figure.data).toHaveLength(1);
    expect(spec?.stats).toEqual({
      traceCount: 1,
      pointCount: 2,
      byteSize: 156,
    });
  });

  test("accepts a bare plot spec and ignores blank captions", () => {
    const spec = readPlotSpec({ ...plot, caption: "   " });
    expect(spec?.caption).toBeNull();
  });

  test("rejects wrong versions, formats, and titles", () => {
    expect(readPlotSpec({ ...plot, version: 2 })).toBeNull();
    expect(readPlotSpec({ ...plot, format: "vega" })).toBeNull();
    expect(readPlotSpec({ ...plot, title: "  " })).toBeNull();
  });

  test("rejects missing, empty, and oversized trace lists", () => {
    const traces = Array.from({ length: 13 }, () => ({ type: "bar" }));
    expect(readPlotSpec({ ...plot, figure: { data: [] } })).toBeNull();
    expect(readPlotSpec({ ...plot, figure: { data: traces } })).toBeNull();
    expect(readPlotSpec({ ...plot, figure: { data: [null] } })).toBeNull();
  });

  test("never throws on hostile input", () => {
    expect(readPlotSpec(null)).toBeNull();
    expect(readPlotSpec("plot")).toBeNull();
    expect(readPlotSpec([plot])).toBeNull();
    expect(readPlotSpec({ plot: { ...plot, figure: { data: "x" } } })).toBeNull();
  });
});

describe("readCalculationResult", () => {
  test("reads a successful calculator result", () => {
    expect(
      readCalculationResult({
        expression: "((12.5 * 4) + 7) / 3",
        result: 19,
        formatted: "19",
        tool: "calculate",
        status: "ok",
      }),
    ).toEqual({
      expression: "((12.5 * 4) + 7) / 3",
      result: 19,
      formatted: "19",
    });
  });

  test("rejects other tools and incomplete results", () => {
    expect(
      readCalculationResult({
        expression: "1 + 1",
        result: 2,
        formatted: "2",
        tool: "render_plot",
      }),
    ).toBeNull();
    expect(
      readCalculationResult({
        expression: "1 + 1",
        result: null,
        formatted: "2",
        tool: "calculate",
      }),
    ).toBeNull();
    expect(readCalculationResult(null)).toBeNull();
  });
});
