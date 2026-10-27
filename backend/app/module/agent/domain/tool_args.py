"""Validated argument models for every agent tool."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema


class _ToolArgs(BaseModel):
    """Base class: reject unknown model arguments instead of ignoring them."""

    model_config = ConfigDict(extra="forbid")


class SearchKnowledgeArgs(_ToolArgs):
    """Arguments for hybrid archive search."""

    query: str = Field(min_length=1, max_length=200)
    result_number: int = Field(default=8, ge=1, le=20)
    include_history: bool = False


class ReadFileArgs(_ToolArgs):
    """Arguments for a bounded file chunk window."""

    file_id: int = Field(gt=0)
    chunk: int = Field(default=1, ge=1)
    chunk_range: int = Field(default=1, ge=0, le=25)


class ReadTimelineArgs(_ToolArgs):
    """Arguments for the sparse timeline."""

    year: int = Field(ge=1970, le=2100)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    day_range: int = Field(default=7, ge=1, le=366)
    include_history: bool = False


class ReadPathArgs(_ToolArgs):
    """Arguments for listing one library path."""

    path: str = Field(default="/", min_length=1, max_length=1024)
    path_depth: int = Field(default=2, ge=1, le=10)
    fuzzy_search: str | None = Field(default=None, max_length=128)


class ReadMemoryArgs(_ToolArgs):
    """Arguments for reading a memory and its chain."""

    memory_id: int = Field(gt=0)
    memory_range: int = Field(default=2, ge=0, le=10)
    trace_history: bool = True


class SaveMemoryArgs(_ToolArgs):
    """Arguments for a memory write or a direct, replacement-free deprecation."""

    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=8000,
        description=(
            "The memory text to save. Omit it when the call only retires the "
            "memories listed in supersedes."
        ),
    )
    supersedes: list[int] = Field(default_factory=list, max_length=50)
    reason: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Why the memories are being retired. Only valid when content is "
            "omitted; it is stored on each deprecated row."
        ),
    )
    occurred_at: datetime | None = None
    user_confirmed: bool = Field(
        default=False,
        description=(
            "Legacy model-supplied hint. It never authorizes a write; the backend "
            "records an explicit human approval before executing save_memory."
        ),
    )

    @model_validator(mode="after")
    def _validate_shape(self) -> "SaveMemoryArgs":
        """Require either new content or an explicit deprecation target."""
        has_content = self.content is not None and bool(self.content.strip())
        if has_content:
            if self.reason is not None:
                raise ValueError(
                    "reason is only allowed when content is omitted (deprecation-only)."
                )
            return self
        if self.content is not None:
            raise ValueError("content must not be blank.")
        if not self.supersedes:
            raise ValueError("Provide content to save a memory, or supersedes ids to deprecate.")
        if self.occurred_at is not None:
            raise ValueError("occurred_at is only allowed when saving content.")
        if self.reason is not None and not self.reason.strip():
            raise ValueError("reason must not be blank when provided.")
        return self


class PresentResourceArgs(_ToolArgs):
    """Arguments for a viewer card."""

    resource_type: Literal["file", "memory"]
    resource_id: int = Field(gt=0)
    chunk: int | None = Field(default=None, ge=1)


class WebSearchArgs(_ToolArgs):
    """Arguments for one public web search."""

    # max_results is capped at 10 and each domain list at 10 entries: a single
    # search must not flood the context window, and the provider must not receive
    # an oversized filter list. The 400-character query limit is enough to express
    # a query while keeping the model from stuffing a whole private document into
    # the URL or query string.
    query: str = Field(min_length=1, max_length=400)
    max_results: int = Field(default=5, ge=1, le=10)
    search_depth: Literal["basic", "advanced"] = "basic"
    include_domains: list[str] = Field(default_factory=list, max_length=10)
    exclude_domains: list[str] = Field(default_factory=list, max_length=10)


class WebFetchArgs(_ToolArgs):
    """Arguments for fetching one server-defined page of a public http(s) URL."""

    # page is the only supported starting point: the service slices pages by a
    # fixed character budget, so the model just moves forward with page=1, 2, ...
    # and never has to compute line numbers or offsets. offset / limit / max_chars
    # are kept for compatibility only: old conversations frozen at
    # archive-tools-v4 (url + max_chars) and archive-tools-v5 (offset / limit /
    # page) still send these parameters and must keep passing validation;
    # SkipJsonSchema keeps the model-facing schema limited to url and page for new
    # conversations. Page mode ignores max_chars and limit.
    # The URL length cap matches WebUrlSafety's 1-2048.
    url: str = Field(min_length=1, max_length=2048)
    page: int = Field(default=1, ge=1)
    offset: SkipJsonSchema[int | None] = Field(default=None, ge=1)
    limit: SkipJsonSchema[int | None] = Field(default=None, ge=1, le=2_000)
    max_chars: SkipJsonSchema[int | None] = Field(default=None, ge=1_000, le=20_000)

    @model_validator(mode="before")
    @classmethod
    def _drop_null_page(cls, data: object) -> object:
        """Treat a legacy explicit ``page=null`` as an omitted page.

        The v5 schema allowed ``page: null``; frozen conversations may still
        send it together with ``offset``. Dropping it here keeps that payload
        valid while the new model-facing schema stays a plain integer.
        """
        if isinstance(data, dict) and data.get("page") is None:
            return {key: value for key, value in data.items() if key != "page"}
        return data

    @model_validator(mode="after")
    def _validate_start(self) -> "WebFetchArgs":
        """Reject two explicit start positions in one call.

        ``model_fields_set`` distinguishes an explicit ``offset`` from its
        default, so ``{"page": 2}`` is valid while ``{"offset": 1, "page": 2}``
        is a validation error. A legacy call with only ``offset`` or only
        ``max_chars`` remains valid.
        """
        if "offset" in self.model_fields_set and "page" in self.model_fields_set:
            raise ValueError("Use either offset or page, not both.")
        return self
