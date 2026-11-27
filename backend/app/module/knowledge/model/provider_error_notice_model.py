"""Persistent provider-chain outage notices for root.

The table is global operational state, not archive content. Every row describes
one sanitized whole-chain failure: which capability/operation failed, the last
provider's stable error code, the ordered attempt list, and when it was seen.
Row-level security follows the other global tables: read-all, root-write.
"""

from datetime import datetime
from typing import Any

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.shared.time import utcnow


class ProviderErrorNoticeModel(Base):
    """One deduplicated provider-chain failure surfaced on the Accounts page."""

    __tablename__ = "provider_error_notice"
    __table_args__ = (
        CheckConstraint(
            "capability IN ('chat', 'embedding', 'web_search', 'web_fetch')",
            name="capability_valid",
        ),
        CheckConstraint("count >= 0", name="count_non_negative"),
        Index(
            "ix_provider_error_notice_resolved_last_seen",
            "resolved_at",
            "last_seen_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    capability: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            name="fk_provider_error_notice_resolved_by_user_id_app_user",
            ondelete="SET NULL",
        ),
        nullable=True,
    )


__all__ = ["ProviderErrorNoticeModel"]
