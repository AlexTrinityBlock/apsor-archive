"""Document vision extraction and structured analysis contracts."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class VisionDocument(BaseModel):
    """Text and metadata extracted from one image or PDF page."""

    model_config = ConfigDict(frozen=True)

    text: str
    caption: str
    ocr_text: str
    title: str
    summary: str
    document_type: str
    tags: list[str]
    language: str
    description: str = ""
    tables: list[str] = Field(default_factory=list)


class VisionExtractorProtocol(Protocol):
    configured: bool
    model_name: str

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        description_language: str,
        mode: Literal["image", "document"] = "image",
    ) -> VisionDocument: ...


class DocumentAnalysis(BaseModel):
    """AI structured judgment before a document is indexed."""

    model_config = ConfigDict(frozen=True)

    has_meaningful_text: bool
    use_vision: bool
    document_type: str
    title: str
    summary: str
    tags: list[str]
    language: str
