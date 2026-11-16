"""Spreadsheet limits and Markdown rendering.

This module is pure: it formats already-extracted cell values and never imports
a workbook parser. Extraction belongs to the service layer so the domain rules
stay testable without calamine or openpyxl.
"""

import datetime
import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

SPREADSHEET_EXTENSIONS = frozenset({".xlsx", ".xls", ".xlsm", ".ods"})
SPREADSHEET_FORMULA_FALLBACK_EXTENSIONS = frozenset({".xlsx", ".xlsm"})
SPREADSHEET_MAX_ROWS = 10_000
SPREADSHEET_MAX_COLUMNS = 100
SPREADSHEET_MAX_TEXT_CHARS = 4_000_000
SPREADSHEET_MAX_CELL_CHARS = 4_000
SPREADSHEET_MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
SPREADSHEET_MAX_ARCHIVE_ENTRY_BYTES = 32 * 1024 * 1024
SPREADSHEET_MAX_ARCHIVE_ENTRIES = 10_000
# These caps run before calamine so a tiny ODS/XLSX cannot expand a repeated
# row or a forged dimension into gigabytes of in-process memory.
SPREADSHEET_MAX_DECLARED_ROWS = 200_000
SPREADSHEET_MAX_DECLARED_COLUMNS = 1_024
SPREADSHEET_MAX_DECLARED_CELLS = 2_000_000

_ELLIPSIS = "\u2026"


@dataclass(frozen=True)
class SpreadsheetSheet:
    """One worksheet after extraction, formatting, and edge trimming."""

    name: str
    hidden: bool
    rows: tuple[tuple[str, ...], ...]
    truncated_rows: bool = False
    truncated_columns: bool = False


def _render_value(value: object) -> str:
    """Render one raw calamine value without Markdown escaping."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime.datetime):
        if value.time() == datetime.time(0, 0):
            return value.date().isoformat()
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, datetime.timedelta):
        total_seconds = int(value.total_seconds())
        sign = "-" if total_seconds < 0 else ""
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3_600)
        minutes, seconds = divmod(remainder, 60)
        return f"{sign}{hours}:{minutes:02d}:{seconds:02d}"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return format(value, ".15g")
    return str(value)


def _sanitize_cell_text(text: str) -> str:
    """Make one rendered cell safe for a Markdown table row."""
    cleaned = text.replace("\x00", "")
    cleaned = cleaned.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    cleaned = cleaned.replace("|", "\\|").strip()
    if len(cleaned) <= SPREADSHEET_MAX_CELL_CHARS:
        return cleaned
    truncated = cleaned[:SPREADSHEET_MAX_CELL_CHARS].rstrip()
    if truncated.endswith("\\"):
        truncated = truncated[:-1]
    return truncated + _ELLIPSIS


def format_spreadsheet_cell(value: object, formula: str | None = None) -> str:
    """Render one cell value, falling back to its formula when it is empty.

    ``formula`` may already include the leading ``=``; it is only used when the
    extracted value is empty, because a cached value is always authoritative.
    """
    rendered = _render_value(value)
    if not rendered.strip() and formula:
        rendered = formula if formula.startswith("=") else f"={formula}"
    return _sanitize_cell_text(rendered)


def _pad_row(row: Sequence[str], width: int) -> list[str]:
    cells = list(row[:width])
    cells.extend([""] * (width - len(cells)))
    return cells


def _table_line(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _separator_line(width: int) -> str:
    return _table_line(["---"] * width)


def _trimmed_sheet_rows(sheet: SpreadsheetSheet) -> tuple[list[list[str]], int]:
    """Return padded rows without leading/trailing empties plus the table width."""
    rows = [list(row) for row in sheet.rows]
    first_content = next((index for index, row in enumerate(rows) if any(row)), None)
    if first_content is None:
        return [], 0
    rows = rows[first_content:]
    while rows and not any(rows[-1]):
        rows.pop()

    width = 0
    for row in rows:
        for index in range(len(row) - 1, -1, -1):
            if row[index]:
                width = max(width, index + 1)
                break
    if width == 0:
        return [], 0
    return [_pad_row(row, width) for row in rows], width


def _sheet_lines(sheet: SpreadsheetSheet) -> Iterator[str]:
    """Yield one sheet's Markdown lines so the caller can bound the workbook."""
    name = sheet.name.replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()
    heading = f"## Sheet: {name or 'Untitled'}"
    if sheet.hidden:
        heading += " (hidden)"
    yield heading
    yield ""

    rows, width = _trimmed_sheet_rows(sheet)
    if not rows:
        yield "_Empty sheet._"
        return
    yield _table_line(rows[0])
    yield _separator_line(width)
    for row in rows[1:]:
        yield _table_line(row)
    if sheet.truncated_rows:
        yield ""
        yield f"_Sheet truncated after {SPREADSHEET_MAX_ROWS:,} rows._"
    if sheet.truncated_columns:
        yield ""
        yield f"_Sheet truncated after {SPREADSHEET_MAX_COLUMNS:,} columns._"


def render_spreadsheet(
    sheets: Sequence[SpreadsheetSheet],
    *,
    max_chars: int = SPREADSHEET_MAX_TEXT_CHARS,
) -> str:
    """Render every sheet as Markdown tables bounded by ``max_chars``.

    The first non-empty row of each sheet becomes the table header. Trailing
    empty rows and columns are removed before rendering, and a workbook that
    exceeds ``max_chars`` stops at a line boundary with a visible notice. Lines
    are accumulated under the budget so a workbook cannot materialize an
    unbounded rendered string.
    """
    if max_chars <= 0:
        return ""
    notice = f"_Workbook text truncated at {max_chars:,} characters._"
    budget = max_chars - len(notice) - 2
    if budget <= 0:
        return "_Truncated._"[:max_chars]

    lines: list[str] = []
    used = 0
    truncated = False
    for sheet in sheets:
        if lines:
            if used + 1 > budget:
                truncated = True
                break
            lines.append("")
            used += 1
        for line in _sheet_lines(sheet):
            addition = len(line) + (1 if lines else 0)
            if used + addition > budget:
                truncated = True
                break
            lines.append(line)
            used += addition
        if truncated:
            break

    rendered = "\n".join(lines).rstrip()
    if not truncated:
        return rendered
    return f"{rendered}\n\n{notice}" if rendered else notice


__all__ = [
    "SPREADSHEET_EXTENSIONS",
    "SPREADSHEET_FORMULA_FALLBACK_EXTENSIONS",
    "SPREADSHEET_MAX_ARCHIVE_BYTES",
    "SPREADSHEET_MAX_ARCHIVE_ENTRIES",
    "SPREADSHEET_MAX_ARCHIVE_ENTRY_BYTES",
    "SPREADSHEET_MAX_CELL_CHARS",
    "SPREADSHEET_MAX_COLUMNS",
    "SPREADSHEET_MAX_DECLARED_CELLS",
    "SPREADSHEET_MAX_DECLARED_COLUMNS",
    "SPREADSHEET_MAX_DECLARED_ROWS",
    "SPREADSHEET_MAX_ROWS",
    "SPREADSHEET_MAX_TEXT_CHARS",
    "SpreadsheetSheet",
    "format_spreadsheet_cell",
    "render_spreadsheet",
]
