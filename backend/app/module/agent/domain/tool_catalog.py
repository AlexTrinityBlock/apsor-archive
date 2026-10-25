"""The frozen tool catalog injected into a conversation's system entry.

The catalog is built once per conversation and stored in ``pi.system``. Changing a
description or parameter schema therefore only affects new conversations, which
keeps the provider cache prefix honest.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.module.agent.domain.tool_args import (
    PresentResourceArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ReadPathArgs,
    ReadTimelineArgs,
    SaveMemoryArgs,
    SearchKnowledgeArgs,
    WebFetchArgs,
    WebSearchArgs,
)

# v12 unifies custom sections and the four seeded defaults into one ordered
# collection: every row uses ``system_prompt:<id>`` and there is no read-time
# built-in append. Composition changed, so the new-conversation prefix changes;
# existing conversations keep their frozen ``pi.system`` and old version string,
# so their KV cache lineage is untouched.
PROMPT_VERSION = "archive-agent-v12"
TOOLS_VERSION = "archive-tools-v4"


@dataclass(frozen=True)
class ToolSpec:
    """One tool's model-facing definition and argument validator."""

    name: str
    description: str
    args_model: type[BaseModel]
    requires_confirmation: bool = False

    def parameters(self) -> dict[str, Any]:
        """Return a compact, deterministic JSON schema for the arguments."""
        return _clean_schema(self.args_model.model_json_schema())

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
            "Search the archive for files, memories, and periodic summaries. "
            "Use this before making factual claims. Results carry source labels "
            "such as [file:10#2] and [memory:7]."
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
        name="web_search",
        description=(
            "Search the public web with the configured web-search provider. "
            "Use for current external facts not in the archive. Results include "
            "title, URL, and an excerpt. Cite the URL. Read-only."
        ),
        args_model=WebSearchArgs,
        requires_confirmation=False,
    ),
    ToolSpec(
        name="web_fetch",
        description=(
            "Fetch one public http(s) URL and return Markdown text. Use after "
            "web_search when an excerpt is insufficient. Cite the URL. Read-only."
        ),
        args_model=WebFetchArgs,
        requires_confirmation=False,
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


def _clean_schema(value: object) -> Any:
    """Drop Pydantic title noise while preserving property order."""
    if isinstance(value, dict):
        return {key: _clean_schema(item) for key, item in value.items() if key != "title"}
    if isinstance(value, list):
        return [_clean_schema(item) for item in value]
    return value
