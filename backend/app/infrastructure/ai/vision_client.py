"""OpenAI-compatible vision requests and the media caption wrapper."""

import base64
import json
from typing import Any

import httpx

from app.module.media.exception.domain_error import (
    MediaCaptionFailedError,
    MediaNotConfiguredError,
)
from app.module.media.protocol.media_captioner_protocol import MediaCaption


class VisionProviderError(Exception):
    """Raised by the low-level vision client; wrappers translate it."""


VISION_SYSTEM_PROMPT = (
    "You are the visual archivist of a personal knowledge library. Analyze the "
    "image so its content can be found later by a text search. Return JSON with "
    'the keys "caption" (2 to 4 sentences describing the image), "ocr_text" '
    "(all legible text in the image, verbatim, or an empty string), "
    '"title" (a short human title), "summary" (1 to 2 sentences), "tags" '
    '(5 to 8 short strings), "objects" (short strings), "scene" (short string), '
    'and "document_type" (photo, screenshot, receipt, scanned_document, chart, '
    'diagram, whiteboard, or other). Do not invent text that is not visible. '
    "Write in the dominant language of any text in the image, otherwise English."
)


class DeepSeekVisionClient:
    """One HTTP call surface shared by media captions and document OCR."""

    configured = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.timeout_seconds = timeout_seconds

    async def analyze(
        self,
        data: bytes,
        mime_type: str,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 700,
    ) -> dict[str, Any]:
        encoded = base64.b64encode(data).decode("ascii")
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                        },
                    ],
                },
            ],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise VisionProviderError(f"network error: {exc}") from exc
        if response.status_code >= 400:
            detail = response.text[:300].replace("\n", " ")
            raise VisionProviderError(f"HTTP {response.status_code}: {detail}")
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise VisionProviderError("malformed vision response") from exc
        if not isinstance(parsed, dict):
            raise VisionProviderError("vision response is not a JSON object")
        return parsed


class DeepSeekVisionCaptioner:
    """Media-slice captioner built on the shared vision client."""

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

    async def caption(self, data: bytes, mime_type: str) -> MediaCaption:
        try:
            parsed = await self._client.analyze(
                data,
                mime_type,
                system_prompt=VISION_SYSTEM_PROMPT,
                user_prompt="Describe this image and return the JSON object.",
                max_tokens=700,
            )
        except VisionProviderError as exc:
            raise MediaCaptionFailedError(str(exc)) from exc

        caption = parsed.get("caption")
        if not isinstance(caption, str) or not caption.strip():
            raise MediaCaptionFailedError("empty caption")

        tags: list[str] = []
        for key in ("tags", "objects"):
            values = parsed.get(key)
            if isinstance(values, list):
                tags.extend(str(value).strip() for value in values if str(value).strip())
        scene = parsed.get("scene")
        if isinstance(scene, str) and scene.strip():
            tags.append(scene.strip())
        unique_tags = list(dict.fromkeys(tags))[:12]
        ocr_text = parsed.get("ocr_text")
        title = parsed.get("title")
        summary = parsed.get("summary")
        document_type = parsed.get("document_type")
        return MediaCaption(
            caption=caption.strip(),
            ocr_text=ocr_text.strip() if isinstance(ocr_text, str) else "",
            title=title.strip() if isinstance(title, str) and title.strip() else caption[:120],
            summary=summary.strip() if isinstance(summary, str) else "",
            document_type=(
                document_type.strip().lower()
                if isinstance(document_type, str) and document_type.strip()
                else "other"
            ),
            tags=unique_tags,
        )


class NullMediaCaptioner:
    """Used when no vision-capable chat provider is configured."""

    configured = False
    model_name = "unconfigured"

    async def caption(self, data: bytes, mime_type: str) -> MediaCaption:
        raise MediaNotConfiguredError()
