"""The companion values the agent freezes into a conversation.

The agent slice does not know how personas or lore are stored. The composition
root resolves them from the companion slice and hands the agent a plain value:
the rendered persona section, which already carries the root-configured rules
that outrank the persona (including the equal-address rule). The agent adds no
story wording of its own.
"""

from dataclasses import dataclass
from typing import Any

PERSONA_SECTION_NAME = "companion_persona"
# The heading the persona section renders under in the frozen system message.
COMPANION_PERSONA_HEADING = "# Companion persona:"


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
            "content": self.content.rstrip(),
        }

    def frozen(self) -> dict[str, str]:
        """Return the identity stored in the system entry's data."""
        return {"ref": self.ref, "name": self.name, "locale": self.locale}


def frozen_speaker(system_data: Any) -> dict[str, str] | None:
    """Return ``{ref, name}`` of the companion frozen in a system entry, or ``None``.

    Stamped on every assistant entry of that conversation as ``data.speaker`` so
    later readers (history search, ``history_message``, ``recall_my_memories``,
    the chat UI) know which librarian said it.
    """
    if not isinstance(system_data, dict):
        return None
    companion = system_data.get("companion")
    if not isinstance(companion, dict):
        return None
    ref = companion.get("ref")
    if not isinstance(ref, str) or not ref:
        return None
    name = companion.get("name")
    return {"ref": ref, "name": name if isinstance(name, str) else ""}


def entry_speaker(data: Any) -> dict[str, str] | None:
    """Return the ``{ref, name}`` speaker stamped on an assistant entry, if any."""
    if not isinstance(data, dict):
        return None
    speaker = data.get("speaker")
    if not isinstance(speaker, dict):
        return None
    ref = speaker.get("ref")
    if not isinstance(ref, str) or not ref:
        return None
    name = speaker.get("name")
    return {"ref": ref, "name": name if isinstance(name, str) else ""}


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
    "COMPANION_PERSONA_HEADING",
    "PERSONA_SECTION_NAME",
    "CompanionPersona",
    "entry_speaker",
    "frozen_companion",
    "frozen_speaker",
]
