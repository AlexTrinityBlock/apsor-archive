import { useMemo, type ReactNode } from "react";

import { utils, type WorkSheet } from "xlsx";

import { useI18n } from "../../i18n";

/** Rows rendered from one sheet before the preview is capped. */
export const XLSX_MAX_PREVIEW_ROWS = 500;

/** Columns rendered from one sheet before the preview is capped. */
export const XLSX_MAX_PREVIEW_COLUMNS = 50;

/** Characters rendered inside one cell before the display value is clipped. */
const XLSX_MAX_CELL_CHARS = 500;

interface XlsxGridProps {
  readonly sheet: WorkSheet;
  readonly panelId: string;
  readonly tabId: string;
}

interface SheetGrid {
  readonly rows: readonly (readonly string[])[];
  readonly startRow: number;
  readonly totalRows: number;
  readonly shownColumns: number;
  readonly totalColumns: number;
}

/** Midnight in the spreadsheet display format, with either hour spelling. */
const MIDNIGHT_TIMESTAMP = /^(\d{4}-\d{2}-\d{2}) (?:0?0):00:00$/;

/**
 * Date cells arrive as formatted text. A date with no meaningful time reads as
 * a day, not as midnight. This only changes the displayed string; the stored
 * value and the full cell text stay untouched.
 */
function shortenMidnight(text: string): string {
  const match = MIDNIGHT_TIMESTAMP.exec(text);
  return match ? match[1] : text;
}

/** Convert one formatted cell into display text without interpreting markup. */
function cellText(value: unknown): string {
  if (typeof value === "string") {
    return shortenMidnight(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? "" : value.toISOString();
  }
  return "";
}

function trimTrailingEmpty(cells: string[]): string[] {
  let end = cells.length;
  while (end > 0 && cells[end - 1] === "") {
    end -= 1;
  }
  return end === cells.length ? cells : cells.slice(0, end);
}

/**
 * Materialize one sheet as bounded text rows. SheetJS formats every value
 * through its stored number format, so dates and currencies read like the
 * workbook, not like raw serial numbers.
 */
function buildGrid(sheet: WorkSheet): SheetGrid {
  const reference = sheet["!ref"];
  if (!reference) {
    return {
      rows: [],
      startRow: 0,
      totalRows: 0,
      shownColumns: 0,
      totalColumns: 0,
    };
  }
  const decoded = utils.decode_range(reference);
  const previewEnd = {
    r: Math.min(decoded.e.r, decoded.s.r + XLSX_MAX_PREVIEW_ROWS - 1),
    c: Math.min(decoded.e.c, decoded.s.c + XLSX_MAX_PREVIEW_COLUMNS - 1),
  };
  const raw = utils.sheet_to_json<unknown[]>(sheet, {
    header: 1,
    raw: false,
    defval: "",
    // Keep interior blank rows so the displayed row numbers stay aligned with
    // the workbook; only trailing empties are trimmed.
    blankrows: true,
    range: { s: decoded.s, e: previewEnd },
  });
  const normalized = raw.map((row) => trimTrailingEmpty(row.map(cellText)));
  while (normalized.length > 0 && normalized[normalized.length - 1].length === 0) {
    normalized.pop();
  }
  const totalRows = decoded.e.r - decoded.s.r + 1;
  const totalColumns = decoded.e.c - decoded.s.c + 1;
  return {
    rows: normalized
      .slice(0, XLSX_MAX_PREVIEW_ROWS)
      .map((row) => row.slice(0, XLSX_MAX_PREVIEW_COLUMNS)),
    startRow: decoded.s.r,
    totalRows,
    shownColumns: Math.min(totalColumns, XLSX_MAX_PREVIEW_COLUMNS),
    totalColumns,
  };
}

/**
 * One cell rendered as React text. Values longer than the display cap are
 * shortened for layout only; the full value stays in the cell title and is
 * never interpreted as HTML.
 */
function CellValue({ value }: { readonly value: string }): ReactNode {
  if (value.length <= XLSX_MAX_CELL_CHARS) {
    return value;
  }
  return (
    <>
      {value.slice(0, XLSX_MAX_CELL_CHARS)}
      <span aria-hidden="true">…</span>
    </>
  );
}

function cellTitle(value: string): string | undefined {
  return value.length > XLSX_MAX_CELL_CHARS ? value : undefined;
}

function columnIndexes(count: number): number[] {
  return Array.from({ length: count }, (_, index) => index);
}

/**
 * The bounded, read-only sheet grid: a sticky first row for the header and a
 * sticky first column for row numbers. The tab panel is the scroll container,
 * so keyboard users can pan the grid after the tab strip hands off focus.
 */
export function XlsxGrid({ sheet, panelId, tabId }: XlsxGridProps) {
  const { t, formatNumber } = useI18n();
  const grid = useMemo(() => buildGrid(sheet), [sheet]);
  const header = grid.rows[0] ?? [];
  const body = grid.rows.slice(1);
  const columns = columnIndexes(grid.shownColumns);

  if (grid.rows.length === 0) {
    return (
      <div
        className="viewer-xlsx__empty"
        role="tabpanel"
        id={panelId}
        aria-labelledby={tabId}
        tabIndex={0}
      >
        <p className="viewer-empty">{t("library.viewer.xlsx.empty")}</p>
      </div>
    );
  }

  const shownRows = grid.rows.length;
  const rowsNote =
    grid.totalRows > XLSX_MAX_PREVIEW_ROWS
      ? t("library.viewer.xlsx.truncated", {
          shown: formatNumber(shownRows),
          total: formatNumber(grid.totalRows),
        })
      : t("library.viewer.xlsx.rows", {
          shown: formatNumber(shownRows),
          total: formatNumber(shownRows),
        });
  const columnsNote =
    grid.totalColumns > XLSX_MAX_PREVIEW_COLUMNS
      ? t("library.viewer.xlsx.truncatedColumns", {
          shown: formatNumber(grid.shownColumns),
          total: formatNumber(grid.totalColumns),
        })
      : t("library.viewer.xlsx.columns", {
          count: formatNumber(grid.shownColumns),
        });

  return (
    <div className="viewer-xlsx__grid">
      <div
        className="viewer-xlsx__scroll"
        role="tabpanel"
        id={panelId}
        aria-labelledby={tabId}
        tabIndex={0}
      >
        <table className="viewer-xlsx__table">
          <thead>
            <tr>
              <th scope="col" className="viewer-xlsx__index">
                #
              </th>
              {columns.map((columnIndex) => {
                const label = header[columnIndex] ?? "";
                return (
                  <th
                    scope="col"
                    key={`head-${columnIndex}`}
                    title={cellTitle(label)}
                  >
                    {label.trim().length > 0 ? (
                      <CellValue value={label} />
                    ) : (
                      t("library.viewer.xlsx.column", {
                        index: columnIndex + 1,
                      })
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {body.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                <th scope="row" className="viewer-xlsx__index">
                  {grid.startRow + rowIndex + 2}
                </th>
                {columns.map((columnIndex) => {
                  const value = row[columnIndex] ?? "";
                  return (
                    <td key={`cell-${rowIndex}-${columnIndex}`} title={cellTitle(value)}>
                      <CellValue value={value} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="viewer-xlsx__note">
        {rowsNote} {columnsNote} {t("library.viewer.xlsx.note")}
      </p>
    </div>
  );
}
