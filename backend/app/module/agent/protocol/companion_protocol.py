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
class RelationshipFacts:
    """Plain facts about how long the person and the librarian have known each other."""

    first_met: str | None
    days_known: int
    conversations: int


@dataclass(frozen=True)
class ContextContribution:
    """One memory the companion offers, with the guidance the model reads.

    ``weight`` (everyday, past, heart) is how much the memory means to her; it
    is never a lock. ``relationship`` carries the relationship facts she weighs.
    """

    id: str
    weight: str
    text: str
    moment: ContributionMoment
    guidance: str
    relationship: RelationshipFacts | None = None


@dataclass(frozen=True)
class OwnMemory:
    """One of the librarian's own memories (lore or a life story) for her own tool."""

    id: str
    weight: str
    text: str


@dataclass(frozen=True)
class CompanionIdentity:
    """Who the librarian of this conversation is."""

    ref: str
    name: str


class CompanionOwnMemoriesProtocol(Protocol):
    """The frozen companion's own memories, looked up by the companion herself."""

    identity: CompanionIdentity

    async def search_own(self, query: str, *, limit: int) -> list[OwnMemory]: ...

    async def relationship(self) -> RelationshipFacts | None: ...

    async def guidance(self) -> str: ...


class CompanionContextContributorProtocol(Protocol):
    """Decide which of the companion's own memories to offer for one signal."""

    async def contribute(self, signal: ContextSignal) -> list[ContextContribution]: ...


class CompanionPersonaLoaderProtocol(Protocol):
    """Resolve the account's active companion persona for a new conversation."""

    async def __call__(self, locale: str | None) -> CompanionPersona | None: ...


class CompanionHandoffProtocol(Protocol):
    """Who speaks in a conversation now, and who the account has chosen.

    ``current`` returns ``{ref, name, locale}`` of the conversation's current
    companion (latest handoff, else the one frozen at creation) or ``None`` for
    the plain archive assistant. ``active`` resolves the account's chosen
    companion persona for ``locale`` or ``None`` when the companion is disabled.
    """

    async def current(self, conversation_id: int) -> dict[str, str] | None: ...

    async def active(self, locale: str | None) -> CompanionPersona | None: ...


class CompanionRunObserverProtocol(Protocol):
    """Count a completed run toward the conversation companion's bond."""

    async def run_completed(self, conversation_id: int) -> None: ...


__all__ = [
    "CompanionContextContributorProtocol",
    "CompanionHandoffProtocol",
    "CompanionIdentity",
    "CompanionOwnMemoriesProtocol",
    "CompanionPersonaLoaderProtocol",
    "CompanionRunObserverProtocol",
    "ContextContribution",
    "ContextSignal",
    "ContextSite",
    "ContributionMoment",
    "OwnMemory",
    "RelationshipFacts",
]
