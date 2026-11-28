"""Render the companion's own memories wherever they enter a run.

Every input site of a run (the user's message with its page context and
attachment names, and every tool result) may receive contributions from the
companion context contributor. They are rendered here into one
``<librarian_memories>`` block, so the model always sees the companion's own
memories in the same shape and never confuses them with archive sources.

The block is pure data; the configured guidance travels on each contribution,
so the agent hardcodes no story wording.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.module.agent.domain.xml_domain import attributes, clip, xml_text
from app.module.agent.protocol.companion_protocol import ContextContribution

# Bounded text of one signal; embeddings and phrase checks need no more.
SIGNAL_TEXT_LIMIT = 1_600

# Keys of the provider-only suffixes stored on a user entry, appended to the
# user's message in this order. ``story_moment`` is the legacy key written by
# conversations before the unified contributor; it is still read.
USER_SUFFIX_KEYS: tuple[str, ...] = ("time_context", "companion_context", "story_moment")

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


@dataclass
class CompanionTurnContext:
    """Per-run companion state shared by every input site of one run.

    ``offered`` holds every fragment id already offered in this run, so the
    contributor never repeats one and the per-run cap counts every site.
    """

    conversation_id: int
    run_id: int | None = None
    offered: set[str] = field(default_factory=set)

    def remember(self, contributions: Iterable[ContextContribution]) -> None:
        """Add offered contribution ids to the run's set."""
        self.offered.update(item.id for item in contributions)


def signal_text(*parts: str | None, limit: int = SIGNAL_TEXT_LIMIT) -> str:
    """Join plain-text parts (markup stripped, whitespace folded) and clip them."""
    cleaned = (_SPACE.sub(" ", _TAG.sub(" ", part)).strip() for part in parts if part)
    return clip(" ".join(part for part in cleaned if part), limit)


def render_contributions(contributions: Sequence[ContextContribution]) -> str:
    """Return one ``<librarian_memories>`` block, or ``""`` when none are offered.

    The block carries ``moment`` when every memory shares it, each distinct
    configured guidance once, and every memory with its id, tier, and moment.
    """
    if not contributions:
        return ""
    moments = {item.moment for item in contributions}
    block_attrs: dict[str, object] = {}
    if len(moments) == 1:
        block_attrs["moment"] = next(iter(moments))
    parts = [f"<librarian_memories{attributes(block_attrs)}>"]
    seen: set[str] = set()
    for item in contributions:
        guidance = item.guidance.strip()
        if guidance and guidance not in seen:
            seen.add(guidance)
            parts.append(
                f"<guidance{attributes({'moment': item.moment})}>{xml_text(guidance)}</guidance>"
            )
    for item in contributions:
        values = {"id": item.id, "tier": item.tier, "moment": item.moment}
        parts.append(
            f"<librarian_memory{attributes(values)}>{xml_text(item.text)}</librarian_memory>"
        )
    parts.append("</librarian_memories>")
    return "".join(parts)


def contribution_data(contributions: Sequence[ContextContribution]) -> list[dict[str, str]]:
    """Return the UI copy of offered memories (``data["lore"]`` on a tool result)."""
    return [
        {"id": item.id, "tier": item.tier, "text": item.text, "moment": item.moment}
        for item in contributions
    ]


def merge_user_suffixes(data: Mapping[str, Any] | None) -> list[str]:
    """Return the provider-only suffixes of a user entry, in their fixed order."""
    if not isinstance(data, Mapping):
        return []
    return [
        value
        for value in (data.get(key) for key in USER_SUFFIX_KEYS)
        if isinstance(value, str) and value
    ]


__all__ = [
    "SIGNAL_TEXT_LIMIT",
    "USER_SUFFIX_KEYS",
    "CompanionTurnContext",
    "contribution_data",
    "merge_user_suffixes",
    "render_contributions",
    "signal_text",
]
