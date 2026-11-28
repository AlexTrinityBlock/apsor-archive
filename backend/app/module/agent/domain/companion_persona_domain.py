"""The companion values the agent freezes into a conversation and reads in tools.

The agent slice does not know how personas or lore are stored. The composition
root resolves them from the companion slice and hands the agent these plain
values: the rendered persona section (persona followed by the rules that
outrank it) and the librarian memories chosen for one search.
"""

from dataclasses import dataclass
from typing import Any

from app.module.agent.domain.xml_domain import xml_attr, xml_text

PERSONA_SECTION_NAME = "companion_persona"


@dataclass(frozen=True)
class CompanionPersona:
    """The companion a new conversation speaks as, frozen at creation."""

    ref: str
    name: str
    locale: str
    content: str

    def section(self) -> dict[str, str]:
        """Return the system section rendered after the user profile."""
        return {
            "name": PERSONA_SECTION_NAME,
            "title": f"Companion persona: {self.name}",
            "content": self.content,
        }

    def frozen(self) -> dict[str, str]:
        """Return the identity stored in the system entry's data."""
        return {"ref": self.ref, "name": self.name, "locale": self.locale}


@dataclass(frozen=True)
class LibrarianMemory:
    """One of the companion's own lore fragments offered beside a search."""

    id: str
    text: str
    tier: str
    # The companion slice's configured guidance for this memory; the agent
    # never hardcodes story wording.
    guidance: str = ""


def render_story_moment(memory: LibrarianMemory) -> str:
    """Return the block appended to the user's message for a story moment."""
    guidance = f"<guidance>{xml_text(memory.guidance)}</guidance>" if memory.guidance else ""
    return (
        f'<librarian_memory moment="story" id={xml_attr(memory.id)} '
        f"tier={xml_attr(memory.tier)}>"
        f"{guidance}{xml_text(memory.text)}</librarian_memory>"
    )


def frozen_companion(system_data: Any) -> tuple[str, str] | None:
    """Return ``(ref, locale)`` frozen in a system entry, or ``None``."""
    if not isinstance(system_data, dict):
        return None
    companion = system_data.get("companion")
    if not isinstance(companion, dict):
        return None
    ref = companion.get("ref")
    locale = companion.get("locale")
    if not isinstance(ref, str) or not ref:
        return None
    return ref, locale if isinstance(locale, str) and locale else "en"


__all__ = [
    "PERSONA_SECTION_NAME",
    "CompanionPersona",
    "LibrarianMemory",
    "frozen_companion",
    "render_story_moment",
]
