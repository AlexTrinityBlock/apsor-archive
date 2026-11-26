import { fetchViewerBinary, fileContentUrl } from "../../../viewer/component/viewer-utils";
import type { XlsxThumbSheet, XlsxThumbWorkerMessage } from "./xlsx-thumb-grid";

const SHEET_WIDTH = 480;
const SHEET_HEIGHT = 360;
const SHEET_QUALITY = 0.85;
// Base64 inflates bytes by about a third; 160k characters is roughly 120 KB.
const MAX_DATA_URL_LENGTH = 160_000;
const WORKER_TIMEOUT_MS = 8_000;

const PADDING_X = 16;
const HEADER_HEIGHT = 36;
const ROW_HEIGHT = 30;
const HEADER_FILL = "#eef2ec";
const HEADER_TEXT = "#2e4b3e";
const HEADER_RULE = "#d6ddd4";
const HEADER_ROW_FILL = "#f6f8f4";
const INK = "#1c1c1a";
const BODY_INK = "#4a4944";
const GRID_LINE = "#e2e5df";
const FONT_STACK =
  'Inter, "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", -apple-system, "Segoe UI", sans-serif';

function abortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("Aborted", "AbortError");
}

function parseWorkbookInWorker(
  buffer: ArrayBuffer,
  signal: AbortSignal,
): Promise<XlsxThumbSheet> {
  const worker = new Worker(new URL("./xlsx-thumb.worker.ts", import.meta.url), {
    type: "module",
  });

  const parsed = new Promise<XlsxThumbSheet>((resolve, reject) => {
    let settled = false;
    let timer: number | undefined;

    function cleanup(): void {
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
      signal.removeEventListener("abort", onAbort);
    }

    function settle(action: () => void): void {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      action();
    }

    function fail(reason: unknown): void {
      settle(() => reject(reason));
    }

    function onAbort(): void {
      fail(abortReason(signal));
    }

    timer = window.setTimeout(() => {
      fail(new Error("Spreadsheet thumbnail timed out"));
    }, WORKER_TIMEOUT_MS);
    signal.addEventListener("abort", onAbort, { once: true });

    worker.addEventListener("message", (event: MessageEvent<XlsxThumbWorkerMessage>) => {
      const message = event.data;
      if (message.type === "ok") {
        settle(() => resolve(message.sheet));
        return;
      }
      fail(new Error(message.message));
    });
    worker.addEventListener("error", (event) => {
      fail(new Error(event.message || "Spreadsheet worker failed"));
    });
    worker.addEventListener("messageerror", () => {
      fail(new Error("Spreadsheet worker returned an unreadable result"));
    });

    if (signal.aborted) {
      fail(abortReason(signal));
      return;
    }
    try {
      worker.postMessage(buffer, [buffer]);
    } catch (error) {
      fail(error);
    }
  });

  // The worker has to outlive the Promise constructor. Returning the Promise
  // from inside a `try/finally` would terminate the worker immediately and
  // leave the caller pending forever.
  return parsed.finally(() => worker.terminate());
}

function fitText(
  context: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
): string {
  if (context.measureText(text).width <= maxWidth) {
    return text;
  }
  let end = text.length;
  while (end > 0) {
    const candidate = `${text.slice(0, end)}…`;
    if (context.measureText(candidate).width <= maxWidth) {
      return candidate;
    }
    end -= 1;
  }
  return "";
}

function columnWidths(
  context: CanvasRenderingContext2D,
  sheet: XlsxThumbSheet,
): number[] {
  const columns = sheet.rows[0]?.length ?? 0;
  if (columns === 0) {
    return [];
  }
  const available = SHEET_WIDTH - PADDING_X * 2;
  const natural = Array.from({ length: columns }, (_, columnIndex) => {
    let widest = 0;
    for (let rowIndex = 0; rowIndex < sheet.rows.length; rowIndex += 1) {
      context.font =
        rowIndex === 0
          ? `600 12.5px ${FONT_STACK}`
          : `400 12px ${FONT_STACK}`;
      widest = Math.max(
        widest,
        context.measureText(sheet.rows[rowIndex][columnIndex] ?? "").width,
      );
    }
    return Math.min(168, Math.max(64, widest + 20));
  });
  const total = natural.reduce((sum, width) => sum + width, 0);
  return natural.map((width) => (width / total) * available);
}

function drawText(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
): void {
  if (text.length === 0) {
    return;
  }
  const available = Math.max(0, maxWidth - 14);
  context.save();
  context.beginPath();
  context.rect(x, y - ROW_HEIGHT / 2, maxWidth, ROW_HEIGHT);
  context.clip();
  context.fillText(fitText(context, text, available), x + 7, y + 1);
  context.restore();
}

function drawHint(
  context: CanvasRenderingContext2D,
  text: string,
  right: number,
  y: number,
): number {
  context.font = `600 11px ${FONT_STACK}`;
  const width = Math.ceil(context.measureText(text).width) + 14;
  const left = right - width;
  context.fillStyle = HEADER_FILL;
  context.fillRect(left, y, width, 19);
  context.strokeStyle = HEADER_RULE;
  context.lineWidth = 1;
  context.strokeRect(left + 0.5, y + 0.5, width - 1, 18);
  context.fillStyle = HEADER_TEXT;
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(text, left + width / 2, y + 10);
  return left;
}

function drawSheet(context: CanvasRenderingContext2D, sheet: XlsxThumbSheet): void {
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, SHEET_WIDTH, SHEET_HEIGHT);

  context.fillStyle = HEADER_FILL;
  context.fillRect(0, 0, SHEET_WIDTH, HEADER_HEIGHT);
  context.fillStyle = HEADER_RULE;
  context.fillRect(0, HEADER_HEIGHT - 1, SHEET_WIDTH, 1);

  context.font = `600 13px ${FONT_STACK}`;
  context.fillStyle = HEADER_TEXT;
  context.textAlign = "left";
  context.textBaseline = "middle";
  context.fillText(
    fitText(context, sheet.sheetName.trim(), PADDING_X + 300),
    PADDING_X,
    HEADER_HEIGHT / 2 + 1,
  );

  const widths = columnWidths(context, sheet);
  if (widths.length === 0) {
    return;
  }
  const gridTop = HEADER_HEIGHT;
  const gridBottom = gridTop + sheet.rows.length * ROW_HEIGHT;
  const gridRight = PADDING_X + widths.reduce((sum, width) => sum + width, 0);

  context.fillStyle = HEADER_ROW_FILL;
  context.fillRect(PADDING_X, gridTop, gridRight - PADDING_X, ROW_HEIGHT);

  let x = PADDING_X;
  context.strokeStyle = GRID_LINE;
  context.lineWidth = 1;
  for (const width of widths) {
    context.beginPath();
    context.moveTo(Math.round(x) + 0.5, gridTop);
    context.lineTo(Math.round(x) + 0.5, gridBottom);
    context.stroke();
    x += width;
  }
  context.beginPath();
  context.moveTo(Math.round(gridRight) + 0.5, gridTop);
  context.lineTo(Math.round(gridRight) + 0.5, gridBottom);
  context.stroke();

  for (let rowIndex = 0; rowIndex <= sheet.rows.length; rowIndex += 1) {
    const y = gridTop + rowIndex * ROW_HEIGHT;
    context.beginPath();
    context.moveTo(PADDING_X, Math.round(y) + 0.5);
    context.lineTo(gridRight, Math.round(y) + 0.5);
    context.stroke();
  }

  for (let rowIndex = 0; rowIndex < sheet.rows.length; rowIndex += 1) {
    const row = sheet.rows[rowIndex];
    const baseline = gridTop + rowIndex * ROW_HEIGHT + ROW_HEIGHT / 2;
    context.font =
      rowIndex === 0
        ? `600 12.5px ${FONT_STACK}`
        : `400 12px ${FONT_STACK}`;
    context.fillStyle = rowIndex === 0 ? INK : BODY_INK;
    context.textAlign = "left";
    context.textBaseline = "middle";

    let cellX = PADDING_X;
    for (let columnIndex = 0; columnIndex < widths.length; columnIndex += 1) {
      const width = widths[columnIndex];
      drawText(
        context,
        row[columnIndex] ?? "",
        cellX,
        baseline,
        Math.max(0, width - 2),
      );
      cellX += width;
    }
  }

  const hiddenRows = Math.max(0, sheet.totalRows - sheet.rows.length);
  const hiddenColumns = Math.max(
    0,
    sheet.totalColumns - (sheet.rows[0]?.length ?? 0),
  );
  if (hiddenRows > 0) {
    const fade = context.createLinearGradient(0, SHEET_HEIGHT - 76, 0, SHEET_HEIGHT);
    fade.addColorStop(0, "rgba(255, 255, 255, 0)");
    fade.addColorStop(1, "rgba(255, 255, 255, 0.98)");
    context.fillStyle = fade;
    context.fillRect(0, SHEET_HEIGHT - 76, SHEET_WIDTH, 76);
  }

  let hintRight = SHEET_WIDTH - PADDING_X;
  if (hiddenRows > 0) {
    hintRight = drawHint(context, `↓ +${hiddenRows}`, hintRight, SHEET_HEIGHT - 29) - 8;
  }
  if (hiddenColumns > 0) {
    drawHint(context, `→ +${hiddenColumns}`, hintRight, SHEET_HEIGHT - 29);
  }
}

function drawThumbnail(sheet: XlsxThumbSheet): string {
  const canvas = document.createElement("canvas");
  const ratio =
    typeof window === "undefined"
      ? 1
      : Math.min(2, Math.max(1, window.devicePixelRatio || 1));
  canvas.width = Math.round(SHEET_WIDTH * ratio);
  canvas.height = Math.round(SHEET_HEIGHT * ratio);
  const context = canvas.getContext("2d");
  if (context === null) {
    throw new Error("Canvas 2D is unavailable");
  }
  context.scale(ratio, ratio);
  drawSheet(context, sheet);

  const dataUrl = canvas.toDataURL("image/webp", SHEET_QUALITY);
  return dataUrl.length > MAX_DATA_URL_LENGTH
    ? canvas.toDataURL("image/webp", 0.62)
    : dataUrl;
}

/**
 * Render the first readable sheet of a workbook into a small WebP data URL.
 *
 * Fetching and parsing happen off the drawing path: the bytes are transferred
 * to a module worker, which returns only the bounded excerpt. The worker is
 * always terminated and the timeout is always cleared, including on abort.
 */
export async function renderXlsxThumb(
  fileId: number,
  signal: AbortSignal,
): Promise<string> {
  signal.throwIfAborted();

  const buffer = await fetchViewerBinary(fileContentUrl(fileId), signal);
  signal.throwIfAborted();

  const sheet = await parseWorkbookInWorker(buffer, signal);
  signal.throwIfAborted();

  return drawThumbnail(sheet);
}
