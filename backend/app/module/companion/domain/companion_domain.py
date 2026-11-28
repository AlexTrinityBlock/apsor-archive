"""Pure rules for custom chat companions and the per-account preference."""

import re
from dataclasses import dataclass
from typing import Literal

from app.shared.companion_action import COMPANION_ACTIONS

CompanionGender = Literal["female", "male", "other"]
CompanionMotion = Literal["full", "reduced", "off"]
CompanionSize = Literal["compact", "medium", "full"]
CompanionOpacityMode = Literal["opaque", "translucent", "auto"]

COMPANION_GENDERS: tuple[str, ...] = ("female", "male", "other")
COMPANION_MOTIONS: tuple[str, ...] = ("full", "reduced", "off")

MAX_COMPANIONS_PER_ACCOUNT = 20
MAX_FRAMES_PER_ACTION = 12
MAX_FILES_PER_UPLOAD = 12
MAX_FRAME_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000
FRAME_MAX_WIDTH = 384
FRAME_MAX_HEIGHT = 576
FRAME_MAX_ENCODED_BYTES = 40 * 1024
FRAME_MIME_TYPES: tuple[str, ...] = ("image/avif", "image/webp")
_FRAME_EXTENSIONS = {"image/avif": ".avif", "image/webp": ".webp"}
NAME_MAX_CHARS = 40

# A preset id names a directory under ``frontend/public/companions``. The server
# does not know the preset catalog; it only keeps the reference well formed.
_PRESET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SELECTION_MAX_CHARS = 64


@dataclass(frozen=True)
class CompanionSelection:
    """A parsed ``preset:<id>`` or ``custom:<id>`` reference."""

    kind: Literal["preset", "custom"]
    preset_id: str | None = None
    companion_id: int | None = None

    def serialize(self) -> str:
        """Return the stored, client-facing reference string."""
        if self.kind == "preset":
            return f"preset:{self.preset_id}"
        return f"custom:{self.companion_id}"


def parse_selection(value: str) -> CompanionSelection | None:
    """Parse a selection reference; return ``None`` when it is malformed."""
    if len(value) > SELECTION_MAX_CHARS:
        return None
    kind, separator, reference = value.partition(":")
    if not separator:
        return None
    if kind == "preset" and _PRESET_PATTERN.fullmatch(reference):
        return CompanionSelection(kind="preset", preset_id=reference)
    if kind == "custom" and reference.isascii() and reference.isdigit():
        companion_id = int(reference)
        if 0 < companion_id < 2**63:
            return CompanionSelection(kind="custom", companion_id=companion_id)
    return None


def is_companion_action(value: str) -> bool:
    """Return whether ``value`` is one of the stable action ids."""
    return value in COMPANION_ACTIONS


def size_for_scale(scale: float) -> CompanionSize:
    """Map a continuous display scale (0 compact .. 1 full) to its nearest preset."""
    if scale < 0.25:
        return "compact"
    if scale < 0.75:
        return "medium"
    return "full"


def normalize_scale(scale: float) -> float:
    """Clamp a display scale to 0..1 and round it to three decimal places."""
    return round(min(1.0, max(0.0, scale)), 3)


def frame_version(sha256: str) -> str:
    """Return the short, cache-busting version of one immutable frame."""
    return sha256[:16]


def frame_storage_key(user_id: int, companion_id: int, token: str, mime_type: str) -> str:
    """Return the owner-prefixed object key for one encoded frame."""
    return f"users/{user_id}/companions/{companion_id}/{token}{_FRAME_EXTENSIONS[mime_type]}"


__all__ = [
    "COMPANION_GENDERS",
    "COMPANION_MOTIONS",
    "FRAME_MAX_ENCODED_BYTES",
    "FRAME_MAX_HEIGHT",
    "FRAME_MAX_WIDTH",
    "FRAME_MIME_TYPES",
    "MAX_COMPANIONS_PER_ACCOUNT",
    "MAX_FILES_PER_UPLOAD",
    "MAX_FRAMES_PER_ACTION",
    "MAX_FRAME_UPLOAD_BYTES",
    "MAX_SOURCE_PIXELS",
    "NAME_MAX_CHARS",
    "SELECTION_MAX_CHARS",
    "CompanionGender",
    "CompanionMotion",
    "CompanionOpacityMode",
    "CompanionSelection",
    "CompanionSize",
    "frame_storage_key",
    "frame_version",
    "is_companion_action",
    "normalize_scale",
    "parse_selection",
    "size_for_scale",
]
