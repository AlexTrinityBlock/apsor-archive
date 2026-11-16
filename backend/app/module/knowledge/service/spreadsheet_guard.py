"""Pre-parse guards for untrusted spreadsheet archives.

These checks run before calamine so a small ODS or XLSX file cannot make the
parser expand repeated rows, repeated columns, or a forged sheet dimension into
gigabytes of in-process memory. The checks are deliberately conservative: a
workbook above the declared grid budget is rejected with the same stable
``spreadsheet_archive_too_large`` error as an archive bomb.
"""

import re
import zipfile
from io import BytesIO

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.module.knowledge.domain.spreadsheet_domain import (
    SPREADSHEET_MAX_ARCHIVE_BYTES,
    SPREADSHEET_MAX_ARCHIVE_ENTRIES,
    SPREADSHEET_MAX_ARCHIVE_ENTRY_BYTES,
    SPREADSHEET_MAX_DECLARED_CELLS,
    SPREADSHEET_MAX_DECLARED_COLUMNS,
    SPREADSHEET_MAX_DECLARED_ROWS,
)
from app.module.knowledge.exception.domain_error import (
    EmptyContentError,
    SpreadsheetArchiveTooLargeError,
)

_ODS_TABLE_NAMESPACE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
_XLSX_MAIN_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_ODS_ROW = f"{{{_ODS_TABLE_NAMESPACE}}}table-row"
_ODS_CELLS = {
    f"{{{_ODS_TABLE_NAMESPACE}}}table-cell",
    f"{{{_ODS_TABLE_NAMESPACE}}}covered-table-cell",
}
_ODS_ROW_REPEAT = f"{{{_ODS_TABLE_NAMESPACE}}}number-rows-repeated"
_ODS_COLUMN_REPEAT = f"{{{_ODS_TABLE_NAMESPACE}}}number-columns-repeated"
_XLSX_DIMENSION = f"{{{_XLSX_MAIN_NAMESPACE}}}dimension"
_XLSX_ROW = f"{{{_XLSX_MAIN_NAMESPACE}}}row"
_XLSX_CELL = f"{{{_XLSX_MAIN_NAMESPACE}}}c"
_COORDINATE = re.compile(r"([A-Za-z]+)([0-9]+)")


def _raise_too_large(detail: str) -> None:
    raise SpreadsheetArchiveTooLargeError(detail)


def _positive_repeat(value: str | None) -> int:
    if value is None:
        return 1
    try:
        parsed = int(value)
    except ValueError:
        return 1
    return max(1, parsed)


def _column_number(letters: str) -> int:
    number = 0
    for character in letters.upper():
        number = number * 26 + (ord(character) - ord("A") + 1)
    return number


def _dimension_bounds(reference: str | None) -> tuple[int, int] | None:
    if not reference:
        return None
    cleaned = reference.replace("$", "").strip()
    start, _, end = cleaned.partition(":")
    end = end or start
    start_match = _COORDINATE.fullmatch(start)
    end_match = _COORDINATE.fullmatch(end)
    if start_match is None or end_match is None:
        return None
    return int(end_match.group(2)), _column_number(end_match.group(1))


def _validate_zip(data: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise EmptyContentError() from exc
    entries = archive.infolist()
    if len(entries) > SPREADSHEET_MAX_ARCHIVE_ENTRIES:
        archive.close()
        _raise_too_large(
            f"Workbook archive has {len(entries)} entries; "
            f"the limit is {SPREADSHEET_MAX_ARCHIVE_ENTRIES}."
        )
    expanded_bytes = 0
    for entry in entries:
        if entry.file_size > SPREADSHEET_MAX_ARCHIVE_ENTRY_BYTES:
            archive.close()
            _raise_too_large(
                f"Workbook entry {entry.filename!r} expands to "
                f"{entry.file_size} bytes; the per-entry limit is "
                f"{SPREADSHEET_MAX_ARCHIVE_ENTRY_BYTES}."
            )
        expanded_bytes += entry.file_size
    if expanded_bytes > SPREADSHEET_MAX_ARCHIVE_BYTES:
        archive.close()
        _raise_too_large(
            f"Workbook archive expands to {expanded_bytes} bytes; "
            f"the limit is {SPREADSHEET_MAX_ARCHIVE_BYTES}."
        )
    return archive


def _check_rows_and_cells(rows: int, cells: int) -> None:
    if rows > SPREADSHEET_MAX_DECLARED_ROWS:
        _raise_too_large(
            f"Workbook declares {rows} rows; the pre-parse limit is "
            f"{SPREADSHEET_MAX_DECLARED_ROWS}."
        )
    if cells > SPREADSHEET_MAX_DECLARED_CELLS:
        _raise_too_large(
            f"Workbook declares {cells} cells; the pre-parse limit is "
            f"{SPREADSHEET_MAX_DECLARED_CELLS}."
        )


def _validate_ods_grid(archive: zipfile.ZipFile) -> None:
    try:
        handle = archive.open("content.xml")
    except KeyError:
        return
    rows = 0
    cells = 0
    row_cells = 0
    row_repeat = 1
    try:
        with handle:
            for event, element in ElementTree.iterparse(handle, events=("start", "end")):
                tag = element.tag
                if event == "start" and tag == _ODS_ROW:
                    row_cells = 0
                    row_repeat = _positive_repeat(element.get(_ODS_ROW_REPEAT))
                    if row_repeat > SPREADSHEET_MAX_DECLARED_ROWS:
                        _raise_too_large(
                            f"Workbook declares a repeated row count of {row_repeat}; "
                            f"the pre-parse limit is {SPREADSHEET_MAX_DECLARED_ROWS}."
                        )
                elif event == "start" and tag in _ODS_CELLS:
                    row_cells += _positive_repeat(element.get(_ODS_COLUMN_REPEAT))
                    if row_cells > SPREADSHEET_MAX_DECLARED_COLUMNS:
                        _raise_too_large(
                            f"Workbook declares {row_cells} columns in one row; "
                            f"the pre-parse limit is {SPREADSHEET_MAX_DECLARED_COLUMNS}."
                        )
                elif event == "end" and tag == _ODS_ROW:
                    rows += row_repeat
                    cells += row_repeat * max(1, row_cells)
                    _check_rows_and_cells(rows, cells)
                    element.clear()
    except (DefusedXmlException, ElementTree.ParseError, OSError, ValueError):
        # Let calamine report malformed ODS content; this guard only needs to
        # stop declared expansion, not replace the parser's error handling.
        return


def _validate_xlsx_grid(archive: zipfile.ZipFile) -> None:
    rows = 0
    cells = 0
    for name in archive.namelist():
        if not (name.startswith("xl/worksheets/") and name.endswith(".xml")):
            continue
        try:
            with archive.open(name) as handle:
                for event, element in ElementTree.iterparse(handle, events=("start",)):
                    if event != "start":
                        continue
                    if element.tag == _XLSX_DIMENSION:
                        bounds = _dimension_bounds(element.get("ref"))
                        if bounds is not None:
                            max_row, max_column = bounds
                            if max_row > SPREADSHEET_MAX_DECLARED_ROWS:
                                _raise_too_large(
                                    f"Workbook declares {max_row} rows in {name}; "
                                    f"the pre-parse limit is "
                                    f"{SPREADSHEET_MAX_DECLARED_ROWS}."
                                )
                            if max_column > SPREADSHEET_MAX_DECLARED_COLUMNS:
                                _raise_too_large(
                                    f"Workbook declares {max_column} columns in {name}; "
                                    f"the pre-parse limit is "
                                    f"{SPREADSHEET_MAX_DECLARED_COLUMNS}."
                                )
                    elif element.tag == _XLSX_ROW:
                        rows += 1
                        _check_rows_and_cells(rows, cells)
                    elif element.tag == _XLSX_CELL:
                        cells += 1
                        _check_rows_and_cells(rows, cells)
                    element.clear()
        except (DefusedXmlException, ElementTree.ParseError, OSError, ValueError):
            return


def validate_spreadsheet_archive(data: bytes, suffix: str) -> None:
    """Reject zip bombs and declared grids that would exhaust calamine memory."""
    if suffix not in {".xlsx", ".xlsm", ".ods"}:
        return
    archive = _validate_zip(data)
    try:
        if suffix == ".ods":
            _validate_ods_grid(archive)
        else:
            _validate_xlsx_grid(archive)
    finally:
        archive.close()


__all__ = ["validate_spreadsheet_archive"]
