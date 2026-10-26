"""OpenAI-compatible vision requests used by document extraction."""

import base64
import json
from typing import Any

import httpx


class VisionProviderError(Exception):
    """Raised by the low-level vision client; callers translate it."""


class DeepSeekVisionClient:
    """One HTTP call surface for image OCR and document vision extraction."""

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
            raise VisionProviderError(f"HTTP {response.status_code}")
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise VisionProviderError("malformed vision response") from exc
        if not isinstance(parsed, dict):
            raise VisionProviderError("vision response is not a JSON object")
        return parsed
