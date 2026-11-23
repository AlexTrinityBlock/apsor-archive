import type { ParsingOptions } from "xlsx";

/**
 * Parse options keep SheetJS to values only: no HTML strings, no styles, no
 * number-format metadata, no VBA, and no extra book parts. The dense cell
 * layout avoids one object per addressed cell on large sheets. `dateNF`
 * replaces the locale-dependent default date format with sortable ISO text;
 * midnight-only values are shortened again when the grid renders them.
 *
 * The full viewer and the library thumbnail worker share this object so the
 * two parsers cannot drift apart.
 */
export const XLSX_READ_OPTIONS: ParsingOptions = {
  type: "array",
  dense: true,
  cellDates: true,
  cellHTML: false,
  cellNF: false,
  cellStyles: false,
  bookVBA: false,
  bookProps: false,
  bookFiles: false,
  bookSheets: false,
  WTF: false,
  dateNF: "yyyy-mm-dd hh:mm:ss",
};
