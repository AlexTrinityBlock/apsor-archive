"""Pure signed feature-hashing embedder.

This is an offline, deterministic vectorizer. It is not a semantic model, but it
provides real vector recall for lexical neighbors and keeps the vector path
usable without downloading a model. Configure ``APSOR_EMBEDDING_PROVIDER=openai``
to use a hosted embedding model instead.
"""

import hashlib
import math

from app.shared.text.ngram import iter_embedding_terms


class HashingEmbedder:
    """Map tokens into a fixed-dimensional signed vector."""

    def __init__(self, *, dimension: int = 384, model_name: str = "apsor-hash-384") -> None:
        if dimension < 16:
            raise ValueError("dimension must be at least 16")
        self.dimension = dimension
        self.model_name = model_name

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for term in iter_embedding_terms(text):
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, byteorder="big", signed=False)
            index = (value >> 1) % self.dimension
            sign = 1.0 if value & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            return vector
        return [component / norm for component in vector]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch synchronously behind the async protocol."""
        return [self._embed_one(text) for text in texts]
