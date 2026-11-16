"""Safety rules for one Plotly figure rendered inside a chat message.

A plot is display-only: the full figure lives in ``agent_entry.data.plot`` and
never enters the provider context. This module answers one deterministic,
offline question: is this figure small, inert, and JSON-clean enough to hand to
the browser? It walks the structure with an explicit stack rather than
recursion, so a hostile nesting depth cannot exhaust the interpreter stack, and
it rejects every construct that could turn an inert chart into code or a
network request.
"""

import json
import math
from dataclasses import dataclass
from typing import Any

from app.module.agent.exception.domain_error import AgentError

MAX_PLOT_BYTES = 200_000
MAX_PLOT_TRACES = 12
MAX_PLOT_POINTS = 2_000
MAX_PLOT_NODES = 50_000
MAX_PLOT_DEPTH = 20

# Only ``data`` and ``layout`` describe a chart. ``frames`` (animation) and any
# other top-level key are rejected instead of silently dropped, so a caller can
# never believe part of its figure was rendered when it was not.
_ALLOWED_FIGURE_KEYS = frozenset({"data", "layout"})
# Rejected at every depth, not only directly under ``layout``: Plotly honours
# these keys wherever a nested object lands, and each one can load external
# content (images, tiles, templates) or build interactive/animated controls.
_FORBIDDEN_KEYS = frozenset(
    {
        "images",
        "mapbox",
        "geo",
        "map",
        "updatemenus",
        "sliders",
        "template",
        "href",
        "url",
        "src",
        "source",
    }
)
_FORBIDDEN_TRACE_TYPES = frozenset(
    {
        "scattermapbox",
        "choroplethmapbox",
        "densitymapbox",
        "scattergeo",
        "choropleth",
        "scattermap",
        "choroplethmap",
        "densitymap",
    }
)
_FORBIDDEN_SCHEMES = ("javascript:", "vbscript:", "data:text/html")
# The per-trace arrays whose longest length is that trace's point count.
_POINT_KEYS = (
    "x",
    "y",
    "z",
    "values",
    "labels",
    "lat",
    "lon",
    "r",
    "theta",
    "open",
    "high",
    "low",
    "close",
)


class PlotSpecError(AgentError):
    """A figure that is unsafe, malformed, or too large for the chat UI."""


@dataclass(frozen=True)
class SanitizedPlot:
    """A validated, deep-copied figure plus the statistics the UI reports."""

    figure: dict[str, Any]
    trace_count: int
    point_count: int
    byte_size: int
    # Present only for one trace whose 2D point arrays share one rectangular
    # shape. The tool receipt uses it to show that a grid was not truncated.
    grid_rows: int | None = None
    grid_columns: int | None = None


def sanitize_plot_figure(figure: dict[str, Any]) -> SanitizedPlot:
    """Validate one Plotly figure and return a deep-copied sanitized figure.

    The caller's dict is never mutated. Every rejection raises
    ``PlotSpecError`` with a short fixed message; the figure and the underlying
    exception are deliberately kept out of the error.
    """
    if not isinstance(figure, dict):
        raise PlotSpecError("The plot figure must be an object.")
    if set(figure) - _ALLOWED_FIGURE_KEYS:
        raise PlotSpecError("The plot figure may only contain data and layout.")

    raw_data = figure.get("data")
    if not isinstance(raw_data, list) or not raw_data:
        raise PlotSpecError("The plot figure needs at least one trace.")
    if len(raw_data) > MAX_PLOT_TRACES:
        raise PlotSpecError("The plot figure has too many traces.")
    if any(not isinstance(trace, dict) for trace in raw_data):
        raise PlotSpecError("Every plot trace must be an object.")

    raw_layout = figure.get("layout")
    if raw_layout is not None and not isinstance(raw_layout, dict):
        raise PlotSpecError("The plot layout must be an object.")

    _validate_tree(figure)
    point_count = _count_points(raw_data)
    grid_shape = _grid_shape(raw_data)
    if grid_shape is not None and grid_shape[0] * grid_shape[1] != point_count:
        grid_shape = None
    clean: dict[str, Any] = {"data": _copy(raw_data)}
    if raw_layout is not None:
        clean["layout"] = _copy(raw_layout)
    encoded = _serialize(clean)
    return SanitizedPlot(
        figure=clean,
        trace_count=len(raw_data),
        point_count=point_count,
        byte_size=len(encoded),
        grid_rows=grid_shape[0] if grid_shape is not None else None,
        grid_columns=grid_shape[1] if grid_shape is not None else None,
    )


def _validate_tree(figure: dict[str, Any]) -> None:
    """Walk the figure iteratively, rejecting unsafe keys, types, and strings."""
    stack: list[tuple[object, int]] = [(figure, 0)]
    visited = 0
    while stack:
        node, depth = stack.pop()
        visited += 1
        if visited > MAX_PLOT_NODES:
            raise PlotSpecError("The plot figure is too complex.")
        if depth > MAX_PLOT_DEPTH:
            raise PlotSpecError("The plot figure is nested too deeply.")
        if isinstance(node, dict):
            for key, value in node.items():
                if not isinstance(key, str):
                    raise PlotSpecError("The plot figure contains a non-text key.")
                _validate_string(key)
                lowered = key.lower()
                if lowered in _FORBIDDEN_KEYS:
                    raise PlotSpecError("The plot figure uses a key that is not allowed.")
                if (
                    lowered == "type"
                    and isinstance(value, str)
                    and value.lower() in _FORBIDDEN_TRACE_TYPES
                ):
                    raise PlotSpecError("Map and geo traces are not supported in a chat plot.")
                stack.append((value, depth + 1))
        elif isinstance(node, list):
            for item in node:
                stack.append((item, depth + 1))
        elif isinstance(node, str):
            _validate_string(node)
        elif node is None or isinstance(node, bool):
            continue
        elif isinstance(node, (int, float)):
            if isinstance(node, float) and not math.isfinite(node):
                raise PlotSpecError("The plot figure contains a non-finite number.")
        else:
            raise PlotSpecError("The plot figure contains an unsupported value.")


def _validate_string(value: str) -> None:
    """Reject script and inline-document schemes, ignoring case and whitespace."""
    compact = "".join(value.split()).lower()
    if any(scheme in compact for scheme in _FORBIDDEN_SCHEMES):
        raise PlotSpecError("The plot figure links to script or external content.")


def _count_points(traces: list[dict[str, Any]]) -> int:
    """Sum each trace's largest cell count and enforce the global point cap.

    A 2D coordinate array is one point per cell, not one point per row: a
    ``surface`` or ``heatmap`` with a 7 x 9 ``z`` array carries 63 points. Flat
    arrays count their length, and ragged rows are summed cell by cell.
    """
    total = 0
    for trace in traces:
        counts = [
            _count_array_cells(trace[key])
            for key in _POINT_KEYS
            if isinstance(trace.get(key), list)
        ]
        if counts:
            total += max(counts)
    if total > MAX_PLOT_POINTS:
        raise PlotSpecError("The plot figure has too many data points.")
    return total


def _count_array_cells(values: list[Any]) -> int:
    """Count leaf cells in one point array, summing every ragged row."""
    cells = 0
    for value in values:
        if isinstance(value, list):
            cells += _count_array_cells(value)
        else:
            cells += 1
    return cells


def _grid_shape(traces: list[dict[str, Any]]) -> tuple[int, int] | None:
    """Return one unambiguous rectangular 2D shape for a single-trace figure.

    The receipt only reports rows and columns when the whole figure is one grid
    with one shape. Mixed, ragged, or multi-trace figures keep the correct cell
    count without claiming a shape that could mislead the model.
    """
    if len(traces) != 1:
        return None
    trace = traces[0]
    shape: tuple[int, int] | None = None
    for key in _POINT_KEYS:
        value = trace.get(key)
        if not isinstance(value, list) or not value:
            continue
        if not all(isinstance(row, list) for row in value):
            continue
        rows = [row for row in value if isinstance(row, list)]
        columns = len(rows[0])
        if columns == 0 or any(len(row) != columns for row in rows):
            return None
        if any(isinstance(cell, list) for row in rows for cell in row):
            return None
        candidate = (len(rows), columns)
        if shape is None:
            shape = candidate
        elif shape != candidate:
            return None
    return shape


def _serialize(figure: dict[str, Any]) -> bytes:
    """Serialize canonically and reject NaN/Infinity or an oversized payload."""
    try:
        encoded = json.dumps(
            figure,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PlotSpecError("The plot figure is not valid JSON.") from exc
    if len(encoded) > MAX_PLOT_BYTES:
        raise PlotSpecError("The plot figure is too large.")
    return encoded


def _copy(value: Any) -> Any:
    """Deep-copy one already-validated JSON value without sharing references."""
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value
