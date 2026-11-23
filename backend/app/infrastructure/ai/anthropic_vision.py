"""Anthropic vision extraction for images and scanned PDF pages.

This extractor mirrors ``DeepSeekVisionExtractor``: it receives the rendered
system prompt from ``FileService`` and returns the same ``VisionDocument``
shape. The image bytes travel as one base64 image block next to the short
extraction instruction, and the JSON body is parsed here.

The output caps are the same as the DeepSeek path: 4,096 tokens for one image
and 2,400 for a scanned document page.
"""

import base64
import json
from typing import Any, Literal

from app.infrastructure.ai.anthropic_client import AnthropicClient
from app.module.knowledge.exception.domain_error import (
    AiProviderError,
    VisionExtractionError,
)
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument

VISION_IMAGE_MAX_TOKENS = 4096
VISION_DOCUMENT_MAX_TOKENS = 2400

VISION_IMAGE_USER_PROMPT = (
    "Extract the text, tables, description, and metadata from this image."
)
VISION_DOCUMENT_USER_PROMPT = (
    "Extract the text, tables, layout note, and metadata from this document page."
)


class AnthropicVisionExtractor:
    """Use an Anthropic vision-capable model for OCR and page metadata."""

    configured = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        reasoning_effort: str | None = None,
    ) -> None:
        # ``complete_chat`` takes its output cap from ``chat_max_tokens``, so the
        # two modes share connection settings but use their own cap.
        self._image_client = AnthropicClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            max_tokens=VISION_IMAGE_MAX_TOKENS,
            chat_max_tokens=VISION_IMAGE_MAX_TOKENS,
            reasoning_effort=reasoning_effort,
        )
        self._document_client = AnthropicClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            max_tokens=VISION_DOCUMENT_MAX_TOKENS,
            chat_max_tokens=VISION_DOCUMENT_MAX_TOKENS,
            reasoning_effort=reasoning_effort,
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
        client = self._document_client if mode == "document" else self._image_client
        encoded = base64.b64encode(data).decode("ascii")
        user_prompt = (
            VISION_DOCUMENT_USER_PROMPT
            if mode == "document"
            else VISION_IMAGE_USER_PROMPT
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded}",
                        },
                    },
                ],
            },
        ]
        try:
            analysis = await client.complete_chat(messages, [], stream=False)
            parsed = json.loads(analysis.text)
        except AiProviderError as exc:
            raise VisionExtractionError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise VisionExtractionError("malformed vision response") from exc
        if not isinstance(parsed, dict):
            raise VisionExtractionError("vision response is not a JSON object")

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
                title.strip()
                if isinstance(title, str) and title.strip()
                else "Untitled document"
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
            usage=analysis.usage,
        )


__all__ = [
    "VISION_DOCUMENT_MAX_TOKENS",
    "VISION_DOCUMENT_USER_PROMPT",
    "VISION_IMAGE_MAX_TOKENS",
    "VISION_IMAGE_USER_PROMPT",
    "AnthropicVisionExtractor",
]
