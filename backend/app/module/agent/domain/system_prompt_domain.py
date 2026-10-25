"""Immutable system-prompt text passed to the context builder."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SystemPromptText:
    """One custom prompt section; empty bodies mean the built-in prompt only."""

    title: str
    body: str
    updated_at: datetime | None = None
