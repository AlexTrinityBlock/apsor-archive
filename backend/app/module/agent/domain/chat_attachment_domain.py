"""Pure value objects for temporary chat images.

The transcript stores only an attachment id and display metadata in ``data``.
At provider-call time the service materializes the bytes as OpenAI-compatible
``image_url`` parts. Keeping this projection out of the append-only entry means
deleting a temporary image cannot rewrite transcript history.
"""

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from app.module.agent.domain.agent_domain import KIND_USER, TranscriptEntry

SUPPORTED_CHAT_IMAGE_MIME_TYPES = (
    "image/png",
    "image/jpeg",
    "image/webp",
)
MAX_CHAT_IMAGES_PER_MESSAGE = 4
CHAT_IMAGE_MAX_DIMENSION = 2048


@dataclass(frozen=True)
class ChatAttachmentImage:
    """Display metadata copied into one user entry's ``data`` payload."""

    id: int
    file_name: str
    mime_type: str
    size_bytes: int
    width: int
    height: int

    def to_entry_data(self) -> dict[str, Any]:
        """Return the bounded UI copy persisted on the user entry."""
        return {
            "id": self.id,
            "file_name": self.file_name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class ChatAttachmentImageData:
    """One image ready to be encoded into a provider message."""

    attachment_id: int
    mime_type: str
    data: bytes


def attachment_ids_from_entry(entry: TranscriptEntry) -> tuple[int, ...]:
    """Read the persisted attachment ids from one entry's UI data."""
    if entry.kind != KIND_USER or not isinstance(entry.data, dict):
        return ()
    raw = entry.data.get("attachments")
    if not isinstance(raw, list):
        return ()
    ids: list[int] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        attachment_id = item.get("id")
        if isinstance(attachment_id, int) and attachment_id > 0:
            ids.append(attachment_id)
    return tuple(ids)


def apply_provider_images(
    entries: Sequence[TranscriptEntry],
    images_by_entry: Mapping[int, Sequence[ChatAttachmentImageData]],
    missing_by_entry: Mapping[int, int],
) -> list[TranscriptEntry]:
    """Return entries with their first user message carrying image parts.

    The input is not mutated. An entry whose temporary images were all deleted
    keeps an explicit text note so the model knows something is missing instead
    of silently receiving a text-only turn.
    """
    enriched: list[TranscriptEntry] = []
    for entry in entries:
        images = tuple(images_by_entry.get(entry.id, ()))
        missing = missing_by_entry.get(entry.id, 0)
        if not images and missing == 0:
            enriched.append(entry)
            continue
        messages = [dict(message) for message in entry.messages]
        changed = False
        for message in messages:
            if message.get("role") != "user":
                continue
            content = message.get("content")
            parts: list[dict[str, Any]] = []
            if isinstance(content, str) and content:
                parts.append({"type": "text", "text": content})
            elif isinstance(content, list):
                parts.extend(content)
            for image in images:
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                f"data:{image.mime_type};base64,"
                                f"{base64.b64encode(image.data).decode('ascii')}"
                            )
                        },
                    }
                )
            if missing > 0:
                noun = "image" if missing == 1 else "images"
                parts.append(
                    {
                        "type": "text",
                        "text": (
                            f"[{missing} attached {noun} could not be loaded from "
                            "temporary storage.]"
                        ),
                    }
                )
            message["content"] = parts
            changed = True
            break
        enriched.append(replace(entry, messages=tuple(messages)) if changed else entry)
    return enriched


__all__ = [
    "CHAT_IMAGE_MAX_DIMENSION",
    "MAX_CHAT_IMAGES_PER_MESSAGE",
    "SUPPORTED_CHAT_IMAGE_MIME_TYPES",
    "ChatAttachmentImage",
    "ChatAttachmentImageData",
    "apply_provider_images",
    "attachment_ids_from_entry",
]
