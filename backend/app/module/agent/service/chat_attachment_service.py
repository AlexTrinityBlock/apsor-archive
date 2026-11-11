"""Temporary chat images: upload, management, and provider materialization."""

import asyncio
import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from app.infrastructure.files.storage_errors import (
    StorageError,
    StorageObjectMissingError,
)
from app.module.agent.domain.agent_domain import TranscriptEntry
from app.module.agent.domain.chat_attachment_domain import (
    CHAT_IMAGE_MAX_DIMENSION,
    MAX_CHAT_IMAGES_PER_MESSAGE,
    SUPPORTED_CHAT_IMAGE_MIME_TYPES,
    ChatAttachmentImage,
    ChatAttachmentImageData,
    apply_provider_images,
    attachment_ids_from_entry,
)
from app.module.agent.exception.domain_error import (
    AgentChatAttachmentInvalidError,
    AgentChatAttachmentLimitError,
    AgentChatAttachmentNotFoundError,
    AgentChatAttachmentStorageError,
    AgentChatAttachmentTooLargeError,
    AgentChatAttachmentUnsupportedError,
)
from app.module.agent.model.agent_model import AgentChatAttachmentModel
from app.module.agent.protocol.chat_attachment_repository_protocol import (
    ChatAttachmentRepositoryProtocol,
)
from app.module.agent.protocol.chat_attachment_storage_protocol import (
    ChatAttachmentStorageProtocol,
)
from app.module.agent.schema.chat_attachment_schema import (
    AgentChatAttachmentSchema,
    AgentChatAttachmentStatus,
)
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

_FORMAT_MIME = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
_MIME_SUFFIX = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
_PNG_MODES = frozenset({"RGB", "RGBA", "L", "LA"})
_CONTENT_URL_PREFIX = "/api/v1/agent/attachments"
_MAX_SOURCE_PIXELS = 40_000_000


@dataclass(frozen=True)
class ChatAttachmentContent:
    """One stored image ready for an authenticated response."""

    data: bytes
    file_name: str
    mime_type: str


@dataclass(frozen=True)
class _ProcessedImage:
    data: bytes
    mime_type: str
    width: int
    height: int


class ChatAttachmentService:
    """Own one account's temporary chat images.

    The service is used both by request-scoped management routes and by the
    agent turn loop. It therefore depends only on protocols and never holds a
    request database session.
    """

    def __init__(
        self,
        *,
        repository: ChatAttachmentRepositoryProtocol,
        storage: ChatAttachmentStorageProtocol,
        max_upload_bytes: int,
        max_per_message: int = MAX_CHAT_IMAGES_PER_MESSAGE,
        user_id: int,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.max_upload_bytes = max_upload_bytes
        self.max_per_message = max_per_message
        self.user_id = user_id

    async def upload(
        self,
        *,
        data: bytes,
        file_name: str | None,
        content_type: str | None,
    ) -> AgentChatAttachmentSchema:
        """Validate, sanitize, and store one pasted image."""
        del content_type  # The bytes are verified and re-encoded, not trusted.
        if not data:
            raise AgentChatAttachmentUnsupportedError()
        if len(data) > self.max_upload_bytes:
            raise AgentChatAttachmentTooLargeError(len(data), self.max_upload_bytes)

        processed = await asyncio.to_thread(_process_image, data)
        if len(processed.data) > self.max_upload_bytes:
            raise AgentChatAttachmentTooLargeError(
                len(processed.data),
                self.max_upload_bytes,
            )
        suffix = _MIME_SUFFIX[processed.mime_type]
        safe_name = _safe_file_name(file_name, suffix)
        storage_key = f"users/{self.user_id}/chat-temp/{uuid4().hex}{suffix}"
        created_at = utcnow()
        try:
            await self.storage.save(storage_key, processed.data)
        except (StorageError, OSError) as exc:
            logger.warning(
                "chat attachment upload failed at storage user_id=%s reason=%s",
                self.user_id,
                type(exc).__name__,
            )
            raise AgentChatAttachmentStorageError() from exc

        try:
            row = await self.repository.add(
                storage_key=storage_key,
                storage_backend=self.storage.default_backend,
                file_name=safe_name,
                mime_type=processed.mime_type,
                size_bytes=len(processed.data),
                width=processed.width,
                height=processed.height,
                content_hash=hashlib.sha256(processed.data).hexdigest(),
                created_at=created_at,
            )
        except Exception:
            await self._delete_quietly(storage_key, self.storage.default_backend)
            raise
        return _attachment_schema(row)

    async def list_images(
        self,
        *,
        status: AgentChatAttachmentStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AgentChatAttachmentSchema], int]:
        """Return one page of temporary images and the account-wide total."""
        rows, total = await self.repository.page(
            status=status,
            limit=limit,
            offset=offset,
        )
        return [_attachment_schema(row) for row in rows], total

    async def delete(self, attachment_id: int) -> None:
        """Remove the object, then soft-delete its row."""
        row = await self._require_row(attachment_id)
        try:
            await self.storage.delete(
                row.storage_key,
                backend=row.storage_backend,
            )
        except (StorageObjectMissingError, FileNotFoundError):
            pass
        except (StorageError, OSError) as exc:
            raise AgentChatAttachmentStorageError() from exc
        if not await self.repository.mark_deleted(attachment_id, now=utcnow()):
            raise AgentChatAttachmentNotFoundError(attachment_id)

    async def content(self, attachment_id: int) -> ChatAttachmentContent:
        """Read one live image for an authenticated content response."""
        row = await self._require_row(attachment_id)
        try:
            data = await self.storage.read(
                row.storage_key,
                backend=row.storage_backend,
            )
        except (StorageObjectMissingError, FileNotFoundError) as exc:
            raise AgentChatAttachmentNotFoundError(attachment_id) from exc
        except (StorageError, OSError) as exc:
            raise AgentChatAttachmentStorageError() from exc
        return ChatAttachmentContent(
            data=data,
            file_name=row.file_name,
            mime_type=row.mime_type,
        )

    async def prepare_for_message(
        self,
        attachment_ids: Sequence[int],
    ) -> list[ChatAttachmentImage]:
        """Validate staged ids and return metadata for the user entry."""
        ordered = list(dict.fromkeys(attachment_ids))
        if len(ordered) != len(attachment_ids):
            raise AgentChatAttachmentInvalidError()
        if len(ordered) > self.max_per_message:
            raise AgentChatAttachmentLimitError(self.max_per_message)

        images: list[ChatAttachmentImage] = []
        for attachment_id in ordered:
            row = await self.repository.get(attachment_id)
            if row is None or row.entry_id is not None or row.deleted_at is not None:
                raise AgentChatAttachmentInvalidError()
            images.append(_attachment_image(row))
        return images

    async def enrich_transcript(
        self,
        entries: Sequence[TranscriptEntry],
    ) -> list[TranscriptEntry]:
        """Materialize linked temporary images as provider content parts.

        A missing object or an unavailable storage backend is represented as an
        explicit note instead of failing the whole turn. Management operations
        still surface a storage error, but a temp image must never make an
        otherwise valid chat request impossible to answer.
        """
        attachment_ids = {
            attachment_id
            for entry in entries
            for attachment_id in attachment_ids_from_entry(entry)
        }
        if not attachment_ids:
            return list(entries)

        rows = await self.repository.list_by_ids(sorted(attachment_ids))
        rows_by_id = {row.id: row for row in rows}
        loaded: dict[int, bytes] = {}
        if rows:
            results = await asyncio.gather(
                *(self._read_quietly(row) for row in rows)
            )
            loaded = {row_id: data for row_id, data in results if data is not None}

        images_by_entry: dict[int, list[ChatAttachmentImageData]] = {}
        missing_by_entry: dict[int, int] = {}
        for entry in entries:
            entry_ids = attachment_ids_from_entry(entry)
            if not entry_ids:
                continue
            images: list[ChatAttachmentImageData] = []
            missing = 0
            for attachment_id in entry_ids:
                row = rows_by_id.get(attachment_id)
                data = loaded.get(attachment_id) if row is not None else None
                if row is None or data is None:
                    missing += 1
                    continue
                images.append(
                    ChatAttachmentImageData(
                        attachment_id=row.id,
                        mime_type=row.mime_type,
                        data=data,
                    )
                )
            if images:
                images_by_entry[entry.id] = images
            if missing:
                missing_by_entry[entry.id] = missing
        return apply_provider_images(entries, images_by_entry, missing_by_entry)

    async def _read_quietly(
        self,
        row: AgentChatAttachmentModel,
    ) -> tuple[int, bytes | None]:
        try:
            data = await self.storage.read(
                row.storage_key,
                backend=row.storage_backend,
            )
        except (StorageError, OSError) as exc:
            logger.warning(
                "chat attachment read failed attachment_id=%s reason=%s",
                row.id,
                type(exc).__name__,
            )
            return row.id, None
        return row.id, data

    async def _require_row(self, attachment_id: int) -> AgentChatAttachmentModel:
        row = await self.repository.get(attachment_id)
        if row is None or row.deleted_at is not None:
            raise AgentChatAttachmentNotFoundError(attachment_id)
        return row

    async def _delete_quietly(self, storage_key: str, backend: str) -> None:
        try:
            await self.storage.delete(storage_key, backend=backend)
        except (StorageError, OSError):
            logger.warning(
                "chat attachment cleanup failed user_id=%s",
                self.user_id,
            )


def _attachment_schema(row: AgentChatAttachmentModel) -> AgentChatAttachmentSchema:
    status: AgentChatAttachmentStatus = "attached" if row.entry_id is not None else "staged"
    return AgentChatAttachmentSchema(
        id=row.id,
        file_name=row.file_name,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        width=row.width,
        height=row.height,
        status=status,
        conversation_id=row.conversation_id,
        entry_id=row.entry_id,
        created_at=row.created_at,
        content_url=f"{_CONTENT_URL_PREFIX}/{row.id}/content",
    )


def _attachment_image(row: AgentChatAttachmentModel) -> ChatAttachmentImage:
    return ChatAttachmentImage(
        id=row.id,
        file_name=row.file_name,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        width=row.width,
        height=row.height,
    )


def _safe_file_name(raw: str | None, suffix: str) -> str:
    """Keep only a basename and bound the stored display name."""
    candidate = (raw or "").replace("\x00", "").replace("\\", "/")
    candidate = candidate.rsplit("/", 1)[-1].strip()
    if not candidate:
        candidate = f"pasted-image{suffix}"
    return candidate[:255]


def _process_image(data: bytes) -> _ProcessedImage:
    """Verify, orient, downscale, and re-encode one image.

    Re-encoding strips EXIF and other opaque metadata from a pasted screenshot.
    The output format is limited to the three MIME types the vision providers
    accept, so a client-supplied content type is never trusted.
    """
    try:
        with Image.open(BytesIO(data)) as opened:
            image_format = (opened.format or "").upper()
            mime_type = _FORMAT_MIME.get(image_format)
            if mime_type is None:
                raise AgentChatAttachmentUnsupportedError()
            if getattr(opened, "is_animated", False):
                raise AgentChatAttachmentUnsupportedError()
            source_width, source_height = opened.size
            if source_width * source_height > _MAX_SOURCE_PIXELS:
                raise AgentChatAttachmentUnsupportedError()
            opened.load()
            oriented = ImageOps.exif_transpose(opened)
            oriented.thumbnail(
                (CHAT_IMAGE_MAX_DIMENSION, CHAT_IMAGE_MAX_DIMENSION),
                Image.Resampling.LANCZOS,
            )
            width, height = oriented.size
            encoded = _encode_image(oriented, image_format)
    except AgentChatAttachmentUnsupportedError:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise AgentChatAttachmentUnsupportedError() from exc
    if not encoded:
        raise AgentChatAttachmentUnsupportedError()
    return _ProcessedImage(
        data=encoded,
        mime_type=mime_type,
        width=width,
        height=height,
    )


def _encode_image(image: Image.Image, image_format: str) -> bytes:
    output = BytesIO()
    if image_format == "JPEG":
        image.convert("RGB").save(
            output,
            format="JPEG",
            quality=90,
            optimize=True,
            progressive=True,
        )
    elif image_format == "WEBP":
        image.save(output, format="WEBP", quality=90, method=4)
    else:
        if image.mode not in _PNG_MODES:
            image = image.convert("RGBA")
        image.save(output, format="PNG", optimize=True)
    return output.getvalue()


__all__ = [
    "SUPPORTED_CHAT_IMAGE_MIME_TYPES",
    "ChatAttachmentContent",
    "ChatAttachmentService",
]
