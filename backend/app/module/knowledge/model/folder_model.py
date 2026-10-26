"""Folder records for the File Library hierarchy.

Files are not stored in this table. A file leaf is derived from
``file.raw_file_path``; folders are explicit records so empty folders, folder
identity, and folder moves do not depend on a file existing.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base
from app.shared.time import utcnow


class FolderModel(Base):
    """One folder in the File Library tree."""

    __tablename__ = "folder"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_folder_id_user_id"),
        ForeignKeyConstraint(
            ["parent_id", "user_id"],
            ["folder.id", "folder.user_id"],
            name="fk_folder_parent_user",
            ondelete="CASCADE",
        ),
        Index("uq_folder_path", "user_id", "path", unique=True),
        Index("ix_folder_parent_id", "parent_id"),
        Index("ix_folder_depth", "depth"),
        Index("ix_folder_user_id_parent_id", "user_id", "parent_id"),
        Index("ix_folder_user_id_depth", "user_id", "depth"),
        CheckConstraint("depth >= 1", name="depth_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_folder_user_id_app_user",
        ),
        nullable=False,
    )
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
