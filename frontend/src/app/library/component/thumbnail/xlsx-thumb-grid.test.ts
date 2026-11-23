// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { expect, test } from "bun:test";
import { utils, type WorkBook, type WorkSheet } from "xlsx";

import {
  buildXlsxThumbSheet,
  XLSX_THUMB_MAX_CELL_CHARS,
  XLSX_THUMB_MAX_COLUMNS,
  XLSX_THUMB_MAX_ROWS,
} from "./xlsx-thumb-grid";

function workbookWith(sheetName: string, sheet: WorkSheet): WorkBook {
  const workbook = utils.book_new();
  utils.book_append_sheet(workbook, sheet, sheetName);
  return workbook;
}

function budgetBook(): WorkBook {
  const header = ["Project", "Owner", "Status", "Updated", "Notes", "Region"];
  const rows = Array.from({ length: 10 }, (_, index) => [
    `Project ${index + 1}`,
    `Owner ${index + 1}`,
    index % 2 === 0 ? "Active" : "Paused",
    `2026-03-${String(index + 1).padStart(2, "0")}`,
    `Note ${index + 1}`,
    index % 2 === 0 ? "North" : "South",
  ]);
  return workbookWith(
    "Projects",
    utils.aoa_to_sheet([header, ...rows]),
  );
}

test("a thumbnail keeps the first row and the 8x5 crop metadata", () => {
  const sheet = buildXlsxThumbSheet(budgetBook());

  expect(sheet.sheetName).toBe("Projects");
  expect(sheet.totalRows).toBe(11);
  expect(sheet.totalColumns).toBe(6);
  expect(sheet.rows).toHaveLength(XLSX_THUMB_MAX_ROWS);
  expect(sheet.rows[0]).toEqual(["Project", "Owner", "Status", "Updated", "Notes"]);
  expect(sheet.rows[0]).toHaveLength(XLSX_THUMB_MAX_COLUMNS);
  expect(sheet.rows[1][0]).toBe("Project 1");
  expect(sheet.rows[7][0]).toBe("Project 7");

  // The canvas turns these differences into the "+N" corner hints.
  expect(sheet.totalRows - sheet.rows.length).toBe(3);
  expect(sheet.totalColumns - sheet.rows[0].length).toBe(1);
});

test("long cells are clipped before reaching the canvas", () => {
  const long = "x".repeat(80);
  const workbook = workbookWith(
    "Notes",
    utils.aoa_to_sheet([["Header", long, "Short"]]),
  );

  const sheet = buildXlsxThumbSheet(workbook);
  expect(sheet.rows[0][1]).toHaveLength(XLSX_THUMB_MAX_CELL_CHARS);
  expect(sheet.rows[0][1]).toBe(`${"x".repeat(XLSX_THUMB_MAX_CELL_CHARS - 1)}…`);
  expect(sheet.rows[0][2]).toBe("Short");
});

test("empty rows and columns at the edges are skipped but interior blanks stay", () => {
  const workbook = workbookWith(
    "Blanks",
    utils.aoa_to_sheet([
      ["", "", "", ""],
      ["Header", "", "Value", ""],
      ["", "", "", ""],
      ["Data", "", "1", ""],
      ["", "", "", ""],
    ]),
  );

  const sheet = buildXlsxThumbSheet(workbook);
  expect(sheet.totalRows).toBe(3);
  expect(sheet.totalColumns).toBe(3);
  expect(sheet.rows).toHaveLength(3);
  expect(sheet.rows[0]).toEqual(["Header", "", "Value"]);
  expect(sheet.rows[1]).toEqual(["", "", ""]);
  expect(sheet.rows[2]).toEqual(["Data", "", "1"]);
});

test("the first sheet with readable cells wins", () => {
  const workbook = utils.book_new();
  utils.book_append_sheet(workbook, utils.aoa_to_sheet([[""]]), "Empty");
  utils.book_append_sheet(
    workbook,
    utils.aoa_to_sheet([["Second"], ["value"]]),
    "Second",
  );

  const sheet = buildXlsxThumbSheet(workbook);
  expect(sheet.sheetName).toBe("Second");
  expect(sheet.rows[0][0]).toBe("Second");
});

test("a workbook without readable cells is rejected instead of drawing a blank", () => {
  expect(() => buildXlsxThumbSheet(workbookWith("Empty", utils.aoa_to_sheet([[""]])))).toThrow(
    "no readable cells",
  );
});
