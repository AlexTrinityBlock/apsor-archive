"""Vision extraction for images and scanned PDF pages."""

from typing import Literal

from app.infrastructure.ai.vision_client import DeepSeekVisionClient, VisionProviderError
from app.module.knowledge.domain.vision_prompt_domain import (
    DEFAULT_VISION_DOCUMENT_PROMPT,
    DEFAULT_VISION_IMAGE_PROMPT,
    render_vision_prompt,
)
from app.module.knowledge.exception.domain_error import VisionExtractionError
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument

VISION_IMAGE_MAX_TOKENS = 4096
VISION_DOCUMENT_MAX_TOKENS = 2400

VISION_IMAGE_USER_PROMPT = (
    "Extract the text, tables, description, and metadata from this image."
)
VISION_DOCUMENT_USER_PROMPT = (
    "Extract the text, tables, layout note, and metadata from this document page."
)


def build_vision_prompt(
    description_language: str,
    mode: Literal["image", "document"],
) -> str:
    """Render the matching built-in prompt for one vision extraction mode.

    The extraction path renders the configured prompt in ``FileService``; this
    wrapper remains for callers that need the built-in text, including tests and
    older integrations.
    """
    template = (
        DEFAULT_VISION_DOCUMENT_PROMPT if mode == "document" else DEFAULT_VISION_IMAGE_PROMPT
    )
    return render_vision_prompt(
        template,
        description_language,
        mode=mode,
    ).system_prompt


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
        system_prompt: str,
        mode: Literal["image", "document"] = "image",
    ) -> VisionDocument:
        try:
            parsed = await self._client.analyze(
                data,
                mime_type,
                system_prompt=system_prompt,
                user_prompt=(
                    VISION_DOCUMENT_USER_PROMPT
                    if mode == "document"
                    else VISION_IMAGE_USER_PROMPT
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
        system_prompt: str,
        mode: Literal["image", "document"] = "image",
    ) -> VisionDocument:
        raise VisionExtractionError("A vision-capable chat provider is required for this document.")


__all__ = [
    "VISION_DOCUMENT_MAX_TOKENS",
    "VISION_DOCUMENT_USER_PROMPT",
    "VISION_IMAGE_MAX_TOKENS",
    "VISION_IMAGE_USER_PROMPT",
    "DeepSeekVisionExtractor",
    "NullVisionExtractor",
    "build_vision_prompt",
]
