import { utils, type WorkBook, type WorkSheet } from "xlsx";

/** Rows drawn in a spreadsheet thumbnail before the grid is cropped. */
export const XLSX_THUMB_MAX_ROWS = 8;

/** Columns drawn in a spreadsheet thumbnail before the grid is cropped. */
export const XLSX_THUMB_MAX_COLUMNS = 5;

/** Characters kept from one cell before the canvas clips it to its column. */
export const XLSX_THUMB_MAX_CELL_CHARS = 48;

// A thumbnail never needs the whole sheet. Scanning a bounded window keeps a
// pathological workbook from materializing hundreds of thousands of strings
// just to draw eight rows; totals still come from the sheet's real range.
const SCAN_ROWS = 128;
const SCAN_COLUMNS = 32;

/** One bounded sheet excerpt, ready for the canvas renderer. */
export interface XlsxThumbSheet {
  readonly sheetName: string;
  readonly rows: readonly (readonly string[])[];
  readonly totalRows: number;
  readonly totalColumns: number;
}

/** Result posted from the parsing worker to the main thread. */
export type XlsxThumbWorkerMessage =
  | { readonly type: "ok"; readonly sheet: XlsxThumbSheet }
  | { readonly type: "error"; readonly message: string };

function cellText(value: unknown): string {
  if (typeof value === "string") {
    // A cell can contain line breaks. A one-line thumbnail treats them as
    // spaces instead of drawing the first fragment only.
    return value.replace(/\r?\n/g, " ");
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? "" : value.toISOString();
  }
  return "";
}

function clipCell(text: string): string {
  const flat = text.trim();
  if (flat.length <= XLSX_THUMB_MAX_CELL_CHARS) {
    return flat;
  }
  return `${flat.slice(0, XLSX_THUMB_MAX_CELL_CHARS - 1)}…`;
}

function isEmptyRow(row: readonly string[]): boolean {
  return row.every((cell) => cell.trim().length === 0);
}

function trimEmptyRows(rows: readonly (readonly string[])[]): {
  readonly rows: readonly (readonly string[])[];
  readonly start: number;
} {
  let start = 0;
  let end = rows.length;
  while (start < end && isEmptyRow(rows[start])) {
    start += 1;
  }
  while (end > start && isEmptyRow(rows[end - 1])) {
    end -= 1;
  }
  return { rows: rows.slice(start, end), start };
}

function trimEmptyColumns(rows: readonly (readonly string[])[]): {
  readonly rows: readonly string[][];
  readonly start: number;
  readonly width: number;
} {
  let width = 0;
  for (const row of rows) {
    width = Math.max(width, row.length);
  }

  let start = 0;
  let end = width;
  while (start < end && rows.every((row) => (row[start] ?? "").trim() === "")) {
    start += 1;
  }
  while (end > start && rows.every((row) => (row[end - 1] ?? "").trim() === "")) {
    end -= 1;
  }

  return {
    rows: rows.map((row) => row.slice(start, end)),
    start,
    width: end - start,
  };
}

/**
 * Build the bounded excerpt for one sheet.
 *
 * SheetJS formats values through the stored number format (`raw: false`), so
 * dates and currencies read like the workbook. Fully empty rows and columns at
 * the edges are dropped, while interior blanks stay as blank cells so the
 * excerpt keeps the sheet's shape. The returned totals describe the trimmed
 * range and let the canvas report how much was cropped.
 */
export function buildSheetThumb(
  sheetName: string,
  sheet: WorkSheet,
): XlsxThumbSheet {
  const reference = sheet["!ref"];
  if (!reference) {
    return { sheetName, rows: [], totalRows: 0, totalColumns: 0 };
  }

  const decoded = utils.decode_range(reference);
  const scanEnd = {
    r: Math.min(decoded.e.r, decoded.s.r + SCAN_ROWS - 1),
    c: Math.min(decoded.e.c, decoded.s.c + SCAN_COLUMNS - 1),
  };
  const raw = utils.sheet_to_json<unknown[]>(sheet, {
    header: 1,
    raw: false,
    defval: "",
    // Interior blank rows are part of the sheet's shape; only the empty edges
    // are removed after conversion.
    blankrows: true,
    range: { s: decoded.s, e: scanEnd },
  });
  const normalized = raw.map((row) => row.map((value) => clipCell(cellText(value))));
  const trimmedRows = trimEmptyRows(normalized);
  if (trimmedRows.rows.length === 0) {
    return { sheetName, rows: [], totalRows: 0, totalColumns: 0 };
  }
  const trimmedColumns = trimEmptyColumns(trimmedRows.rows);

  // When the scan covered the whole sheet, the trimmed span is the true
  // extent. When the scan stopped early, the remainder is still part of the
  // sheet and only the leading empty edge is known.
  const scanReachedEnd = scanEnd.r >= decoded.e.r;
  const scanReachedLastColumn = scanEnd.c >= decoded.e.c;
  const totalRows = scanReachedEnd
    ? trimmedRows.rows.length
    : decoded.e.r - (decoded.s.r + trimmedRows.start) + 1;
  const totalColumns = scanReachedLastColumn
    ? trimmedColumns.width
    : decoded.e.c - (decoded.s.c + trimmedColumns.start) + 1;
  const shownRows = Math.min(trimmedColumns.rows.length, XLSX_THUMB_MAX_ROWS);
  const shownColumns = Math.min(trimmedColumns.width, XLSX_THUMB_MAX_COLUMNS);

  const rows: string[][] = [];
  for (let rowIndex = 0; rowIndex < shownRows; rowIndex += 1) {
    const row = trimmedColumns.rows[rowIndex] ?? [];
    rows.push(
      Array.from({ length: shownColumns }, (_, columnIndex) => row[columnIndex] ?? ""),
    );
  }

  return { sheetName, rows, totalRows, totalColumns };
}

/**
 * Pick the first sheet with any readable cell and build its excerpt.
 *
 * An empty leading sheet is skipped: a thumbnail should show content, not an
 * empty tab that happens to be first in the file.
 */
export function buildXlsxThumbSheet(workbook: WorkBook): XlsxThumbSheet {
  for (const sheetName of workbook.SheetNames) {
    const sheet = workbook.Sheets[sheetName];
    if (!sheet) {
      continue;
    }
    const built = buildSheetThumb(sheetName, sheet);
    if (built.rows.length > 0) {
      return built;
    }
  }
  throw new Error("The workbook has no readable cells");
}
