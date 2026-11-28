"""The frozen tool catalog injected into a conversation's system entry.

The catalog is built once per conversation and stored in ``pi.system``. Changing a
description or parameter schema therefore only affects new conversations, which
keeps the provider cache prefix honest.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel

from app.module.agent.domain.tool_args import (
    CalculateArgs,
    CompanionActionArgs,
    HistoryMessageArgs,
    PresentResourceArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ReadPathArgs,
    ReadTimelineArgs,
    RenderPlotArgs,
    SaveMemoryArgs,
    SearchKnowledgeArgs,
    WebFetchArgs,
    WebSearchArgs,
)

# v12 unifies custom sections and the four seeded defaults into one ordered
# collection: every row uses ``system_prompt:<id>`` and there is no read-time
# built-in append. v13 adds the Exa search-tool ``objective`` instruction.
# v14 adds the ``<search_hint>`` sentence to the Context protocol section.
# Composition changed, so the new-conversation prefix changes; existing
# conversations keep their frozen ``pi.system`` and old version string, so their
# KV cache lineage is untouched. v15 adds the companion_action guidance line.
PROMPT_VERSION = "archive-agent-v15"
# v6 replaced web_fetch's line-offset pagination with server-defined pages. v7
# makes ``objective`` a required web_search field in the model-facing schema
# while keeping it optional on the validation model, so conversations frozen on
# v6 still validate. v8 adds the conversation-history lane to search_knowledge
# and the read-only history_message tool. v9 adds calculate and render_plot.
# v10 tightens render_plot's point guidance after a truncated output-limit call.
# v11 makes render_plot a once-per-turn action and states that the success receipt
# is authoritative. v12 raises render_plot's density caps for 3D grids and tells
# the model to pass a complete figure instead of a placeholder. v13 removes the
# fixed point/byte/node numbers from render_plot's description because those
# budgets now come from the deployer-editable agent_config row; the tool still
# enforces them. v14 adds per-result content_chars/excerpt_chars/excerpt_truncated
# and the trailing <search_hint> to web_search. Existing conversations keep their
# frozen pi.system snapshot. v15 adds the read-only companion_action gesture tool.
TOOLS_VERSION = "archive-tools-v15"

PLOT_TOOL_NAME = "render_plot"


@dataclass(frozen=True)
class ToolSpec:
    """One tool's model-facing definition and argument validator."""

    name: str
    description: str
    args_model: type[BaseModel]
    requires_confirmation: bool = False
    # Fields that are required in the model-facing schema for new
    # conversations. They stay optional on the Pydantic model so a conversation
    # frozen on an earlier tools version can still omit them.
    required_fields: tuple[str, ...] = ()

    def parameters(self) -> dict[str, Any]:
        """Return a compact, deterministic JSON schema for the arguments."""
        schema = _inline_refs(_clean_schema(self.args_model.model_json_schema()))
        if self.required_fields:
            required = list(schema.get("required", []))
            for field_name in self.required_fields:
                if field_name not in required:
                    required.append(field_name)
            schema["required"] = required
        return schema

    def definition(self) -> dict[str, Any]:
        """Return one OpenAI-compatible function tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters(),
            },
        }


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="search_knowledge",
        description=(
            "Search the archive for files, memories, periodic summaries, and "
            "past conversation windows. Use this before making factual claims. "
            "Results carry source labels such as [file:10#2], [memory:7], and "
            "[history:123]. A history hit is a raw 256-character window; use "
            "history_message with its id when the excerpt is not enough."
        ),
        args_model=SearchKnowledgeArgs,
    ),
    ToolSpec(
        name="read_file",
        description=(
            "Read a bounded chunk window from a text file by file id. Find ids "
            "with search_knowledge or read_path. Cite chunks as [file:id#chunk]."
        ),
        args_model=ReadFileArgs,
    ),
    ToolSpec(
        name="read_timeline",
        description=(
            "Read a sparse timeline of memories, summaries, and file updates for "
            "one date range. Use it for questions about what happened when."
        ),
        args_model=ReadTimelineArgs,
    ),
    ToolSpec(
        name="read_path",
        description=(
            "List folders and files under one File Library path. Use '/' for the "
            "root. Fuzzy search is only a fallback when the exact path is unknown."
        ),
        args_model=ReadPathArgs,
    ),
    ToolSpec(
        name="read_memory",
        description=(
            "Read one memory with its neighboring memories, supersession chain, "
            "and deprecation history. Cite it as [memory:id]."
        ),
        args_model=ReadMemoryArgs,
    ),
    ToolSpec(
        name="history_message",
        description=(
            "Read one past conversation message by its stable entry id, with "
            "optional neighbouring messages. search_knowledge returns history "
            "windows as <history_message id=\"...\">; use that id here when the "
            "window is not enough. Cite the message as [history:id]."
        ),
        args_model=HistoryMessageArgs,
    ),
    ToolSpec(
        name="save_memory",
        description=(
            "Save a new memory, or retire existing memories without a "
            "replacement. Save ONLY when the user explicitly asks you to remember "
            "or record something and confirms the wording; never save inferred, "
            "speculative, or unconfirmed content. To retire memories because they "
            "are done, cancelled, or no longer true, omit content and pass their "
            "ids in supersedes (optionally with reason). That deprecates the rows "
            "directly and writes no new memory. This is a write action."
        ),
        args_model=SaveMemoryArgs,
        requires_confirmation=True,
    ),
    ToolSpec(
        name="present_resource",
        description=(
            "Show a file or memory to the user as a viewer card. Use this when "
            "the user should open the resource. Images are presented as files. "
            "It only returns the viewer URL and metadata; it does not fetch "
            "content."
        ),
        args_model=PresentResourceArgs,
    ),
    ToolSpec(
        name="calculate",
        description=(
            "Evaluate an arithmetic expression with a precise calculator. Use "
            "this tool for every arithmetic step instead of doing mental math: "
            "totals, percentages, ratios, averages, compound expressions, and "
            "multi-step calculations. Pass one expression per call. Supports "
            "+ - * / // % **, parentheses, and functions: abs, round, min, max, "
            "sum, avg, mean, sqrt, exp, log, log10, log2, sin, cos, tan, asin, "
            "acos, atan, atan2, floor, ceil, trunc, radians, degrees, hypot, "
            "fabs; constants pi, e, tau. `%` is modulo, not percent; write 15% "
            "as 15/100. Do not use variables, strings, attributes, or symbolic "
            "algebra. If a calculation has several steps, call the tool once "
            "per step or combine them with parentheses."
        ),
        args_model=CalculateArgs,
    ),
    ToolSpec(
        name="render_plot",
        description=(
            "Render a Plotly chart inline in the chat. Use this whenever a "
            "visual makes numeric or comparative information easier to "
            "understand. Pass figure.data as an array of Plotly trace objects "
            "and figure.layout as a layout object. Common traces include bar, "
            'scatter with mode "lines", pie, histogram, box, violin, and '
            "heatmap. Keep the figure small: at most 12 traces, and the "
            "current point, byte, and node budgets are enforced by the tool. "
            "For generated or random data, prefer 50-200 points. For a 3D "
            "surface, use a 30x30 to 60x60 grid (900-3,600 cells). Put the "
            "chart title in `title`, not layout.title. Use "
            "clear axis labels and units; use a small color palette and do not "
            "rely on color alone. All data must be inline. Do not use "
            "layout.images, layout.mapbox, layout.geo, layout.map, "
            "layout.updatemenus, layout.sliders, layout.template, external "
            "URLs, or map/geo traces. Call render_plot at most once per assistant "
            "turn. After it succeeds, explain the chart in text; do not call it "
            "again for the same request. Always pass a complete figure."
        ),
        args_model=RenderPlotArgs,
    ),
    ToolSpec(
        name="web_search",
        description=(
            "Search the public web with the configured web-search provider. "
            "Use for current external facts not in the archive. Provide both "
            "query and objective. Results are bounded excerpts with title, URL, "
            "score, and excerpt metadata; the <search_hint> element states when "
            "content was clipped and that web_fetch recovers the rest. Cite the "
            "URL. Read-only."
        ),
        args_model=WebSearchArgs,
        requires_confirmation=False,
        required_fields=("query", "objective"),
    ),
    ToolSpec(
        name="web_fetch",
        description=(
            "Fetch one server-defined page of a public http(s) URL as Markdown. "
            "Call page=1, then page=2, ... until has_more=false. Pages are "
            "server-sized, contiguous, and do not require offsets. Never claim "
            "content beyond what you actually read. Cite the URL. Read-only."
        ),
        args_model=WebFetchArgs,
        requires_confirmation=False,
    ),
    ToolSpec(
        name="companion_action",
        description=(
            "Make the on-screen companion perform one visible gesture, such as "
            "greet, thinking, success, or confused. It only changes the "
            "animation beside the chat; it reads and writes no archive data. "
            "The interface already animates searches and tool calls, so use "
            "this sparingly: at most once per turn, when a gesture adds warmth "
            "or clarity. Never use it instead of answering."
        ),
        args_model=CompanionActionArgs,
    ),
)


def tool_definitions() -> list[dict[str, Any]]:
    """Build a fresh frozen tool-definition list for a new conversation."""
    return [spec.definition() for spec in TOOL_SPECS]


def tool_catalog() -> list[dict[str, Any]]:
    """Return the public catalog shown by the UI and method page."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters(),
            "requires_confirmation": spec.requires_confirmation,
        }
        for spec in TOOL_SPECS
    ]


def display_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Return the human-readable argument form shown by the UI.

    A figure is UI state, not reasoning state. The complete figure travels in
    the tool result's ``plot.figure``; the tool-call and tool-result display
    payloads only need the title and caption. Other tools keep their arguments
    unchanged.
    """
    if name != PLOT_TOOL_NAME:
        return arguments
    return {
        "title": arguments.get("title"),
        "caption": arguments.get("caption"),
    }


def _clean_schema(value: object, *, keep_keys: bool = False) -> Any:
    """Drop Pydantic title noise while preserving property order.

    ``keep_keys`` is set while cleaning a ``properties`` mapping: there a key is
    an argument name, so a tool that really has a ``title`` argument keeps it.
    The generated ``title`` annotation inside each property schema is still
    removed.
    """
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key == "title" and not keep_keys:
                continue
            cleaned[key] = _clean_schema(item, keep_keys=key == "properties")
        return cleaned
    if isinstance(value, list):
        return [_clean_schema(item, keep_keys=keep_keys) for item in value]
    return value


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline Pydantic ``$defs`` so the model-facing schema is self-contained.

    Function-calling providers accept only a subset of JSON Schema, and a
    top-level ``$defs`` map with ``$ref`` pointers is its least portable part.
    The definitions are local, so resolving them here yields one flat schema
    that describes exactly the same contract without exposing an internal model
    name to the provider.
    """
    definitions = schema.pop("$defs", None)
    if not isinstance(definitions, dict):
        return schema
    resolved_defs = {
        name: _inline_refs(definition)
        for name, definition in definitions.items()
        if isinstance(definition, dict)
    }
    return cast(dict[str, Any], _resolve_refs(schema, resolved_defs, depth=0))


def _resolve_refs(value: Any, definitions: Mapping[str, Any], *, depth: int) -> Any:
    """Replace local ``$ref`` objects with their definition, with a depth cap."""
    if depth > 10:
        return value
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = definitions.get(ref.removeprefix("#/$defs/"))
            if isinstance(target, dict):
                resolved = _resolve_refs(target, definitions, depth=depth + 1)
                siblings = {key: item for key, item in value.items() if key != "$ref"}
                if siblings and isinstance(resolved, dict):
                    return {
                        **resolved,
                        **_resolve_refs(siblings, definitions, depth=depth + 1),
                    }
                return resolved
        return {
            key: _resolve_refs(item, definitions, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_resolve_refs(item, definitions, depth=depth + 1) for item in value]
    return value
