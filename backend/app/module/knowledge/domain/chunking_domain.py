"""Sentence-aware chunking with a bounded character overlap."""

import re

from pydantic import BaseModel, ConfigDict

from app.shared.text.ngram import count_terms

_SENTENCE_BREAK = re.compile(
    r"(?<=[.!?;])|(?<=[\u3002\uff01\uff1f\uff1b])|(?<=[\n])"
)
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n+")


class ChunkDraft(BaseModel):
    """One chunk ready to be persisted and indexed."""

    model_config = ConfigDict(frozen=True)

    index: int
    content: str
    char_count: int
    token_count: int


def normalize_document_text(text: str) -> str:
    """Normalize line endings, remove NULs, and trim outer whitespace."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return normalized.strip()


def _sentences(text: str) -> list[str]:
    units: list[str] = []
    for paragraph in _PARAGRAPH_BREAK.split(text):
        for piece in _SENTENCE_BREAK.split(paragraph):
            sentence = piece.strip()
            if sentence:
                units.append(sentence)
    return units


def _tail(value: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or not value:
        return ""
    return value[-overlap_chars:].strip()


def _split_long_unit(value: str, target_chars: int) -> list[str]:
    pieces: list[str] = []
    remaining = value
    while len(remaining) > target_chars:
        pieces.append(remaining[:target_chars])
        remaining = remaining[target_chars:]
    if remaining:
        pieces.append(remaining)
    return pieces


def chunk_text(text: str, *, target_chars: int, overlap_chars: int) -> list[ChunkDraft]:
    """Split a document into deterministic, 1-based chunks.

    A chunk is flushed when the next sentence would push it past
    ``target_chars``. The next chunk starts with at most ``overlap_chars`` from
    the previous chunk so a sentence straddling a boundary remains retrievable.
    """
    if target_chars < 100:
        raise ValueError("target_chars must be at least 100")
    if overlap_chars < 0 or overlap_chars >= target_chars:
        raise ValueError("overlap_chars must be between 0 and target_chars")

    normalized = normalize_document_text(text)
    if not normalized:
        return []

    raw_chunks: list[str] = []
    buffer = ""
    for sentence in _sentences(normalized):
        units = (
            _split_long_unit(sentence, target_chars)
            if len(sentence) > target_chars
            else [sentence]
        )
        for unit in units:
            candidate = f"{buffer}\n{unit}".strip() if buffer else unit
            if buffer and len(candidate) > target_chars:
                raw_chunks.append(buffer)
                prefix = _tail(buffer, overlap_chars)
                buffer = f"{prefix}\n{unit}".strip() if prefix else unit
            else:
                buffer = candidate
            while len(buffer) > target_chars:
                raw_chunks.append(buffer[:target_chars])
                prefix = _tail(buffer[:target_chars], overlap_chars)
                remainder = buffer[target_chars:]
                buffer = f"{prefix}\n{remainder}".strip() if prefix else remainder
    if buffer:
        raw_chunks.append(buffer)

    drafts: list[ChunkDraft] = []
    for content in raw_chunks:
        cleaned = content.strip()
        if len(cleaned) < 2:
            continue
        drafts.append(
            ChunkDraft(
                index=len(drafts) + 1,
                content=cleaned,
                char_count=len(cleaned),
                token_count=count_terms(cleaned),
            )
        )
    return drafts
