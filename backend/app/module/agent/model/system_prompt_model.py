"""Singleton custom system prompt, loaded before the built-in sections."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base
from app.shared.time import utcnow

SYSTEM_PROMPT_ID = 1


class SystemPromptModel(Base):
    """One owner-authored prompt section, frozen into each new conversation."""

    __tablename__ = "system_prompt"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("char_length(title) <= 200", name="title_length"),
        CheckConstraint("char_length(body) <= 32000", name="body_length"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=SYSTEM_PROMPT_ID)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
