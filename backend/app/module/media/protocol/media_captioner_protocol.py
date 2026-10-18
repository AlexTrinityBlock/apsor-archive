"""Vision captioning contract."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class MediaCaption(BaseModel):
    model_config = ConfigDict(frozen=True)

    caption: str
    ocr_text: str
    title: str
    summary: str
    document_type: str
    tags: list[str]


class MediaCaptionerProtocol(Protocol):
    configured: bool
    model_name: str

    async def caption(self, data: bytes, mime_type: str) -> MediaCaption: ...
