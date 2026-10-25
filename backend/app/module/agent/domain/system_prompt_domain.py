"""Immutable system-prompt sections passed to the context builder."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SystemPromptSection:
    """One ordered prompt section.

    Every row is equal: seeded defaults and owner-authored sections share the
    same table and the same CRUD surface. The frozen dataclass crosses the
    repository/service boundary so callers do not receive a live ORM row.
    ``body`` is still filtered for whitespace at composition time: a row copied
    by the migration or edited directly in SQL must never inject an empty
    heading into the provider prompt.
    """

    id: int
    title: str
    body: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


__all__ = ["SystemPromptSection"]
