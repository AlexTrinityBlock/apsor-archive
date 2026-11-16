"""Workbook extraction into searchable Markdown tables.

calamine owns the cell values for every supported format. openpyxl is a narrow
fallback that recovers formula text for OOXML workbooks whose cached values are
missing; it is never used for legacy ``.xls`` or OpenDocument files. The pure
formatting and limit rules live in the spreadsheet domain module.
"""

import logging
import zipfile
from collections.abc import Mapping
from io import BytesIO
from itertools import islice

from openpyxl import load_workbook
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.worksheet.worksheet import Worksheet
from python_calamine import (
    CalamineError,
    CalamineSheet,
    CalamineWorkbook,
    SheetMetadata,
    SheetTypeEnum,
    SheetVisibleEnum,
)

from app.module.knowledge.domain.spreadsheet_domain import (
    SPREADSHEET_FORMULA_FALLBACK_EXTENSIONS,
    SPREADSHEET_MAX_COLUMNS,
    SPREADSHEET_MAX_ROWS,
    SPREADSHEET_MAX_TEXT_CHARS,
    SpreadsheetSheet,
    format_spreadsheet_cell,
    render_spreadsheet,
)
from app.module.knowledge.exception.domain_error import EmptyContentError
from app.module.knowledge.service.spreadsheet_guard import (
    validate_spreadsheet_archive,
)

logger = logging.getLogger(__name__)

_FORMULA_SCAN_CHUNK_BYTES = 1024 * 1024
_FormulaMap = dict[tuple[int, int], str]


def _sheet_start(sheet: CalamineSheet) -> tuple[int, int]:
    start = sheet.start
    return start if start is not None else (0, 0)


def _collect_rows(
    sheet: CalamineSheet,
    *,
    start_row: int,
    start_column: int,
    effective_start_column: int,
    column_limit: int,
) -> list[list[str]]:
    """Collect at most the row cap, cropping and padding to the column cap.

    Calamine crops columns to the used-range start. A formula left of that
    start is still recoverable, so rows are left-padded before the formula
    overlay runs.
    """
    if column_limit <= 0:
        return []
    left_padding = max(0, start_column - effective_start_column)
    available_columns = max(0, column_limit - left_padding)
    rows: list[list[str]] = []
    row_iterator = islice(
        sheet.iter_rows(),
        start_row,
        start_row + SPREADSHEET_MAX_ROWS,
    )
    for raw_row in row_iterator:
        values = [""] * left_padding
        values.extend(
            format_spreadsheet_cell(value) for value in raw_row[:available_columns]
        )
        values = values[:column_limit]
        values.extend([""] * (column_limit - len(values)))
        rows.append(values)
    return rows


def _overlay_formulas(
    rows: list[list[str]],
    formulas: Mapping[tuple[int, int], str],
    *,
    start_row: int,
    start_column: int,
    column_limit: int,
) -> None:
    """Fill cells that calamine rendered empty with their recovered formula.

    A formula-only workbook has no cached values, so calamine reports an empty
    used range. Empty grid rows are added as needed, then trimmed like any other
    row, which keeps the formula text searchable without materializing the sheet.
    Calamine crops columns to the used-range start, so both the row and column
    keys must be translated into local offsets before indexing.
    """
    for (row_index, column_index), formula in formulas.items():
        local_row = row_index - start_row
        local_column = column_index - start_column
        if not 0 <= local_row < SPREADSHEET_MAX_ROWS:
            continue
        if not 0 <= local_column < column_limit:
            continue
        while len(rows) <= local_row:
            rows.append([""] * column_limit)
        row = rows[local_row]
        if local_column < len(row) and not row[local_column]:
            row[local_column] = formula


def _expand_merged_cells(
    rows: list[list[str]],
    merged_ranges: list[tuple[tuple[int, int], tuple[int, int]]] | None,
    *,
    start_row: int,
    start_column: int,
) -> None:
    """Repeat the top-left value across every collected cell of a merged range."""
    if not merged_ranges or not rows:
        return
    for (top_row, left_column), (bottom_row, right_column) in merged_ranges:
        source_row = top_row - start_row
        source_column = left_column - start_column
        if not 0 <= source_row < len(rows):
            continue
        source_cells = rows[source_row]
        if not 0 <= source_column < len(source_cells):
            continue
        value = source_cells[source_column]
        if not value:
            continue
        first_row = max(source_row, 0)
        last_row = min(bottom_row - start_row, len(rows) - 1)
        first_column = max(source_column, 0)
        last_column = min(right_column - start_column, SPREADSHEET_MAX_COLUMNS - 1)
        for row_index in range(first_row, last_row + 1):
            target = rows[row_index]
            if last_column >= len(target):
                target.extend([""] * (last_column + 1 - len(target)))
            for column_index in range(first_column, last_column + 1):
                if not target[column_index]:
                    target[column_index] = value


def _trim_empty_edges(rows: list[list[str]]) -> list[list[str]]:
    """Drop leading/trailing empty rows and trailing empty columns."""
    first_content = next((index for index, row in enumerate(rows) if any(row)), None)
    if first_content is None:
        return []
    retained = rows[first_content:]
    while retained and not any(retained[-1]):
        retained.pop()
    width = 0
    for row in retained:
        for index in range(len(row) - 1, -1, -1):
            if row[index]:
                width = max(width, index + 1)
                break
    return [row[:width] for row in retained]


def _extract_sheet(
    metadata: SheetMetadata,
    sheet: CalamineSheet,
    formulas: Mapping[tuple[int, int], str],
) -> SpreadsheetSheet:
    start_row, start_column = _sheet_start(sheet)
    formula_rows = [row for row, _ in formulas]
    formula_columns = [column for _, column in formulas]
    effective_start_row = min([start_row, *formula_rows])
    effective_start_column = min([start_column, *formula_columns])
    left_padding = max(0, start_column - effective_start_column)
    formula_column_width = max(
        (column - effective_start_column + 1 for _, column in formulas),
        default=0,
    )
    formula_row_height = max(
        (row - effective_start_row + 1 for row, _ in formulas),
        default=0,
    )
    column_limit = min(
        max(sheet.width + left_padding, formula_column_width),
        SPREADSHEET_MAX_COLUMNS,
    )
    rows = _collect_rows(
        sheet,
        start_row=effective_start_row,
        start_column=start_column,
        effective_start_column=effective_start_column,
        column_limit=column_limit,
    )
    _overlay_formulas(
        rows,
        formulas,
        start_row=effective_start_row,
        start_column=effective_start_column,
        column_limit=column_limit,
    )
    _expand_merged_cells(
        rows,
        sheet.merged_cell_ranges,
        start_row=effective_start_row,
        start_column=effective_start_column,
    )
    trimmed = _trim_empty_edges(rows)
    return SpreadsheetSheet(
        name=metadata.name,
        hidden=metadata.visible is not SheetVisibleEnum.Visible,
        rows=tuple(tuple(row) for row in trimmed),
        truncated_rows=(
            sheet.height + (start_row - effective_start_row) > SPREADSHEET_MAX_ROWS
            or formula_row_height > SPREADSHEET_MAX_ROWS
        ),
        truncated_columns=(
            sheet.width + left_padding > SPREADSHEET_MAX_COLUMNS
            or formula_column_width > SPREADSHEET_MAX_COLUMNS
        ),
    )


def _formula_text(value: object) -> str | None:
    """Return the sanitized formula text of one openpyxl cell, if any."""
    if isinstance(value, ArrayFormula):
        return format_spreadsheet_cell("", "=" + value.text)
    if isinstance(value, str) and value.startswith("="):
        return format_spreadsheet_cell("", value)
    return None


def _worksheet_formulas(
    worksheet: Worksheet,
    window: tuple[int, int],
) -> _FormulaMap:
    """Read a bounded absolute cell window and keep only formula cells.

    The scan starts at row 1 / column 1 because calamine's used-range start can
    sit below or to the right of formula-only cells. Reading only the used-range
    window would silently drop exactly the formulas the fallback exists for.
    """
    start_row, start_column = window
    max_row = start_row + SPREADSHEET_MAX_ROWS
    max_column = start_column + SPREADSHEET_MAX_COLUMNS
    if worksheet.max_row is not None:
        max_row = min(max_row, max(worksheet.max_row, 1))
    if worksheet.max_column is not None:
        max_column = min(max_column, max(worksheet.max_column, 1))
    formulas: _FormulaMap = {}
    for row in worksheet.iter_rows(
        min_row=1,
        max_row=max_row,
        min_col=1,
        max_col=max_column,
    ):
        for cell in row:
            formula = _formula_text(cell.value)
            if formula is not None:
                formulas[(cell.row - 1, cell.column - 1)] = formula
    return formulas


def _archive_contains_formula_cells(data: bytes) -> bool:
    """Stream the OOXML sheet parts and look for a formula element."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            for name in archive.namelist():
                if not (name.startswith("xl/worksheets/") and name.endswith(".xml")):
                    continue
                with archive.open(name) as worksheet_file:
                    previous_tail = b""
                    while chunk := worksheet_file.read(_FORMULA_SCAN_CHUNK_BYTES):
                        if b"<f" in previous_tail + chunk:
                            return True
                        previous_tail = chunk[-1:]
    except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
        return False
    return False


def _load_formula_map(
    data: bytes,
    windows: Mapping[str, tuple[int, int]],
) -> dict[str, _FormulaMap]:
    """Recover OOXML formulas per worksheet, keyed by worksheet title.

    The map is nested by sheet name because two sheets can hold a formula at the
    same absolute coordinate. Any openpyxl failure is ignored: calamine values
    remain authoritative.
    """
    if not _archive_contains_formula_cells(data):
        return {}
    formulas: dict[str, _FormulaMap] = {}
    workbook = None
    try:
        workbook = load_workbook(
            BytesIO(data),
            read_only=True,
            data_only=False,
            keep_links=False,
        )
        for worksheet in workbook.worksheets:
            window = windows.get(worksheet.title)
            if window is None:
                continue
            formulas[worksheet.title] = _worksheet_formulas(worksheet, window)
    except Exception as exc:
        logger.debug(
            "Spreadsheet formula fallback failed and was ignored: %s",
            exc.__class__.__name__,
        )
    finally:
        if workbook is not None:
            workbook.close()
    return formulas


def extract_spreadsheet_text(
    data: bytes,
    suffix: str,
    max_chars: int = SPREADSHEET_MAX_TEXT_CHARS,
) -> str:
    """Extract one workbook into searchable Markdown tables.

    Runs in the ingestion worker's bounded CPU executor. Raises
    ``EmptyContentError`` for unreadable or empty workbooks and
    ``SpreadsheetArchiveTooLargeError`` for archive bombs or declared grids
    that would exhaust the parser's memory.
    """
    normalized_suffix = suffix.lower()
    validate_spreadsheet_archive(data, normalized_suffix)

    sheets: list[SpreadsheetSheet] = []
    stream = BytesIO(data)
    workbook: CalamineWorkbook | None = None
    try:
        try:
            workbook = CalamineWorkbook.from_filelike(stream)
        except (CalamineError, OSError, ValueError) as exc:
            raise EmptyContentError() from exc

        selected: list[tuple[SheetMetadata, CalamineSheet]] = []
        for metadata in workbook.sheets_metadata:
            if metadata.typ is not SheetTypeEnum.WorkSheet:
                continue
            selected.append((metadata, workbook.get_sheet_by_name(metadata.name)))
        windows = {
            metadata.name: _sheet_start(sheet) for metadata, sheet in selected
        }
        formulas = (
            _load_formula_map(data, windows)
            if normalized_suffix in SPREADSHEET_FORMULA_FALLBACK_EXTENSIONS
            else {}
        )
        for metadata, sheet in selected:
            sheets.append(
                _extract_sheet(
                    metadata,
                    sheet,
                    formulas.get(metadata.name, {}),
                )
            )
    except CalamineError as exc:
        raise EmptyContentError() from exc
    finally:
        if workbook is not None:
            workbook.close()

    if not any(sheet.rows for sheet in sheets):
        raise EmptyContentError()
    return render_spreadsheet(sheets, max_chars=max_chars)


__all__ = ["extract_spreadsheet_text"]
