"""Custom companions: CRUD, frame uploads, frame order, and the preference."""

import asyncio
import hashlib
import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

from app.infrastructure.files.storage_errors import StorageError, StorageObjectMissingError
from app.module.companion.domain.companion_domain import (
    MAX_COMPANIONS_PER_ACCOUNT,
    MAX_FILES_PER_UPLOAD,
    MAX_FRAME_UPLOAD_BYTES,
    MAX_FRAMES_PER_ACTION,
    CompanionSelection,
    frame_storage_key,
    frame_version,
    parse_selection,
)
from app.module.companion.exception.domain_error import (
    CompanionFrameLimitError,
    CompanionFrameNotFoundError,
    CompanionFrameTooLargeError,
    CompanionFrameUnsupportedError,
    CompanionInvalidError,
    CompanionLimitError,
    CompanionNotFoundError,
    CompanionStorageError,
)
from app.module.companion.model.companion_model import (
    CompanionFrameModel,
    CompanionModel,
    CompanionPreferenceModel,
)
from app.module.companion.protocol.companion_protocol import (
    CompanionRepositoryProtocol,
    CompanionStorageProtocol,
)
from app.module.companion.schema.companion_schema import (
    CompanionCreateSchema,
    CompanionFrameOrderSchema,
    CompanionFrameSchema,
    CompanionPositionSchema,
    CompanionPreferenceSchema,
    CompanionPreferenceUpdateSchema,
    CompanionSchema,
    CompanionUpdateSchema,
)
from app.module.companion.service.companion_frame_image import EncodedFrame, encode_frame
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1/companions"


@dataclass(frozen=True)
class FrameUpload:
    """One uploaded file as read from the request (size-capped by the router)."""

    data: bytes


@dataclass(frozen=True)
class FrameMeta:
    """One frame's immutable cache identity."""

    etag: str
    version: str


@dataclass(frozen=True)
class FrameImage:
    """One stored frame's bytes and cache metadata."""

    data: bytes
    meta: FrameMeta


class CompanionService:
    """Owner-scoped companion workflows on the request transaction.

    Object bytes are written before the rows and removed again when a later
    step fails, so a failed upload never leaves a row pointing at nothing.
    Deleting rows removes their objects afterwards on a best-effort basis.
    """

    def __init__(
        self,
        *,
        repository: CompanionRepositoryProtocol,
        storage: CompanionStorageProtocol,
        user_id: int,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.user_id = user_id

    async def list_companions(self) -> list[CompanionSchema]:
        companions = await self.repository.list_companions(self.user_id)
        frames = await self.repository.list_frames(
            self.user_id,
            [companion.id for companion in companions],
        )
        grouped: dict[int, list[CompanionFrameModel]] = defaultdict(list)
        for frame in frames:
            grouped[frame.companion_id].append(frame)
        return [_companion_schema(companion, grouped[companion.id]) for companion in companions]

    async def create_companion(self, payload: CompanionCreateSchema) -> CompanionSchema:
        if await self.repository.count_companions(self.user_id) >= MAX_COMPANIONS_PER_ACCOUNT:
            raise CompanionLimitError(MAX_COMPANIONS_PER_ACCOUNT)
        companion = await self.repository.add_companion(
            user_id=self.user_id,
            name=payload.name,
            gender=payload.gender,
            now=utcnow(),
        )
        return _companion_schema(companion, [])

    async def update_companion(
        self,
        companion_id: int,
        payload: CompanionUpdateSchema,
    ) -> CompanionSchema:
        companion = await self._require_companion(companion_id)
        if "name" in payload.model_fields_set and payload.name is not None:
            companion.name = payload.name
        if "gender" in payload.model_fields_set:
            companion.gender = payload.gender
        await self.repository.touch_companion(companion, utcnow())
        return await self._read(companion)

    async def delete_companion(self, companion_id: int) -> None:
        companion = await self._require_companion(companion_id)
        frames = await self.repository.list_frames(self.user_id, [companion.id])
        objects = [(frame.storage_key, frame.storage_backend) for frame in frames]
        await self.repository.delete_companion(companion)
        await self.repository.clear_selection(
            self.user_id,
            CompanionSelection(kind="custom", companion_id=companion_id).serialize(),
            utcnow(),
        )
        await self._delete_objects(objects)

    async def upload_frames(
        self,
        companion_id: int,
        action: str,
        uploads: Sequence[FrameUpload],
    ) -> CompanionSchema:
        companion = await self._require_companion(companion_id)
        if not uploads:
            raise CompanionInvalidError("Upload at least one image.")
        if len(uploads) > MAX_FILES_PER_UPLOAD:
            raise CompanionFrameLimitError(MAX_FRAMES_PER_ACTION)
        for upload in uploads:
            if not upload.data:
                raise CompanionFrameUnsupportedError()
            if len(upload.data) > MAX_FRAME_UPLOAD_BYTES:
                raise CompanionFrameTooLargeError(MAX_FRAME_UPLOAD_BYTES)

        existing = [
            frame
            for frame in await self.repository.list_frames(self.user_id, [companion.id])
            if frame.action == action
        ]
        if len(existing) + len(uploads) > MAX_FRAMES_PER_ACTION:
            raise CompanionFrameLimitError(MAX_FRAMES_PER_ACTION)

        encoded: list[EncodedFrame] = []
        for upload in uploads:
            encoded.append(await asyncio.to_thread(encode_frame, upload.data))

        backend = self.storage.default_backend
        saved: list[tuple[str, str]] = []
        try:
            next_position = max((frame.position for frame in existing), default=-1) + 1
            now = utcnow()
            for offset, frame in enumerate(encoded):
                key = frame_storage_key(self.user_id, companion.id, uuid4().hex)
                try:
                    await self.storage.save(key, frame.data)
                except (StorageError, OSError) as exc:
                    logger.warning(
                        "companion frame upload failed at storage user_id=%s reason=%s",
                        self.user_id,
                        type(exc).__name__,
                    )
                    raise CompanionStorageError() from exc
                saved.append((key, backend))
                await self.repository.add_frame(
                    user_id=self.user_id,
                    companion_id=companion.id,
                    action=action,
                    position=next_position + offset,
                    storage_backend=backend,
                    storage_key=key,
                    width=frame.width,
                    height=frame.height,
                    size_bytes=len(frame.data),
                    sha256=hashlib.sha256(frame.data).hexdigest(),
                    now=now,
                )
            await self.repository.touch_companion(companion, now)
        except BaseException:
            await self._delete_objects(saved)
            raise
        return await self._read(companion)

    async def delete_frame(self, companion_id: int, frame_id: int) -> None:
        companion = await self._require_companion(companion_id)
        frame = await self.repository.get_frame(self.user_id, companion.id, frame_id)
        if frame is None:
            raise CompanionFrameNotFoundError(frame_id)
        action = frame.action
        storage = (frame.storage_key, frame.storage_backend)
        await self.repository.delete_frame(frame)
        remaining = [
            item
            for item in await self.repository.list_frames(self.user_id, [companion.id])
            if item.action == action
        ]
        for position, item in enumerate(remaining):
            item.position = position
        await self.repository.touch_companion(companion, utcnow())
        await self._delete_objects([storage])

    async def reorder_frames(
        self,
        companion_id: int,
        payload: CompanionFrameOrderSchema,
    ) -> CompanionSchema:
        companion = await self._require_companion(companion_id)
        frames = {
            frame.id: frame
            for frame in await self.repository.list_frames(self.user_id, [companion.id])
            if frame.action == payload.action
        }
        if set(payload.frame_ids) != set(frames):
            raise CompanionInvalidError(
                "frame_ids must list every frame of the action exactly once."
            )
        for position, frame_id in enumerate(payload.frame_ids):
            frames[frame_id].position = position
        await self.repository.touch_companion(companion, utcnow())
        return await self._read(companion)

    async def frame_image(self, companion_id: int, frame_id: int) -> FrameImage:
        frame = await self.repository.get_frame(self.user_id, companion_id, frame_id)
        if frame is None:
            raise CompanionFrameNotFoundError(frame_id)
        try:
            data = await self.storage.read(frame.storage_key, backend=frame.storage_backend)
        except StorageObjectMissingError as exc:
            raise CompanionFrameNotFoundError(frame_id) from exc
        except (StorageError, OSError) as exc:
            raise CompanionStorageError() from exc
        return FrameImage(data=data, meta=_frame_meta(frame))

    async def frame_meta(self, companion_id: int, frame_id: int) -> FrameMeta:
        """Return the frame's cache identity without reading its bytes."""
        frame = await self.repository.get_frame(self.user_id, companion_id, frame_id)
        if frame is None:
            raise CompanionFrameNotFoundError(frame_id)
        return _frame_meta(frame)

    async def get_preference(self) -> CompanionPreferenceSchema:
        preference = await self.repository.get_preference(self.user_id)
        return await self._preference_schema(preference)

    async def update_preference(
        self,
        payload: CompanionPreferenceUpdateSchema,
    ) -> CompanionPreferenceSchema:
        current = await self.repository.get_preference(self.user_id)
        fields = payload.model_fields_set
        selected = current.selected if current is not None else None
        enabled = current.enabled if current is not None else True
        motion = current.motion if current is not None else "full"
        position_x = current.position_x if current is not None else None
        position_y = current.position_y if current is not None else None

        if "selected" in fields:
            selected = payload.selected
            if selected is not None:
                await self._require_selectable(selected)
        if "enabled" in fields and payload.enabled is not None:
            enabled = payload.enabled
        if "motion" in fields and payload.motion is not None:
            motion = payload.motion
        if "position" in fields:
            position_x = payload.position.x if payload.position is not None else None
            position_y = payload.position.y if payload.position is not None else None

        preference = await self.repository.upsert_preference(
            user_id=self.user_id,
            selected=selected,
            enabled=enabled,
            motion=motion,
            position_x=position_x,
            position_y=position_y,
            now=utcnow(),
        )
        return await self._preference_schema(preference)

    async def _preference_schema(
        self,
        preference: CompanionPreferenceModel | None,
    ) -> CompanionPreferenceSchema:
        if preference is None:
            return CompanionPreferenceSchema(
                selected=None,
                enabled=True,
                motion="full",
                position=None,
                updated_at=None,
            )
        selected = preference.selected
        if selected is not None and not await self._is_selectable(selected):
            # A custom companion that no longer exists falls back to the default.
            selected = None
        position = (
            CompanionPositionSchema(x=preference.position_x, y=preference.position_y)
            if preference.position_x is not None and preference.position_y is not None
            else None
        )
        return CompanionPreferenceSchema(
            selected=selected,
            enabled=preference.enabled,
            motion=preference.motion,  # type: ignore[arg-type]
            position=position,
            updated_at=preference.updated_at,
        )

    async def _require_selectable(self, selected: str) -> None:
        if not await self._is_selectable(selected):
            raise CompanionInvalidError("The selected companion does not exist.")

    async def _is_selectable(self, selected: str) -> bool:
        parsed = parse_selection(selected)
        if parsed is None:
            return False
        if parsed.kind == "preset" or parsed.companion_id is None:
            return parsed.kind == "preset"
        return await self.repository.get_companion(self.user_id, parsed.companion_id) is not None

    async def _require_companion(self, companion_id: int) -> CompanionModel:
        companion = await self.repository.get_companion(self.user_id, companion_id)
        if companion is None:
            raise CompanionNotFoundError(companion_id)
        return companion

    async def _read(self, companion: CompanionModel) -> CompanionSchema:
        await self.repository.flush()
        frames = await self.repository.list_frames(self.user_id, [companion.id])
        return _companion_schema(companion, frames)

    async def _delete_objects(self, objects: Sequence[tuple[str, str]]) -> None:
        for key, backend in objects:
            try:
                await self.storage.delete(key, backend=backend)
            except (StorageError, OSError) as exc:
                logger.warning(
                    "companion frame object cleanup failed user_id=%s reason=%s",
                    self.user_id,
                    type(exc).__name__,
                )


def _frame_meta(frame: CompanionFrameModel) -> FrameMeta:
    return FrameMeta(etag=frame.sha256, version=frame_version(frame.sha256))


def _frame_schema(frame: CompanionFrameModel) -> CompanionFrameSchema:
    version = frame_version(frame.sha256)
    return CompanionFrameSchema(
        id=frame.id,
        action=frame.action,  # type: ignore[arg-type]
        position=frame.position,
        width=frame.width,
        height=frame.height,
        size_bytes=frame.size_bytes,
        version=version,
        url=f"{API_PREFIX}/{frame.companion_id}/frames/{frame.id}/image?v={version}",
    )


def _companion_schema(
    companion: CompanionModel,
    frames: Sequence[CompanionFrameModel],
) -> CompanionSchema:
    ordered = sorted(frames, key=lambda frame: (frame.action, frame.position, frame.id))
    return CompanionSchema(
        id=companion.id,
        name=companion.name,
        gender=companion.gender,  # type: ignore[arg-type]
        frames=[_frame_schema(frame) for frame in ordered],
        created_at=companion.created_at,
        updated_at=companion.updated_at,
    )


__all__ = ["CompanionService", "FrameImage", "FrameMeta", "FrameUpload"]
