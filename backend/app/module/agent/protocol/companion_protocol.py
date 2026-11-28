"""Consumer-owned contracts for the companion persona, lore, and bond."""

from collections.abc import Sequence
from typing import Protocol

from app.module.agent.domain.companion_persona_domain import (
    CompanionPersona,
    LibrarianMemory,
)


class CompanionPersonaLoaderProtocol(Protocol):
    """Resolve the account's active companion persona for a new conversation."""

    async def __call__(self, locale: str | None) -> CompanionPersona | None: ...


class LibrarianMemoryRecallProtocol(Protocol):
    """Offer the conversation companion's own memories for one search."""

    async def recall(
        self,
        query: str,
        context: Sequence[str],
    ) -> list[LibrarianMemory]: ...


class CompanionRunObserverProtocol(Protocol):
    """Count a completed run toward the conversation companion's bond."""

    async def run_completed(self, conversation_id: int) -> None: ...


class CompanionStoryMomentProtocol(Protocol):
    """Offer a paced story moment from the conversation companion, if one is due."""

    async def story_moment(self, conversation_id: int) -> LibrarianMemory | None: ...


__all__ = [
    "CompanionPersonaLoaderProtocol",
    "CompanionRunObserverProtocol",
    "CompanionStoryMomentProtocol",
    "LibrarianMemoryRecallProtocol",
]
