"""OpenAI-compatible embedding provider."""

import httpx

from app.module.knowledge.exception.domain_error import EmbeddingProviderError


class OpenAICompatibleEmbedder:
    """Call a hosted ``/embeddings`` endpoint and normalize its vectors."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        dimension: int,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model
        self.dimension = dimension
        self.timeout_seconds = timeout_seconds

    async def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model_name, "input": texts}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingProviderError(str(exc)) from exc

        body = response.json()
        data = body.get("data")
        if not isinstance(data, list) or not data:
            raise EmbeddingProviderError("The embedding response has no data.")
        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(embedding, list):
                raise EmbeddingProviderError("An embedding item has no vector.")
            vectors.append([float(value) for value in embedding])
        return vectors


class DisabledEmbedder:
    """A no-op embedder used when vector recall is disabled."""

    dimension = 0
    model_name = "none"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingProviderError("Embeddings are disabled.")
