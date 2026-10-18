"""Inverted n-gram index used by BM25 text recall."""

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.module.knowledge.model.base import Base


class ChunkNgramModel(Base):
    """One row per unique gram in a chunk, with its term frequency."""

    __tablename__ = "chunk_ngram"
    __table_args__ = (
        Index("ix_chunk_ngram_gram", "gram"),
        Index("ix_chunk_ngram_chunk_id", "chunk_id"),
    )

    chunk_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chunk.id", ondelete="CASCADE"),
        primary_key=True,
    )
    gram: Mapped[str] = mapped_column(Text, primary_key=True)
    term_frequency: Mapped[int] = mapped_column(Integer, nullable=False)
