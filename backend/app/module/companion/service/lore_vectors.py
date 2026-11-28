"""Cached embedding vectors for lore fragments, shared across processes.

A fragment's vector depends only on the embedder model and its text, so it is
keyed by ``(model, sha256(text))``. Vectors live in a small in-process LRU and,
when the app has a cache, in Valkey for thirty days: the dedicated worker warms
every shipped preset fragment there, so a search in the API embeds only the
query. Edited or custom fragments are embedded lazily on first use.

Valkey is disposable: a miss or an outage only means the vector is recomputed.
"""

import asyncio
import hashlib
import logging
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Protocol

from app.module.companion.domain.story_domain import STORY_LOCALES, is_semantic_embedder
from app.module.companion.protocol.companion_story_protocol import LoreEmbedderProtocol
from app.module.companion.service.preset_lore_catalog import load_presets

logger = logging.getLogger(__name__)

_MEMORY_SIZE = 4096
_CACHE_TTL_SECONDS = 30 * 24 * 3600
_CACHE_PREFIX = "companion-lore-vector"
_WARM_BATCH = 32
_WARM_INTERVAL_SECONDS = 6 * 3600

_memory: OrderedDict[tuple[str, str], list[float]] = OrderedDict()


class LoreVectorCacheProtocol(Protocol):
    """The subset of the shared JSON cache the vector store uses."""

    async def get_json(self, key: str) -> Any: ...

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None: ...


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_key(model: str, digest: str) -> str:
    return f"{_CACHE_PREFIX}:{model}:{digest}"


def _vector(value: object) -> list[float] | None:
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, int | float) for item in value):
        return None
    return [float(item) for item in value]


def clear_memory() -> None:
    """Forget every in-process vector (tests use this for isolation)."""
    _memory.clear()


class LoreVectorStore:
    """Two-level vector cache: process memory first, then the shared cache."""

    def __init__(self, cache: LoreVectorCacheProtocol | None = None) -> None:
        self.cache = cache

    async def get(self, model: str, text: str) -> list[float] | None:
        """Return the cached vector for ``text`` under ``model``, if any."""
        key = (model, _digest(text))
        vector = _memory.get(key)
        if vector is not None:
            _memory.move_to_end(key)
            return vector
        if self.cache is None:
            return None
        try:
            vector = _vector(await self.cache.get_json(_cache_key(*key)))
        except Exception:
            return None
        if vector is not None:
            self._remember(key, vector)
        return vector

    async def put(self, model: str, text: str, vector: list[float]) -> None:
        """Store a vector in process memory and, best-effort, the shared cache."""
        key = (model, _digest(text))
        self._remember(key, vector)
        if self.cache is None:
            return
        try:
            await self.cache.set_json(_cache_key(*key), vector, _CACHE_TTL_SECONDS)
        except Exception:
            logger.debug("lore vector cache write failed")

    @staticmethod
    def _remember(key: tuple[str, str], vector: list[float]) -> None:
        _memory[key] = vector
        _memory.move_to_end(key)
        while len(_memory) > _MEMORY_SIZE:
            _memory.popitem(last=False)


def preset_lore_texts() -> list[str]:
    """Return every shipped fragment text in every story locale, deduplicated."""
    texts: dict[str, None] = {}
    for locale in STORY_LOCALES:
        for preset in load_presets(locale).values():
            for fragment in preset.fragments:
                texts[fragment.text] = None
    return list(texts)


class LoreVectorWarmer:
    """Embed every shipped preset fragment ahead of time (idempotent)."""

    def __init__(
        self,
        *,
        embedder: Callable[[], LoreEmbedderProtocol | None],
        vectors: LoreVectorStore,
        interval_seconds: float = _WARM_INTERVAL_SECONDS,
    ) -> None:
        self.embedder = embedder
        self.vectors = vectors
        self.interval_seconds = interval_seconds

    async def run_once(self) -> int:
        """Embed the fragments missing for the current model; return how many."""
        embedder = self.embedder()
        if embedder is None or not is_semantic_embedder(embedder.model_name, embedder.dimension):
            return 0
        model = embedder.model_name
        missing = [
            text for text in preset_lore_texts() if await self.vectors.get(model, text) is None
        ]
        warmed = 0
        for start in range(0, len(missing), _WARM_BATCH):
            batch = missing[start : start + _WARM_BATCH]
            try:
                vectors = await embedder.embed(batch)
            except Exception:
                logger.warning("lore vector warm-up failed; it will retry later")
                return warmed
            if len(vectors) != len(batch):
                return warmed
            for text, vector in zip(batch, vectors, strict=True):
                await self.vectors.put(model, text, vector)
            warmed += len(batch)
        if warmed:
            logger.info("lore vectors warmed count=%s model=%s", warmed, model)
        return warmed

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """Warm now, then re-check periodically (a model change re-warms)."""
        stop = stop_event or asyncio.Event()
        logger.info("lore vector warmer started")
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.warning("lore vector warm-up failed", exc_info=True)
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue


__all__ = [
    "LoreVectorCacheProtocol",
    "LoreVectorStore",
    "LoreVectorWarmer",
    "clear_memory",
    "preset_lore_texts",
]
