"""The chat companion's stable action vocabulary.

Two slices share these ids: the agent's ``companion_action`` tool validates the
gesture the model asks for, and the companion slice stores uploaded frames per
action. The browser's state machine and the preset manifests use the same ids,
so they are part of the public contract and must not be renamed.
"""

from typing import Literal, get_args

CompanionAction = Literal[
    "idle",
    "greet",
    "listening",
    "thinking",
    "searching",
    "reading",
    "writing",
    "calculating",
    "browsing",
    "presenting",
    "speaking",
    "waiting",
    "success",
    "confused",
    "sleeping",
    "held",
]

COMPANION_ACTIONS: tuple[str, ...] = get_args(CompanionAction)

__all__ = ["COMPANION_ACTIONS", "CompanionAction"]
