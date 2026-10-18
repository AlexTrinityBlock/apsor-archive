"""DeepSeek chat-completions client (OpenAI-compatible)."""

import logging

import httpx

from app.module.knowledge.exception.domain_error import AiNotConfiguredError, AiProviderError
from app.module.knowledge.protocol.text_generator_protocol import AiCompletion

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """The only place that knows the DeepSeek HTTP contract."""

    configured = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        temperature: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def _complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
    ) -> AiCompletion:
        payload: dict[str, object] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "thinking": {"type": "disabled"},
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

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
            raise AiProviderError(f"network error: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:300].replace("\n", " ")
            raise AiProviderError(f"HTTP {response.status_code}: {detail}")
        try:
            body = response.json()
            choice = body["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AiProviderError("malformed completion response") from exc
        if not isinstance(text, str) or not text.strip():
            raise AiProviderError("empty completion")

        usage_raw = body.get("usage") if isinstance(body, dict) else None
        usage: dict[str, int] = {}
        if isinstance(usage_raw, dict):
            usage = {
                str(key): int(value)
                for key, value in usage_raw.items()
                if isinstance(value, int)
            }
        model = body.get("model") if isinstance(body, dict) else None
        return AiCompletion(
            text=text.strip(),
            model=str(model or self.model_name),
            usage=usage,
        )

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        return await self._complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=False,
        )

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        return await self._complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
        )


class NullTextGenerator:
    """Fail fast when no AI key is configured."""

    configured = False
    model_name = "unconfigured"

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        raise AiNotConfiguredError()

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        raise AiNotConfiguredError()
