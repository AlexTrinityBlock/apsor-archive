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
# A user entry that hands the conversation to another companion (or to the plain
# archive assistant) carries ``data[COMPANION_SWITCH_KEY] = {ref, name, locale}``
# (``ref`` is ``None`` for the archive assistant) and the rendered handoff text
# under ``data[COMPANION_HANDOFF_KEY]``, which the context builder appends to that
# user message only. The frozen system entry never changes.
COMPANION_SWITCH_KEY = "companion_switch"
COMPANION_HANDOFF_KEY = "companion_handoff"
ARCHIVE_ASSISTANT_NAME = "the archive assistant"
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


def entry_switch(data: Any) -> tuple[bool, dict[str, str] | None]:
    """Return ``(is_switch, companion)`` for a user entry's handoff record.

    ``companion`` is ``{ref, name, locale}`` or ``None`` when the conversation was
    handed to the plain archive assistant.
    """
    if not isinstance(data, dict):
        return False, None
    switch = data.get(COMPANION_SWITCH_KEY)
    if not isinstance(switch, dict):
        return False, None
    ref = switch.get("ref")
    if not isinstance(ref, str) or not ref:
        return True, None
    name = switch.get("name")
    locale = switch.get("locale")
    return True, {
        "ref": ref,
        "name": name if isinstance(name, str) else "",
        "locale": locale if isinstance(locale, str) and locale else "en",
    }


def current_companion(
    system_data: Any,
    latest_switch_data: Any = None,
) -> dict[str, str] | None:
    """Return ``{ref, name, locale}`` of whoever speaks now, or ``None``.

    The latest handoff wins; without one, the companion frozen at creation.
    """
    is_switch, switched = entry_switch(latest_switch_data)
    if is_switch:
        return switched
    frozen = frozen_companion(system_data)
    speaker = frozen_speaker(system_data)
    if frozen is None or speaker is None:
        return None
    return {"ref": frozen[0], "name": speaker["name"], "locale": frozen[1]}


def switch_record(companion: "CompanionPersona | None") -> dict[str, str | None]:
    """Return the handoff record stored on the user entry."""
    if companion is None:
        return {"ref": None, "name": ARCHIVE_ASSISTANT_NAME, "locale": None}
    return {"ref": companion.ref, "name": companion.name, "locale": companion.locale}


def render_handoff(new: "CompanionPersona | None", previous_name: str | None) -> str:
    """Render the provider-only handoff appended to the switching user message."""
    before = previous_name or ARCHIVE_ASSISTANT_NAME
    if new is None:
        body = (
            "From here on you answer as the archive assistant, without any companion "
            f"persona. Earlier assistant replies in this conversation were said by {before} "
            "(and others as labeled); they are not your own words, and that persona no "
            "longer applies. Labels like [said by …] only mark who said earlier "
            "replies; never write such a label yourself."
        )
        return f"<companion_handoff>\n{body}\n</companion_handoff>"
    body = (
        f"From here on you are {new.name}. Earlier assistant replies in this conversation "
        f"were said by {before} (and others as labeled); they are not your own words. "
        "The persona below replaces any companion persona in the system message. "
        "Labels like [said by …] only mark who said earlier replies; never write "
        "such a label yourself."
    )
    return (
        f"<companion_handoff>\n{body}\n\n{new.content.rstrip()}\n</companion_handoff>"
    )


__all__ = [
    "ARCHIVE_ASSISTANT_NAME",
    "COMPANION_HANDOFF_KEY",
    "COMPANION_PERSONA_HEADING",
    "COMPANION_SWITCH_KEY",
    "PERSONA_SECTION_NAME",
    "CompanionPersona",
    "current_companion",
    "entry_speaker",
    "entry_switch",
    "frozen_companion",
    "frozen_speaker",
    "render_handoff",
    "switch_record",
]
