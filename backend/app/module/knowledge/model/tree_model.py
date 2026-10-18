"""Unified branch table for the File Library tree."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base
from app.shared.time import utcnow

NODE_KIND_FOLDER = "folder"
NODE_KIND_FILE = "file"
NODE_KINDS = (NODE_KIND_FOLDER, NODE_KIND_FILE)


class TreeNodeModel(Base):
    """A folder or a file leaf in one unified tree.

    A historical branch is a row with ``is_current = false``; the row it was
    replaced by is linked through ``superseded_by_id``.
    """

    __tablename__ = "tree_node"
    __table_args__ = (
        Index(
            "uq_tree_node_current_path",
            "path",
            unique=True,
            postgresql_where=text("is_current AND deleted_at IS NULL"),
        ),
        Index("ix_tree_node_parent_id", "parent_id"),
        Index("ix_tree_node_path", "path"),
        Index("ix_tree_node_file_id", "file_id"),
        CheckConstraint("kind IN ('folder', 'file')", name="kind_valid"),
        CheckConstraint("depth >= 1", name="depth_positive"),
        CheckConstraint(
            "(kind = 'file' AND file_id IS NOT NULL) OR (kind = 'folder' AND file_id IS NULL)",
            name="file_id_matches_kind",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("tree_node.id", ondelete="CASCADE"), nullable=True
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    file_id: Mapped[int | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("tree_node.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
