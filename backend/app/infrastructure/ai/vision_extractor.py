"""Vision extraction for images and scanned PDF pages."""

import json
from typing import Literal

from app.infrastructure.ai.vision_client import DeepSeekVisionClient, VisionProviderError
from app.module.knowledge.domain.ingest_config_domain import (
    normalize_vision_description_language,
)
from app.module.knowledge.exception.domain_error import VisionExtractionError
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument

VISION_IMAGE_MAX_TOKENS = 4096
VISION_DOCUMENT_MAX_TOKENS = 2400


def build_vision_prompt(
    description_language: str,
    mode: Literal["image", "document"],
) -> str:
    """Build the fixed, versioned prompt for one vision extraction mode.

    OCR text and table cell text stay verbatim in the source language. Only the
    description and the short metadata fields use ``description_language``.
    """
    language = json.dumps(normalize_vision_description_language(description_language))
    shared = (
        "Return one JSON object with the keys text, tables, description, caption, "
        "title, summary, document_type, tags, and language. "
        f"Use {language} for description, caption, title, summary, and tags. "
        "text must contain OCR text verbatim in its original language. Do not "
        "translate, paraphrase, summarize, or invent text. tables must be an array "
        "of GitHub-Flavored Markdown tables; preserve header rows, column order, row "
        "order, and cell text verbatim, and repeat a merged cell's value in every "
        "cell it covers. Do not translate the OCR text or table cell text. caption is "
        "one sentence in the configured language. title is a short title in the "
        "configured language. summary is one or two sentences in the configured "
        "language. tags is 5 to 8 short strings in the configured language. language "
        "is the dominant language of the visible text, or an empty string when there "
        "is none. Never invent content that is not visible."
    )
    if mode == "document":
        return (
            "You extract searchable text, tables, and a brief layout note from one "
            f"scanned document page. {shared} "
            "text covers all readable non-table text on the page and preserves line "
            "breaks; use an empty string when there is no non-table text. tables is "
            "an empty array when there are no tables. description is a brief layout "
            "note in the configured language: where text blocks, tables, figures, "
            "headers, and footers sit. Do not produce an exhaustive visual essay. "
            "Keep document_type accurate (scanned_document, receipt, table, chart, "
            "diagram, screenshot, photo, or other)."
        )
    return (
        "You extract searchable text, tables, and metadata from one image. "
        f"{shared} "
        "text is every visible non-table text string, verbatim in its original "
        "language, in natural reading order (left-to-right, top-to-bottom; finish "
        "one column before the next). Use an empty string when there is no non-table "
        "text. tables is an empty array when there are no tables. description is a "
        "complete visual description in the configured language; read left-to-right "
        "and top-to-bottom, and cover layout, regions, shapes, colors, objects, "
        "people, UI controls, and their spatial relationships. Be specific and "
        "factual. Do not repeat or translate the OCR text or table cell text. "
        "document_type is one of screenshot, photo, receipt, chart, diagram, "
        "scanned_document, table, or other."
    )


class DeepSeekVisionExtractor:
    """Use the configured chat/vision model for OCR and page metadata."""

    configured = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._client = DeepSeekVisionClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
        )
        self.model_name = model

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        description_language: str,
        mode: Literal["image", "document"] = "image",
    ) -> VisionDocument:
        try:
            parsed = await self._client.analyze(
                data,
                mime_type,
                system_prompt=build_vision_prompt(description_language, mode),
                user_prompt=(
                    "Extract the text, tables, layout note, and metadata from this "
                    "document page."
                    if mode == "document"
                    else "Extract the text, tables, description, and metadata from this image."
                ),
                max_tokens=(
                    VISION_IMAGE_MAX_TOKENS
                    if mode == "image"
                    else VISION_DOCUMENT_MAX_TOKENS
                ),
            )
        except VisionProviderError as exc:
            raise VisionExtractionError(str(exc)) from exc

        text = parsed.get("text")
        if not isinstance(text, str):
            text = ""
        caption = parsed.get("caption")
        title = parsed.get("title")
        summary = parsed.get("summary")
        document_type = parsed.get("document_type")
        raw_tags = parsed.get("tags")
        tags = (
            [str(tag).strip() for tag in raw_tags if str(tag).strip()]
            if isinstance(raw_tags, list)
            else []
        )
        raw_tables = parsed.get("tables")
        if isinstance(raw_tables, str):
            raw_tables = [raw_tables]
        tables = (
            [
                table.strip()
                for table in raw_tables
                if isinstance(table, str) and table.strip()
            ]
            if isinstance(raw_tables, list)
            else []
        )
        description = parsed.get("description")
        language = parsed.get("language")
        return VisionDocument(
            text=text.strip(),
            caption=caption.strip() if isinstance(caption, str) else "",
            ocr_text=text.strip(),
            title=(
                title.strip() if isinstance(title, str) and title.strip() else "Untitled document"
            ),
            summary=summary.strip() if isinstance(summary, str) else "",
            document_type=(
                document_type.strip().lower()
                if isinstance(document_type, str) and document_type.strip()
                else "other"
            ),
            tags=tags[:8],
            language=language.strip() if isinstance(language, str) else "",
            description=description.strip() if isinstance(description, str) else "",
            tables=tables,
        )


class NullVisionExtractor:
    """Fail closed when the chat/vision provider is not configured."""

    configured = False
    model_name = "unconfigured"

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        description_language: str,
        mode: Literal["image", "document"] = "image",
    ) -> VisionDocument:
        raise VisionExtractionError("A vision-capable chat provider is required for this document.")


__all__ = [
    "VISION_DOCUMENT_MAX_TOKENS",
    "VISION_IMAGE_MAX_TOKENS",
    "DeepSeekVisionExtractor",
    "NullVisionExtractor",
    "build_vision_prompt",
]
