import { memo, useEffect, useMemo, useRef, useState } from "react";
import type {
  Config,
  Data,
  Layout,
  ModeBarDefaultButtons,
} from "plotly.js";

import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { readPlotSpec, type PlotSpec } from "../plot";
import { isRecord } from "../types";

/**
 * The small runtime surface PlotBlock needs from the Plotly bundle.
 *
 * `plotly.js-dist-min` ships the runtime bundle; `@types/plotly.js` supplies
 * the published public shape. Both describe the same API, so one boundary cast
 * keeps the rest of the component typed without `any`.
 */
interface PlotlyRuntime {
  react(
    element: HTMLElement,
    data: Data[],
    layout: Partial<Layout>,
    config: Partial<Config>,
  ): Promise<unknown>;
  purge(element: HTMLElement): void;
  toImage(
    element: HTMLElement,
    options: { format: "png"; width: number; height: number },
  ): Promise<string>;
  readonly Plots: { resize(element: HTMLElement): void };
}

type PlotStatus = "loading" | "ready" | "error";

/**
 * Plotly traces that always live in a 3D scene.
 * 一律位於 3D scene 的 Plotly trace 型別。
 */
const SCENE_TRACE_TYPES = new Set([
  "scatter3d",
  "surface",
  "mesh3d",
  "isosurface",
  "volume",
  "streamtube",
  "cone",
]);

/**
 * A figure is 3D when it declares a scene or uses a scene-only trace type.
 * 圖形宣告 scene 或使用僅限 3D 的 trace 型別時，即視為 3D。
 */
function isThreeDimensional(spec: PlotSpec): boolean {
  if (isRecord(spec.figure.layout?.scene)) {
    return true;
  }
  return spec.figure.data.some((trace) => {
    const type = trace.type;
    return typeof type === "string" && SCENE_TRACE_TYPES.has(type.toLowerCase());
  });
}

/**
 * Build the Plotly config for this render.
 * 為這一次繪製建立 Plotly config。
 *
 * 2D keeps the transcript's scroll position: no wheel zoom and no modebar.
 * 3D may capture the wheel for camera zoom and exposes a hover modebar without
 * the image/cloud/external-editor buttons the card already replaces.
 * 2D 保留對話串的捲動：不攔截滾輪、不顯示模式列。3D 允許滾輪縮放相機，
 * 並在游標移入時顯示不含下載、雲端與外部編輯按鈕的模式列。
 */
function plotConfig(is3d: boolean): Partial<Config> {
  return {
    responsive: true,
    displaylogo: false,
    displayModeBar: is3d ? "hover" : false,
    showSendToCloud: false,
    showEditInChartStudio: false,
    scrollZoom: is3d,
    modeBarButtonsToRemove: is3d
      ? ([
          "toImage",
          "sendDataToCloud",
          // Plotly honors this name at runtime; @types/plotly.js omits it.
          // Plotly 執行時接受這個名稱；@types/plotly.js 未列出。
          "editInChartStudio",
        ] as unknown as ModeBarDefaultButtons[])
      : undefined,
    doubleClick: "reset",
  };
}

const MAX_TABLE_ROWS = 30;

interface PlotTable {
  readonly columns: readonly [string, string];
  readonly rows: ReadonlyArray<readonly [string, string]>;
  readonly total: number;
}

/** Matches Plotly's cartesian axis layout keys: xaxis, yaxis2, xaxis3, ... */
const AXIS_KEY = /^[xy]axis\d*$/;

function cssToken(name: string, fallback: string): string {
  if (typeof document === "undefined") {
    return fallback;
  }
  try {
    const value = getComputedStyle(document.documentElement)
      .getPropertyValue(name)
      .trim();
    return value.length > 0 ? value : fallback;
  } catch {
    return fallback;
  }
}

function themedLayout(
  source: Record<string, unknown> | undefined,
): Partial<Layout> {
  const layout: Record<string, unknown> = { ...(source ?? {}) };
  delete layout.width;
  delete layout.height;
  // The figcaption carries the title, so a model-supplied layout title would
  // duplicate it.
  delete layout.title;

  const fontFamily = cssToken("--mono-font", "system-ui, sans-serif");
  const inkColor = cssToken("--mono-ink", "#1c1c1a");
  const gridColor = cssToken("--mono-grid", "#deddd6");
  const mutedColor = cssToken("--mono-muted", "#8f8e88");

  for (const [key, value] of Object.entries(layout)) {
    if (!AXIS_KEY.test(key) || !isRecord(value)) {
      continue;
    }
    const tickfont = isRecord(value.tickfont) ? value.tickfont : {};
    layout[key] = {
      ...value,
      gridcolor: gridColor,
      zerolinecolor: gridColor,
      linecolor: gridColor,
      tickfont: {
        ...tickfont,
        color: mutedColor,
        size: 11,
      },
    };
  }

  const font = isRecord(layout.font) ? layout.font : {};
  return {
    ...layout,
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {
      ...font,
      family: fontFamily,
      color: inkColor,
    },
  } as Partial<Layout>;
}

function scalarColumn(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const cells: string[] = [];
  for (const item of value) {
    if (item === null || item === undefined) {
      cells.push("");
      continue;
    }
    if (typeof item === "string") {
      cells.push(item);
      continue;
    }
    if (typeof item === "number" && Number.isFinite(item)) {
      cells.push(String(item));
      continue;
    }
    return null;
  }
  return cells;
}

function axisLabel(
  layout: Record<string, unknown> | undefined,
  axis: "xaxis" | "yaxis",
  fallback: string,
): string {
  const axisRecord = isRecord(layout?.[axis]) ? layout[axis] : null;
  const title = axisRecord?.title;
  if (typeof title === "string" && title.trim().length > 0) {
    return title;
  }
  if (isRecord(title)) {
    const text = title.text;
    if (typeof text === "string" && text.trim().length > 0) {
      return text;
    }
  }
  // Plotly's own axis keys, used only when the agent supplied no axis title.
  return fallback;
}

function pairTable(
  left: readonly string[],
  right: readonly string[],
  columns: readonly [string, string],
): PlotTable | null {
  const total = Math.min(left.length, right.length);
  if (total === 0) {
    return null;
  }
  const rows: Array<readonly [string, string]> = [];
  const shown = Math.min(total, MAX_TABLE_ROWS);
  for (let index = 0; index < shown; index += 1) {
    rows.push([left[index] ?? "", right[index] ?? ""]);
  }
  return { columns, rows, total };
}

/** Build a readable table for a single simple x/y or labels/values trace. */
function buildPlotTable(spec: PlotSpec): PlotTable | null {
  if (spec.figure.data.length !== 1) {
    return null;
  }
  const trace = spec.figure.data[0];
  // A 3D trace has a z channel; an x/y-only table would misrepresent it.
  // 3D trace 有 z 軸；只列 x/y 會誤導，因此不提供表格替代。
  const traceType = typeof trace.type === "string" ? trace.type.toLowerCase() : "";
  if (trace.z !== undefined || SCENE_TRACE_TYPES.has(traceType)) {
    return null;
  }
  const x = scalarColumn(trace.x);
  const y = scalarColumn(trace.y);
  if (x && y) {
    return pairTable(x, y, [
      axisLabel(spec.figure.layout, "xaxis", "x"),
      axisLabel(spec.figure.layout, "yaxis", "y"),
    ]);
  }
  const labels = scalarColumn(trace.labels);
  const values = scalarColumn(trace.values);
  if (labels && values) {
    return pairTable(labels, values, ["labels", "values"]);
  }
  return null;
}

const PNG_DATA_PREFIX = "data:image/png;base64,";

function pngBlobFromDataUrl(dataUrl: string): Blob | null {
  if (!dataUrl.startsWith(PNG_DATA_PREFIX)) {
    return null;
  }
  try {
    const binary = atob(dataUrl.slice(PNG_DATA_PREFIX.length));
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return new Blob([bytes], { type: "image/png" });
  } catch {
    return null;
  }
}

function downloadFileName(title: string): string {
  const base = title
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  return `${base.length > 0 ? base : "plot"}.png`;
}

interface PlotBlockProps {
  /** Tool result `data`; a `{ plot: PlotSpec }` envelope or a bare PlotSpec. */
  readonly data: unknown;
}

/** One persisted or streaming Plotly chart with an accessible data table. */
export const PlotBlock = memo(function PlotBlock({ data }: PlotBlockProps) {
  const { t, formatNumber } = useI18n();
  const spec = useMemo(() => readPlotSpec(data), [data]);
  const is3d = useMemo(() => (spec ? isThreeDimensional(spec) : false), [spec]);
  const config = useMemo(() => plotConfig(is3d), [is3d]);
  const table = useMemo(() => (spec ? buildPlotTable(spec) : null), [spec]);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const plotlyRef = useRef<PlotlyRuntime | null>(null);
  const [status, setStatus] = useState<PlotStatus>("loading");
  const [downloading, setDownloading] = useState(false);
  const [downloadFailed, setDownloadFailed] = useState(false);

  useEffect(() => {
    const element = canvasRef.current;
    if (!element || !spec) {
      return;
    }

    let cancelled = false;
    let observer: ResizeObserver | null = null;
    let loaded: PlotlyRuntime | null = null;

    const draw = async (): Promise<void> => {
      try {
        const module = await import("plotly.js-dist-min");
        if (cancelled) {
          return;
        }
        const plotly = module.default as unknown as PlotlyRuntime;
        loaded = plotly;
        plotlyRef.current = plotly;
        await plotly.react(
          element,
          spec.figure.data as unknown as Data[],
          themedLayout(spec.figure.layout),
          config,
        );
        if (cancelled) {
          return;
        }
        setStatus("ready");
        if (typeof ResizeObserver === "undefined") {
          return;
        }
        observer = new ResizeObserver(() => {
          if (!element.isConnected) {
            return;
          }
          plotlyRef.current?.Plots.resize(element);
        });
        observer.observe(element);
      } catch {
        if (!cancelled) {
          setStatus("error");
        }
      }
    };

    void draw();

    return () => {
      cancelled = true;
      observer?.disconnect();
      if (loaded) {
        loaded.purge(element);
        if (plotlyRef.current === loaded) {
          plotlyRef.current = null;
        }
      }
    };
  }, [spec, is3d, config]);

  if (!spec) {
    return null;
  }

  const title = spec.title || t("chat.plot.title");

  const handleDownload = async (): Promise<void> => {
    const element = canvasRef.current;
    const plotly = plotlyRef.current;
    if (!element || !plotly || status !== "ready" || downloading) {
      return;
    }
    setDownloading(true);
    setDownloadFailed(false);
    try {
      const dataUrl = await plotly.toImage(element, {
        format: "png",
        width: 1200,
        height: 720,
      });
      const blob = pngBlobFromDataUrl(dataUrl);
      if (!blob) {
        setDownloadFailed(true);
        return;
      }
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = downloadFileName(spec.title);
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch {
      setDownloadFailed(true);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <figure
      className="chat-plot"
      aria-label={title}
      aria-busy={status === "loading" ? true : undefined}
    >
      <figcaption className="chat-plot__caption">
        <div className="chat-plot__head">
          <span className="chat-plot__title">{title}</span>
          <span className="chat-plot__actions">
            <button
              type="button"
              className="chat-plot__download"
              onClick={() => {
                void handleDownload();
              }}
              disabled={status !== "ready" || downloading}
              title={t("chat.plot.download")}
            >
              <Icon name="arrow-down" size={11} />
              <span>{t("chat.plot.download")}</span>
            </button>
          </span>
        </div>
        {spec.caption ? (
          <p className="chat-plot__note">{spec.caption}</p>
        ) : null}
        {is3d ? (
          <p className="chat-plot__hint">{t("chat.plot.zoomHint")}</p>
        ) : null}
      </figcaption>

      <div className="chat-plot__canvas">
        <div
          ref={canvasRef}
          className={
            is3d ? "chat-plot__target chat-plot__target--3d" : "chat-plot__target"
          }
          aria-hidden="true"
        />
        {status === "loading" ? (
          <p className="chat-plot__state" role="status">
            {t("chat.plot.loading")}
          </p>
        ) : null}
        {status === "error" ? (
          <p className="chat-plot__error" role="alert">
            {t("chat.plot.error")}
          </p>
        ) : null}
      </div>

      {downloadFailed ? (
        <p className="chat-plot__error" role="alert">
          {t("chat.plot.error")}
        </p>
      ) : null}

      <details className="chat-plot__data">
        <summary>{t("chat.plot.dataTable")}</summary>
        {table ? (
          <>
            <table className="chat-plot__table">
              <caption className="visually-hidden">
                {t("chat.plot.dataTable")}
              </caption>
              <thead>
                <tr>
                  {table.columns.map((column, columnIndex) => (
                    <th key={`${column}-${columnIndex}`} scope="col">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    <td>{row[0]}</td>
                    <td>{row[1]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {table.total > table.rows.length ? (
              <p className="chat-plot__truncated">
                {t("chat.plot.truncated", {
                  shown: formatNumber(table.rows.length),
                  total: formatNumber(table.total),
                })}
              </p>
            ) : null}
          </>
        ) : (
          <p className="chat-plot__empty">{t("chat.plot.dataTableEmpty")}</p>
        )}
      </details>
    </figure>
  );
});
