"""SQLAlchemy persistence for one owner's file thumbnails.

Every statement carries ``user_id = :user_id``; row-level security is the
defense-in-depth layer, not the only filter.
"""

from collections.abc import Sequence

from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.module.knowledge.model.file_model import FileModel
from app.module.knowledge.model.file_thumbnail_model import (
    THUMBNAIL_STATUS_FAILED,
    THUMBNAIL_STATUS_READY,
    FileThumbnailModel,
)
from app.module.knowledge.protocol.file_thumbnail_repository_protocol import (
    ThumbnailBytes,
    ThumbnailMeta,
)
from app.shared.time import utcnow


class FileThumbnailRepository:
    """Queries over one owner's ``file_thumbnail`` rows."""

    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def upsert(
        self,
        *,
        file_id: int,
        status: str,
        data: bytes | None,
        width: int | None,
        height: int | None,
        sha256: str | None,
        generator_version: int,
        error_code: str | None,
    ) -> None:
        """Insert or replace the row; a repeated failure increments ``attempts``."""
        now = utcnow()
        statement = insert(FileThumbnailModel).values(
            file_id=file_id,
            user_id=self.user_id,
            status=status,
            data=data,
            width=width,
            height=height,
            sha256=sha256,
            generator_version=generator_version,
            error_code=error_code,
            attempts=1,
            created_at=now,
            updated_at=now,
        )
        excluded = statement.excluded
        attempts = (
            FileThumbnailModel.attempts + 1
            if status == THUMBNAIL_STATUS_FAILED
            else literal(1)
        )
        statement = statement.on_conflict_do_update(
            index_elements=[FileThumbnailModel.file_id],
            set_={
                "status": excluded.status,
                "data": excluded.data,
                "width": excluded.width,
                "height": excluded.height,
                "sha256": excluded.sha256,
                "generator_version": excluded.generator_version,
                "error_code": excluded.error_code,
                "attempts": attempts,
                "updated_at": excluded.updated_at,
            },
            where=FileThumbnailModel.user_id == self.user_id,
        )
        await self.session.execute(statement)

    async def get_ready(self, file_id: int) -> ThumbnailBytes | None:
        statement = (
            select(FileThumbnailModel)
            .options(undefer(FileThumbnailModel.data))
            .where(
                FileThumbnailModel.file_id == file_id,
                FileThumbnailModel.user_id == self.user_id,
                FileThumbnailModel.status == THUMBNAIL_STATUS_READY,
            )
        )
        row = (await self.session.execute(statement)).scalar_one_or_none()
        if row is None or row.data is None or row.sha256 is None:
            return None
        return ThumbnailBytes(data=row.data, sha256=row.sha256)

    async def meta_for(self, file_ids: Sequence[int]) -> dict[int, ThumbnailMeta]:
        if not file_ids:
            return {}
        statement = select(
            FileThumbnailModel.file_id,
            FileThumbnailModel.width,
            FileThumbnailModel.height,
            FileThumbnailModel.sha256,
        ).where(
            FileThumbnailModel.user_id == self.user_id,
            FileThumbnailModel.file_id.in_(list(file_ids)),
            FileThumbnailModel.status == THUMBNAIL_STATUS_READY,
        )
        result: dict[int, ThumbnailMeta] = {}
        for file_id, width, height, sha256 in (await self.session.execute(statement)).all():
            if width is None or height is None or sha256 is None:
                continue
            result[file_id] = ThumbnailMeta(
                file_id=file_id, width=width, height=height, sha256=sha256
            )
        return result

    async def find_reusable(
        self,
        *,
        content_hash: str,
        extension: str,
        generator_version: int,
        exclude_file_id: int,
    ) -> int | None:
        """Find a ready thumbnail of another file with byte-identical content."""
        statement = (
            select(FileThumbnailModel.file_id)
            .join(
                FileModel,
                (FileModel.id == FileThumbnailModel.file_id)
                & (FileModel.user_id == FileThumbnailModel.user_id),
            )
            .where(
                FileThumbnailModel.user_id == self.user_id,
                FileThumbnailModel.status == THUMBNAIL_STATUS_READY,
                FileThumbnailModel.generator_version >= generator_version,
                FileModel.content_hash == content_hash,
                func.lower(FileModel.extension) == extension.lower(),
                FileModel.id != exclude_file_id,
            )
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def clone(self, *, source_file_id: int, target_file_id: int) -> bool:
        """Copy a ready thumbnail to another file id of the same owner."""
        now = utcnow()
        source = select(
            literal(target_file_id),
            FileThumbnailModel.user_id,
            FileThumbnailModel.status,
            FileThumbnailModel.data,
            FileThumbnailModel.width,
            FileThumbnailModel.height,
            FileThumbnailModel.sha256,
            FileThumbnailModel.generator_version,
            literal(1),
            literal(now),
            literal(now),
        ).where(
            FileThumbnailModel.file_id == source_file_id,
            FileThumbnailModel.user_id == self.user_id,
            FileThumbnailModel.status == THUMBNAIL_STATUS_READY,
        )
        statement = (
            insert(FileThumbnailModel)
            .from_select(
                [
                    "file_id",
                    "user_id",
                    "status",
                    "data",
                    "width",
                    "height",
                    "sha256",
                    "generator_version",
                    "attempts",
                    "created_at",
                    "updated_at",
                ],
                source,
            )
            .on_conflict_do_nothing(index_elements=[FileThumbnailModel.file_id])
        )
        result = await self.session.execute(statement)
        return bool(getattr(result, "rowcount", 0))
