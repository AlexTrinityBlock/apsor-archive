"""Ports the companion service depends on."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.module.companion.model.companion_model import (
    CompanionFrameModel,
    CompanionModel,
    CompanionPreferenceModel,
)


class CompanionStorageProtocol(Protocol):
    """Persist, retrieve, and delete opaque bytes on a selectable backend."""

    @property
    def default_backend(self) -> str: ...

    async def save(self, key: str, data: bytes, *, backend: str | None = None) -> str: ...

    async def read(self, key: str, *, backend: str | None = None) -> bytes: ...

    async def delete(self, key: str, *, backend: str | None = None) -> None: ...


class CompanionRepositoryProtocol(Protocol):
    """Owner-scoped persistence on the request transaction."""

    async def list_companions(self, user_id: int) -> list[CompanionModel]: ...

    async def count_companions(self, user_id: int) -> int: ...

    async def get_companion(
        self,
        user_id: int,
        companion_id: int,
    ) -> CompanionModel | None: ...

    async def add_companion(
        self,
        *,
        user_id: int,
        name: str,
        gender: str | None,
        now: datetime,
    ) -> CompanionModel: ...

    async def touch_companion(self, companion: CompanionModel, now: datetime) -> None: ...

    async def delete_companion(self, companion: CompanionModel) -> None: ...

    async def list_frames(
        self,
        user_id: int,
        companion_ids: Sequence[int],
    ) -> list[CompanionFrameModel]: ...

    async def get_frame(
        self,
        user_id: int,
        companion_id: int,
        frame_id: int,
    ) -> CompanionFrameModel | None: ...

    async def add_frame(
        self,
        *,
        user_id: int,
        companion_id: int,
        action: str,
        position: int,
        storage_backend: str,
        storage_key: str,
        mime_type: str,
        width: int,
        height: int,
        size_bytes: int,
        sha256: str,
        now: datetime,
    ) -> CompanionFrameModel: ...

    async def delete_frame(self, frame: CompanionFrameModel) -> None: ...

    async def flush(self) -> None: ...

    async def get_preference(self, user_id: int) -> CompanionPreferenceModel | None: ...

    async def upsert_preference(
        self,
        *,
        user_id: int,
        selected: str | None,
        enabled: bool,
        motion: str,
        size: str,
        scale: float | None,
        opacity_mode: str,
        position_x: float | None,
        position_y: float | None,
        now: datetime,
    ) -> CompanionPreferenceModel: ...

    async def clear_selection(self, user_id: int, selected: str, now: datetime) -> None: ...


__all__ = ["CompanionRepositoryProtocol", "CompanionStorageProtocol"]
