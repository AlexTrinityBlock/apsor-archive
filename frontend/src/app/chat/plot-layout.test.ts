// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { plotMinimumWidth } from "./plot-layout";
import type { PlotSpec } from "./plot";

function spec(
  data: ReadonlyArray<Record<string, unknown>>,
  layout?: Record<string, unknown>,
): PlotSpec {
  return {
    version: 1,
    format: "plotly",
    title: "Test chart",
    caption: null,
    figure: layout === undefined ? { data } : { data, layout },
    stats: null,
  };
}

const LONG_CATEGORIES = [
  "內部威脅分析師",
  "網路風險分析師",
  "滲透測試員",
  "CISO",
  "安全工程師",
  "安全分析師",
  "全體平均",
  "資安資料科學家",
  "AI 安全工程師",
];

describe("plotMinimumWidth", () => {
  test("widens a pinned rotated category axis for long labels", () => {
    const width = plotMinimumWidth(
      spec([{ type: "bar", x: LONG_CATEGORIES, y: LONG_CATEGORIES.map(() => 1) }], {
        xaxis: { tickangle: -45 },
      }),
    );

    expect(width).toBeGreaterThan(600);
    expect(width).toBeLessThanOrEqual(1200);
  });

  test("leaves a short category axis to Plotly's own rotation", () => {
    const labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"];
    const width = plotMinimumWidth(
      spec([{ type: "bar", x: labels, y: labels.map(() => 1) }]),
    );

    expect(width).toBe(0);
  });

  test("does not widen long labels when Plotly may auto-rotate them", () => {
    const width = plotMinimumWidth(
      spec([
        { type: "bar", x: LONG_CATEGORIES, y: LONG_CATEGORIES.map(() => 1) },
      ]),
    );

    expect(width).toBe(0);
  });

  test("widens an explicitly unrotated axis with many labels", () => {
    const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon2"];
    const width = plotMinimumWidth(
      spec([{ type: "bar", x: labels, y: labels.map(() => 1) }], {
        xaxis: { tickangle: 0 },
      }),
    );

    expect(width).toBeGreaterThan(0);
  });

  test("leaves room for long horizontal bar categories", () => {
    const width = plotMinimumWidth(
      spec([
        {
          type: "bar",
          orientation: "h",
          x: LONG_CATEGORIES.map(() => 1),
          y: LONG_CATEGORIES,
        },
      ]),
    );

    expect(width).toBeGreaterThanOrEqual(400);
    expect(width).toBeLessThanOrEqual(1200);
  });

  test("reserves a column for a right-side legend", () => {
    const data = [
      { type: "bar", x: LONG_CATEGORIES, y: LONG_CATEGORIES.map(() => 1), name: "第一次調查" },
      { type: "bar", x: LONG_CATEGORIES, y: LONG_CATEGORIES.map(() => 2), name: "第二次調查" },
    ];
    const layout = { xaxis: { tickangle: -45 } };
    const width = plotMinimumWidth(spec(data, layout));

    expect(width).toBeGreaterThan(776);
  });

  test("keeps a wide horizontal model margin", () => {
    const width = plotMinimumWidth(
      spec(
        [
          {
            type: "bar",
            orientation: "h",
            x: [1, 2],
            y: ["長分類標籤一", "長分類標籤二"],
          },
        ],
        { margin: { l: 320, r: 40 } },
      ),
    );

    expect(width).toBeGreaterThanOrEqual(660);
  });

  test("caps a pathological label count", () => {
    const labels = Array.from({ length: 200 }, (_, index) => `長分類標籤${index}`);
    const width = plotMinimumWidth(
      spec([{ type: "bar", x: labels, y: labels.map(() => 1) }], {
        xaxis: { tickangle: -45 },
      }),
    );

    expect(width).toBe(1200);
  });

  test("ignores a pie chart with no cartesian categories", () => {
    const width = plotMinimumWidth(
      spec([
        {
          type: "pie",
          labels: ["甲", "乙", "丙"],
          values: [1, 2, 3],
        },
      ]),
    );

    expect(width).toBe(0);
  });
});
