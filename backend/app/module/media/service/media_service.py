"""Standalone media ingestion and retrieval."""

import hashlib
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from app.module.media.domain.visual_domain import (
    MODEL_NAME,
    InvalidImageError,
    extract_visual_features,
)
from app.module.media.exception.domain_error import (
    InvalidMediaPathError,
    InvalidMediaQueryError,
    MediaCaptionFailedError,
    MediaNotConfiguredError,
    MediaNotFoundError,
    MediaTooLargeError,
    UnsupportedMediaTypeError,
)
from app.module.media.model.media_model import MediaModel
from app.module.media.protocol.media_cache_protocol import MediaCacheProtocol
from app.module.media.protocol.media_captioner_protocol import (
    MediaCaption,
    MediaCaptionerProtocol,
)
from app.module.media.protocol.media_repository_protocol import MediaRepositoryProtocol
from app.module.media.protocol.media_storage_protocol import MediaStorageProtocol
from app.module.media.schema.media_schema import (
    MediaSchema,
    MediaSearchResponseSchema,
    MediaSearchResultSchema,
)
from app.shared.text.ngram import count_terms, term_frequencies, unique_query_terms

logger = logging.getLogger(__name__)

MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
ALLOWED_MIME_TYPES = frozenset(MIME_EXTENSIONS)
MAX_PATH_LENGTH = 512


class MediaService:
    """Coordinate image storage, captioning, visual descriptors, and search."""

    def __init__(
        self,
        *,
        repository: MediaRepositoryProtocol,
        captioner: MediaCaptionerProtocol,
        storage: MediaStorageProtocol,
        cache: MediaCacheProtocol,
        max_bytes: int,
    ) -> None:
        self.repository = repository
        self.captioner = captioner
        self.storage = storage
        self.cache = cache
        self.max_bytes = max_bytes

    @staticmethod
    def _to_schema(media: MediaModel) -> MediaSchema:
        return MediaSchema(
            media_id=media.id,
            raw_file_path=media.raw_file_path,
            file_name=media.file_name,
            mime_type=media.mime_type,
            size_bytes=media.size_bytes,
            width=media.width,
            height=media.height,
            caption=media.caption,
            ocr_text=media.ocr_text,
            title=media.title,
            summary=media.summary,
            document_type=media.document_type,
            tags=list(media.tags),
            update_time=media.updated_at,
            created_at=media.created_at,
        )

    @staticmethod
    def _normalize_path(path: str) -> str:
        value = path.strip()
        if not value.startswith("/"):
            raise InvalidMediaPathError("Media paths must start with '/'.")
        if len(value) > MAX_PATH_LENGTH:
            raise InvalidMediaPathError("Media path is too long.")
        if "\\" in value or ".." in value.split("/"):
            raise InvalidMediaPathError("Traversal segments are not allowed.")
        if value.endswith("/"):
            raise InvalidMediaPathError("Media path must include a file name.")
        return value

    @staticmethod
    def _normalize_mime(mime_type: str | None, path: str) -> str:
        candidate = (mime_type or "").lower().split(";")[0].strip()
        if candidate in ALLOWED_MIME_TYPES:
            return "image/jpeg" if candidate == "image/jpg" else candidate
        lowered = path.lower()
        if lowered.endswith((".jpg", ".jpeg")):
            return "image/jpeg"
        if lowered.endswith(".png"):
            return "image/png"
        if lowered.endswith(".webp"):
            return "image/webp"
        raise UnsupportedMediaTypeError(candidate)

    async def _caption(
        self,
        *,
        data: bytes,
        mime_type: str,
        file_name: str,
        caption: str | None,
        tags: list[str],
    ) -> MediaCaption:
        cleaned_caption = (caption or "").strip()
        cleaned_tags = [tag.strip() for tag in tags if tag.strip()]
        stem = file_name.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
        if cleaned_caption:
            return MediaCaption(
                caption=cleaned_caption,
                ocr_text="",
                title=stem,
                summary=cleaned_caption,
                document_type="other",
                tags=cleaned_tags,
            )
        if self.captioner.configured:
            try:
                generated = await self.captioner.caption(data, mime_type)
                return MediaCaption(
                    caption=generated.caption,
                    ocr_text=generated.ocr_text,
                    title=generated.title,
                    summary=generated.summary,
                    document_type=generated.document_type,
                    tags=list(dict.fromkeys([*cleaned_tags, *generated.tags])),
                )
            except MediaCaptionFailedError as exc:
                logger.warning("Image captioning failed; using the file name: %s", exc)
        return MediaCaption(
            caption=f"{stem} image",
            ocr_text="",
            title=stem,
            summary="",
            document_type="other",
            tags=cleaned_tags,
        )

    async def create(
        self,
        *,
        data: bytes,
        mime_type: str | None,
        path: str | None,
        caption: str | None,
        tags: list[str],
    ) -> MediaSchema:
        """Store an image, caption it, and index its caption/tags."""
        if len(data) > self.max_bytes:
            raise MediaTooLargeError(len(data), self.max_bytes)
        candidate_path = path.strip() if path and path.strip() else ""
        if candidate_path:
            normalized_path = self._normalize_path(candidate_path)
            normalized_mime = self._normalize_mime(mime_type, normalized_path)
        else:
            normalized_mime = self._normalize_mime(mime_type, "")
            extension = MIME_EXTENSIONS[normalized_mime]
            normalized_path = f"/media/{uuid4().hex}{extension}"
        try:
            features = extract_visual_features(data)
        except InvalidImageError as exc:
            raise UnsupportedMediaTypeError(normalized_mime) from exc

        file_name = normalized_path.rsplit("/", 1)[-1]
        existing = await self.repository.get_current_by_path(normalized_path)
        if existing is not None:
            await self.repository.mark_not_current(existing)
        caption_result = await self._caption(
            data=data,
            mime_type=normalized_mime,
            file_name=file_name,
            caption=caption,
            tags=tags,
        )
        storage_key = (
            f"media/{uuid4().hex[:2]}/{uuid4().hex}{MIME_EXTENSIONS[normalized_mime]}"
        )
        await self.storage.save(storage_key, data)
        try:
            indexed_text = " ".join(
                [
                    caption_result.caption,
                    caption_result.ocr_text,
                    caption_result.title,
                    caption_result.summary,
                    *caption_result.tags,
                ]
            ).strip()
            media = await self.repository.add(
                MediaModel(
                    raw_file_path=normalized_path,
                    file_name=file_name,
                    mime_type=normalized_mime,
                    size_bytes=len(data),
                    width=features.width,
                    height=features.height,
                    content_hash=hashlib.sha256(data).hexdigest(),
                    storage_key=storage_key,
                    caption=caption_result.caption,
                    ocr_text=caption_result.ocr_text,
                    title=caption_result.title,
                    summary=caption_result.summary,
                    document_type=caption_result.document_type,
                    tags=caption_result.tags,
                    token_count=count_terms(indexed_text),
                    visual_embedding=features.vector,
                    embedding_model=MODEL_NAME,
                    perceptual_hash=features.perceptual_hash,
                    is_current=True,
                )
            )
            await self.repository.add_ngrams(media.id, dict(term_frequencies(indexed_text)))
            await self.cache.bump_version()
            return self._to_schema(media)
        except Exception:
            await self.storage.delete(storage_key)
            raise

    async def list_media(self, *, limit: int, offset: int) -> list[MediaSchema]:
        media = await self.repository.list_recent(limit=limit, offset=offset)
        return [self._to_schema(item) for item in media]

    async def count(self) -> int:
        return await self.repository.count()

    async def get(self, media_id: int) -> MediaSchema:
        media = await self.repository.get_by_id(media_id)
        if media is None or media.deleted_at is not None:
            raise MediaNotFoundError(media_id)
        return self._to_schema(media)

    async def content(self, media_id: int) -> tuple[bytes, str, str]:
        media = await self.repository.get_by_id(media_id)
        if media is None or media.deleted_at is not None:
            raise MediaNotFoundError(media_id)
        data = await self.storage.read(media.storage_key)
        return data, media.mime_type, media.file_name

    async def delete(self, media_id: int) -> None:
        media = await self.repository.get_by_id(media_id)
        if media is None or media.deleted_at is not None:
            raise MediaNotFoundError(media_id)
        now = datetime.now(UTC)
        media.is_current = False
        media.deleted_at = now
        await self.repository.save(media)
        await self.cache.bump_version()

    async def search_text(self, *, query: str, limit: int) -> MediaSearchResponseSchema:
        cleaned = " ".join(query.split())
        terms = unique_query_terms(cleaned)
        if not terms:
            raise InvalidMediaQueryError("query contains no searchable terms.")
        started = time.perf_counter()
        candidates = await self.repository.text_candidates(terms, limit=limit)
        media_by_id = {
            media.id: media
            for media in await self.repository.list_by_ids(
                [candidate.media_id for candidate in candidates]
            )
        }
        results = [
            MediaSearchResultSchema(
                **self._to_schema(media_by_id[candidate.media_id]).model_dump(),
                score=round(candidate.score, 6),
                matched_by="text",
            )
            for candidate in candidates
            if candidate.media_id in media_by_id
            and media_by_id[candidate.media_id].deleted_at is None
        ]
        return MediaSearchResponseSchema(
            query=cleaned,
            mode="text",
            total=len(results),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            results=results,
        )

    async def search_visual(
        self,
        *,
        data: bytes,
        limit: int,
    ) -> MediaSearchResponseSchema:
        try:
            features = extract_visual_features(data)
        except InvalidImageError as exc:
            raise UnsupportedMediaTypeError("image") from exc
        started = time.perf_counter()
        candidates = await self.repository.visual_candidates(features.vector, limit=limit)
        media_by_id = {
            media.id: media
            for media in await self.repository.list_by_ids(
                [candidate.media_id for candidate in candidates]
            )
        }
        results = [
            MediaSearchResultSchema(
                **self._to_schema(media_by_id[candidate.media_id]).model_dump(),
                score=round(candidate.score, 6),
                matched_by="visual",
            )
            for candidate in candidates
            if candidate.media_id in media_by_id
            and media_by_id[candidate.media_id].deleted_at is None
        ]
        return MediaSearchResponseSchema(
            query=None,
            mode="visual",
            total=len(results),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            results=results,
        )

    async def describe(self, media_id: int) -> MediaSchema:
        if not self.captioner.configured:
            raise MediaNotConfiguredError()
        media = await self.repository.get_by_id(media_id)
        if media is None or media.deleted_at is not None:
            raise MediaNotFoundError(media_id)
        data = await self.storage.read(media.storage_key)
        generated = await self.captioner.caption(data, media.mime_type)
        media.caption = generated.caption
        media.ocr_text = generated.ocr_text
        media.title = generated.title
        media.summary = generated.summary
        media.document_type = generated.document_type
        media.tags = generated.tags
        indexed_text = " ".join(
            [
                generated.caption,
                generated.ocr_text,
                generated.title,
                generated.summary,
                *generated.tags,
            ]
        ).strip()
        media.token_count = count_terms(indexed_text)
        await self.repository.replace_ngrams(
            media.id,
            dict(term_frequencies(indexed_text)),
        )
        await self.repository.save(media)
        await self.cache.bump_version()
        return self._to_schema(media)
