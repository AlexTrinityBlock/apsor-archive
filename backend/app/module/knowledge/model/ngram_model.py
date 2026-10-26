"""Inverted n-gram index used by BM25 text recall."""

from sqlalchemy import BigInteger, ForeignKey, ForeignKeyConstraint, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base


class ChunkNgramModel(Base):
    """One row per unique gram in a chunk, with its term frequency."""

    __tablename__ = "chunk_ngram"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chunk_id", "user_id"],
            ["chunk.id", "chunk.user_id"],
            name="fk_chunk_ngram_chunk_user",
            ondelete="CASCADE",
        ),
        Index("ix_chunk_ngram_gram", "gram"),
        Index("ix_chunk_ngram_chunk_id", "chunk_id"),
        Index("ix_chunk_ngram_user_id_gram", "user_id", "gram"),
    )

    chunk_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "app_user.id",
            ondelete="RESTRICT",
            name="fk_chunk_ngram_user_id_app_user",
        ),
        nullable=False,
    )
    gram: Mapped[str] = mapped_column(Text, primary_key=True)
    term_frequency: Mapped[int] = mapped_column(Integer, nullable=False)
