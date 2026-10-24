"""Vision extraction for images and scanned PDF pages."""

from app.infrastructure.ai.vision_client import DeepSeekVisionClient, VisionProviderError
from app.module.knowledge.exception.domain_error import VisionExtractionError
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument

DOCUMENT_VISION_PROMPT = (
    "You extract searchable text and metadata from a document page or image. "
    "Return JSON with the keys: text (all readable text, verbatim, in reading "
    "order; empty if there is none), caption (a short description), title, "
    "summary (1 to 2 sentences), document_type (scanned_document, screenshot, "
    "receipt, chart, diagram, photo, or other), tags (5 to 8 short strings), and "
    "language. Never invent text that is not visible. Preserve the original "
    "language of the document."
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

    async def extract(self, data: bytes, mime_type: str) -> VisionDocument:
        try:
            parsed = await self._client.analyze(
                data,
                mime_type,
                system_prompt=DOCUMENT_VISION_PROMPT,
                user_prompt="Extract the text and metadata from this document page.",
                max_tokens=1600,
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
        )


class NullVisionExtractor:
    """Fail closed when the chat/vision provider is not configured."""

    configured = False
    model_name = "unconfigured"

    async def extract(self, data: bytes, mime_type: str) -> VisionDocument:
        raise VisionExtractionError("A vision-capable chat provider is required for this document.")
