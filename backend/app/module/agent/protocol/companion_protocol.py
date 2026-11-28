"""Consumer-owned contracts for the companion persona, context, and bond.

The companion context contributor is the single path by which a companion's
own memories enter a run. Every input site (the user's message, its page
context, its attachment names, and every tool result) builds one
:class:`ContextSignal`; the contributor decides whether to offer anything
(story moment, topical recall, or a self query) and returns
:class:`ContextContribution` items the agent renders in one
``<librarian_memories>`` block.
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.module.agent.domain.companion_persona_domain import CompanionPersona

ContextSite = Literal["user_message", "page_context", "attachment", "tool_result"]
ContributionMoment = Literal["story", "topical", "self"]


@dataclass(frozen=True)
class ContextSignal:
    """One input the companion may answer with its own memories.

    ``text`` is bounded (callers clip it to about 1600 characters) and never
    carries attachment bytes. ``query`` is the person's own question when the
    site has one (the user's message, or a search query); only it is checked
    for questions about the librarian itself, never document text.
    ``offered_this_run`` lists fragment ids already offered in this run so the
    contributor never repeats one and counts them toward the per-run cap.
    """

    site: ContextSite
    conversation_id: int
    text: str
    run_id: int | None = None
    tool_name: str | None = None
    resource: tuple[str, int] | None = None
    offered_this_run: frozenset[str] = field(default_factory=frozenset)
    query: str | None = None


@dataclass(frozen=True)
class ContextContribution:
    """One memory the companion offers, with the guidance the model reads."""

    id: str
    tier: str
    text: str
    moment: ContributionMoment
    guidance: str


class CompanionContextContributorProtocol(Protocol):
    """Decide which of the companion's own memories to offer for one signal."""

    async def contribute(self, signal: ContextSignal) -> list[ContextContribution]: ...


class CompanionPersonaLoaderProtocol(Protocol):
    """Resolve the account's active companion persona for a new conversation."""

    async def __call__(self, locale: str | None) -> CompanionPersona | None: ...


class CompanionRunObserverProtocol(Protocol):
    """Count a completed run toward the conversation companion's bond."""

    async def run_completed(self, conversation_id: int) -> None: ...


__all__ = [
    "CompanionContextContributorProtocol",
    "CompanionPersonaLoaderProtocol",
    "CompanionRunObserverProtocol",
    "ContextContribution",
    "ContextSignal",
    "ContextSite",
    "ContributionMoment",
]
