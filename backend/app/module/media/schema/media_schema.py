"""Schemas for standalone multimodal media retrieval."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

MediaMatch = Literal["text", "visual"]


class MediaSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    media_id: int
    raw_file_path: str
    file_name: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    caption: str
    ocr_text: str
    title: str
    summary: str
    document_type: str
    tags: list[str]
    update_time: datetime
    created_at: datetime


class MediaSearchResultSchema(MediaSchema):
    model_config = ConfigDict(frozen=True)

    score: float
    matched_by: MediaMatch


class MediaSearchResponseSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str | None
    mode: MediaMatch
    total: int
    elapsed_ms: int
    results: list[MediaSearchResultSchema]
