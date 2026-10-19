"""File Library orchestration: multimodal intake, chunk reads, and paths."""

import hashlib
import json
import logging
import mimetypes
import zipfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from uuid import uuid4

import pypdfium2 as pdfium
from docx import Document
from pypdf import PdfReader

from app.module.knowledge.domain.chunking_domain import chunk_text
from app.module.knowledge.domain.path_domain import (
    InvalidPathValueError,
    extension,
    file_name,
    normalize_directory_path,
    normalize_file_path,
    normalize_fuzzy_search,
    parent_directory,
    path_segments,
)
from app.module.knowledge.exception.domain_error import (
    AiProviderError,
    EmptyContentError,
    FileContentUnavailableError,
    FileRecordNotFoundError,
    FileTooLargeError,
    InvalidChunkWindowError,
    InvalidPathError,
    PathNotFoundError,
    TooManyChunksError,
    TreePathConflictError,
    UnsupportedFileTypeError,
    VisionExtractionError,
)
from app.module.knowledge.model.chunk_model import SOURCE_FILE, ChunkModel
from app.module.knowledge.model.file_model import FileModel
from app.module.knowledge.model.tree_model import NODE_KIND_FILE, NODE_KIND_FOLDER, TreeNodeModel
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.chunk_repository_protocol import ChunkRepositoryProtocol
from app.module.knowledge.protocol.file_repository_protocol import FileRepositoryProtocol
from app.module.knowledge.protocol.file_storage_protocol import FileStorageProtocol
from app.module.knowledge.protocol.text_generator_protocol import TextGeneratorProtocol
from app.module.knowledge.protocol.tree_repository_protocol import TreeRepositoryProtocol
from app.module.knowledge.protocol.vision_extractor_protocol import (
    DocumentAnalysis,
    VisionExtractorProtocol,
)
from app.module.knowledge.schema.file_schema import (
    ChunkSchema,
    DirectorySchema,
    FileChunksSchema,
    FileSchema,
    PathFileSchema,
    PathListingSchema,
)
from app.module.knowledge.service.indexer_service import IndexerService
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx"}
TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".csv", ".json", ".log"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS

DOCUMENT_ANALYSIS_PROMPT = (
    "You analyze a document before it enters a personal knowledge library. "
    "Return JSON with the keys: has_meaningful_text (boolean), use_vision "
    "(boolean), document_type (short string such as pdf, docx, text, json, "
    "image, scanned_pdf), title (short string), summary (1 to 2 sentences), tags "
    "(3 to 6 short strings), and language. Set use_vision to true only when the "
    "extracted text is empty, garbled, or clearly not the document's main content "
    "and a vision pass over its pages or images could recover it. For plain text "
    "files use_vision must be false. Do not invent content."
)


@dataclass(frozen=True)
class ExtractedDocument:
    """Text plus structured metadata produced by one extraction pass."""

    text: str
    document_type: str
    extraction_method: str
    ai_summary: str | None
    ai_tags: list[str]


@dataclass(frozen=True)
class FileOriginal:
    """The stored bytes and validators for one file version."""

    data: bytes
    file_name: str
    mime_type: str
    content_hash: str
    updated_at: datetime


class FileService:
    """Coordinate file storage, multimodal extraction, tree placement, and indexing."""

    def __init__(
        self,
        *,
        file_repository: FileRepositoryProtocol,
        tree_repository: TreeRepositoryProtocol,
        chunk_repository: ChunkRepositoryProtocol,
        indexer: IndexerService,
        storage: FileStorageProtocol,
        cache: CacheProtocol,
        text_generator: TextGeneratorProtocol,
        vision_extractor: VisionExtractorProtocol,
        target_chars: int,
        overlap_chars: int,
        max_chunks: int,
        max_upload_bytes: int,
        max_text_bytes: int,
        vision_max_pages: int,
        pdf_text_threshold: int,
    ) -> None:
        self.file_repository = file_repository
        self.tree_repository = tree_repository
        self.chunk_repository = chunk_repository
        self.indexer = indexer
        self.storage = storage
        self.cache = cache
        self.text_generator = text_generator
        self.vision_extractor = vision_extractor
        self.target_chars = target_chars
        self.overlap_chars = overlap_chars
        self.max_chunks = max_chunks
        self.max_upload_bytes = max_upload_bytes
        self.max_text_bytes = max_text_bytes
        self.vision_max_pages = vision_max_pages
        self.pdf_text_threshold = pdf_text_threshold

    @staticmethod
    def _to_schema(file: FileModel) -> FileSchema:
        return FileSchema(
            id=file.id,
            raw_file_path=file.raw_file_path,
            file_name=file.file_name,
            extension=file.extension,
            mime_type=file.mime_type,
            size_bytes=file.size_bytes,
            version=file.version,
            supersedes_file_id=file.supersedes_file_id,
            is_current=file.is_current,
            total_chunks=file.total_chunks,
            has_original=file.storage_key is not None,
            ai_summary=file.ai_summary,
            ai_tags=list(file.ai_tags),
            document_type=file.document_type,
            extraction_method=file.extraction_method,
            created_at=file.created_at,
            updated_at=file.updated_at,
            deleted_at=file.deleted_at,
        )

    @staticmethod
    def _path_file_schema(file: FileModel) -> PathFileSchema:
        return PathFileSchema(
            file_id=file.id,
            raw_file_path=file.raw_file_path,
            file_name=file.file_name,
            total_chunks=file.total_chunks,
            size_bytes=file.size_bytes,
            update_time=file.updated_at,
        )

    @staticmethod
    def _normalized_path(raw: str) -> str:
        try:
            return normalize_file_path(raw)
        except InvalidPathValueError as exc:
            raise InvalidPathError(str(exc)) from exc

    @staticmethod
    def _normalized_directory(raw: str) -> str:
        try:
            normalized = normalize_directory_path(raw)
        except InvalidPathValueError as exc:
            raise InvalidPathError(str(exc)) from exc
        if normalized == "/":
            raise InvalidPathError("A folder path must include a folder name.")
        return normalized

    @staticmethod
    def _directory_schema(node: TreeNodeModel) -> DirectorySchema:
        return DirectorySchema(path=node.path, name=node.name, depth=node.depth)

    @staticmethod
    def _new_storage_key(suffix: str) -> str:
        return f"files/{uuid4().hex[:2]}/{uuid4().hex}{suffix}"

    @staticmethod
    def _decode_text(data: bytes) -> str:
        if b"\x00" in data[:8192]:
            raise EmptyContentError()
        for encoding in ("utf-8", "utf-8-sig", "big5"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("latin-1")

    @staticmethod
    def _heuristic_analysis(
        text: str,
        *,
        file_name_value: str,
        document_type: str,
    ) -> DocumentAnalysis:
        cleaned = text.strip()
        return DocumentAnalysis(
            has_meaningful_text=len(cleaned) >= 40,
            use_vision=False,
            document_type=document_type,
            title=file_name_value,
            summary=cleaned[:240],
            tags=[],
            language="",
        )

    async def _analyze_text(
        self,
        text: str,
        *,
        file_name_value: str,
        document_type: str,
    ) -> DocumentAnalysis:
        """Use structured AI output to judge whether the text is usable."""
        if not self.text_generator.configured or not text.strip():
            return self._heuristic_analysis(
                text,
                file_name_value=file_name_value,
                document_type=document_type,
            )
        user_prompt = (
            f"Filename: {file_name_value}\n"
            f"Declared type: {document_type}\n"
            f"Extracted text sample:\n{text[:5000]}"
        )
        try:
            completion = await self.text_generator.complete_json(
                DOCUMENT_ANALYSIS_PROMPT,
                user_prompt,
            )
            body = json.loads(completion.text)
        except (AiProviderError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Document analysis failed; using heuristics: %s", exc)
            return self._heuristic_analysis(
                text,
                file_name_value=file_name_value,
                document_type=document_type,
            )
        raw_tags = body.get("tags")
        tags = (
            [str(tag).strip() for tag in raw_tags if str(tag).strip()]
            if isinstance(raw_tags, list)
            else []
        )
        return DocumentAnalysis(
            has_meaningful_text=bool(
                body.get("has_meaningful_text", len(text.strip()) >= 40)
            ),
            use_vision=bool(body.get("use_vision", False)),
            document_type=str(body.get("document_type") or document_type),
            title=str(body.get("title") or file_name_value),
            summary=str(body.get("summary") or text[:240]),
            tags=tags[:6],
            language=str(body.get("language") or ""),
        )

    async def _vision_pdf(self, data: bytes) -> tuple[str, str | None, list[str], str]:
        """Render up to N PDF pages and OCR them with the vision provider."""
        texts: list[str] = []
        summary: str | None = None
        tags: list[str] = []
        document_type = "scanned_pdf"
        try:
            pdf = pdfium.PdfDocument(data)
            page_count = min(len(pdf), self.vision_max_pages)
            for index in range(page_count):
                page = pdf[index]
                bitmap = page.render(scale=2.0)
                image = bitmap.to_pil()
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                vision = await self.vision_extractor.extract(buffer.getvalue(), "image/png")
                if vision.text.strip():
                    texts.append(vision.text.strip())
                elif vision.caption.strip():
                    texts.append(vision.caption.strip())
                summary = summary or vision.summary or None
                tags.extend(vision.tags)
                document_type = vision.document_type or document_type
            pdf.close()
        except VisionExtractionError:
            raise
        except Exception as exc:
            raise EmptyContentError() from exc
        return "\n\n".join(texts).strip(), summary, list(dict.fromkeys(tags))[:8], document_type

    @staticmethod
    def _docx_text(data: bytes) -> str:
        document = Document(BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        return "\n".join(parts)

    @staticmethod
    def _docx_images(data: bytes) -> list[tuple[bytes, str]]:
        images: list[tuple[bytes, str]] = []
        with zipfile.ZipFile(BytesIO(data)) as archive:
            for name in archive.namelist():
                if not name.startswith("word/media/"):
                    continue
                suffix = extension(name)
                if suffix not in IMAGE_EXTENSIONS:
                    continue
                mime = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                }[suffix]
                images.append((archive.read(name), mime))
        return images

    async def _vision_images(
        self,
        images: list[tuple[bytes, str]],
    ) -> tuple[str, str | None, list[str], str]:
        texts: list[str] = []
        summary: str | None = None
        tags: list[str] = []
        document_type = "docx"
        for data, mime_type in images[: self.vision_max_pages]:
            vision = await self.vision_extractor.extract(data, mime_type)
            if vision.text.strip():
                texts.append(vision.text.strip())
            elif vision.caption.strip():
                texts.append(vision.caption.strip())
            summary = summary or vision.summary or None
            tags.extend(vision.tags)
            document_type = vision.document_type or document_type
        return "\n\n".join(texts).strip(), summary, list(dict.fromkeys(tags))[:8], document_type

    async def _extract_document(self, path: str, data: bytes) -> ExtractedDocument:
        """Extract text; use vision when text is absent or AI says it is needed."""
        suffix = extension(path)
        file_name_value = file_name(path)
        if suffix in TEXT_EXTENSIONS:
            text = self._decode_text(data)
            analysis = await self._analyze_text(
                text,
                file_name_value=file_name_value,
                document_type=suffix.lstrip(".") or "text",
            )
            return ExtractedDocument(
                text=text,
                document_type=analysis.document_type,
                extraction_method="text",
                ai_summary=analysis.summary or None,
                ai_tags=analysis.tags,
            )
        if suffix == ".pdf":
            try:
                reader = PdfReader(BytesIO(data))
                pages = [page.extract_text() or "" for page in reader.pages]
                text = "\n\n".join(page for page in pages if page.strip())
            except Exception:
                text = ""
            analysis = await self._analyze_text(
                text,
                file_name_value=file_name_value,
                document_type="pdf",
            )
            needs_vision = (
                not analysis.has_meaningful_text
                or analysis.use_vision
                or len(text.strip()) < self.pdf_text_threshold
            )
            if needs_vision and self.vision_extractor.configured:
                vision_text, summary, tags, document_type = await self._vision_pdf(data)
                combined = "\n\n".join(part for part in (text.strip(), vision_text) if part)
                if not combined:
                    raise EmptyContentError()
                return ExtractedDocument(
                    text=combined,
                    document_type=document_type or "scanned_pdf",
                    extraction_method="mixed" if text.strip() else "vision",
                    ai_summary=summary or analysis.summary or None,
                    ai_tags=list(dict.fromkeys([*analysis.tags, *tags]))[:8],
                )
            if not text.strip():
                raise EmptyContentError()
            return ExtractedDocument(
                text=text,
                document_type=analysis.document_type,
                extraction_method="text",
                ai_summary=analysis.summary or None,
                ai_tags=analysis.tags,
            )
        if suffix == ".docx":
            try:
                text = self._docx_text(data)
            except Exception as exc:
                raise EmptyContentError() from exc
            analysis = await self._analyze_text(
                text,
                file_name_value=file_name_value,
                document_type="docx",
            )
            if (
                (not analysis.has_meaningful_text or analysis.use_vision)
                and self.vision_extractor.configured
            ):
                images = self._docx_images(data)
                if images:
                    vision_text, summary, tags, document_type = await self._vision_images(
                        images
                    )
                    combined = "\n\n".join(
                        part for part in (text.strip(), vision_text) if part
                    )
                    if combined:
                        return ExtractedDocument(
                            text=combined,
                            document_type=document_type or "docx",
                            extraction_method="mixed" if text.strip() else "vision",
                            ai_summary=summary or analysis.summary or None,
                            ai_tags=list(dict.fromkeys([*analysis.tags, *tags]))[:8],
                        )
            if not text.strip():
                raise EmptyContentError()
            return ExtractedDocument(
                text=text,
                document_type=analysis.document_type,
                extraction_method="text",
                ai_summary=analysis.summary or None,
                ai_tags=analysis.tags,
            )
        if suffix in IMAGE_EXTENSIONS:
            if not self.vision_extractor.configured:
                raise VisionExtractionError(
                    "Image ingestion requires a vision-capable chat provider."
                )
            vision = await self.vision_extractor.extract(
                data,
                {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                }[suffix],
            )
            text = vision.text.strip() or vision.caption.strip()
            if not text:
                raise EmptyContentError()
            return ExtractedDocument(
                text=text,
                document_type=vision.document_type or "image",
                extraction_method="vision",
                ai_summary=vision.summary or None,
                ai_tags=vision.tags,
            )
        raise UnsupportedFileTypeError(suffix)

    async def _ensure_folder_chain(self, directory: str) -> TreeNodeModel | None:
        """Create every missing folder in ``directory`` and return the leaf folder."""
        parent_id: int | None = None
        current: TreeNodeModel | None = None
        segments = path_segments(directory)
        for index, segment in enumerate(segments, start=1):
            directory_path = "/" + "/".join(segments[:index])
            node = await self.tree_repository.get_current_by_path(directory_path)
            if node is None:
                node = await self.tree_repository.add(
                    TreeNodeModel(
                        parent_id=parent_id,
                        path=directory_path,
                        name=segment,
                        kind=NODE_KIND_FOLDER,
                        depth=index,
                    )
                )
            elif node.kind != NODE_KIND_FOLDER:
                raise TreePathConflictError(directory_path)
            parent_id = node.id
            current = node
        return current

    async def _ensure_parent_folder(self, path: str) -> int | None:
        node = await self._ensure_folder_chain(parent_directory(path))
        return node.id if node is not None else None

    async def _ingest(
        self,
        *,
        path: str,
        data: bytes,
        text: str,
        mime_type: str,
        storage_key: str | None,
        occurred_at: datetime | None,
        ai_summary: str | None = None,
        ai_tags: list[str] | None = None,
        document_type: str = "text",
        extraction_method: str = "text",
    ) -> FileSchema:
        drafts = chunk_text(
            text,
            target_chars=self.target_chars,
            overlap_chars=self.overlap_chars,
        )
        if not drafts:
            raise EmptyContentError()
        if len(drafts) > self.max_chunks:
            raise TooManyChunksError(len(drafts), self.max_chunks)

        existing = await self.file_repository.get_current_by_path(path)
        existing_node = await self.tree_repository.get_current_by_path(path)
        if existing_node is not None and existing_node.kind != NODE_KIND_FILE:
            raise TreePathConflictError(path)

        if existing is not None:
            await self.file_repository.mark_not_current(existing)
            await self.chunk_repository.mark_source_not_current(SOURCE_FILE, existing.id)
        if existing_node is not None:
            await self.tree_repository.mark_not_current(existing_node)

        timestamp = occurred_at or utcnow()
        file = await self.file_repository.add(
            FileModel(
                raw_file_path=path,
                file_name=file_name(path),
                extension=extension(path),
                mime_type=mime_type,
                size_bytes=len(data),
                content_hash=hashlib.sha256(data).hexdigest(),
                storage_key=storage_key,
                ai_summary=ai_summary,
                ai_tags=ai_tags or [],
                document_type=document_type,
                extraction_method=extraction_method,
                version=existing.version + 1 if existing is not None else 1,
                supersedes_file_id=existing.id if existing is not None else None,
                is_current=True,
                total_chunks=len(drafts),
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

        parent_id = await self._ensure_parent_folder(path)
        node = await self.tree_repository.add(
            TreeNodeModel(
                parent_id=parent_id,
                path=path,
                name=file_name(path),
                kind=NODE_KIND_FILE,
                file_id=file.id,
                depth=len(path_segments(path)),
            )
        )
        if existing_node is not None:
            await self.tree_repository.mark_not_current(
                existing_node,
                superseded_by_id=node.id,
            )

        await self.indexer.index_chunks(
            source_kind=SOURCE_FILE,
            source_id=file.id,
            drafts=drafts,
        )
        await self.cache.bump_version()
        return self._to_schema(file)

    async def ingest_text(
        self,
        *,
        path: str,
        content: str,
        occurred_at: datetime | None = None,
    ) -> FileSchema:
        """Create or version a text file and index it."""
        normalized = self._normalized_path(path)
        encoded = content.encode("utf-8")
        if len(encoded) > self.max_text_bytes:
            raise FileTooLargeError(len(encoded), self.max_text_bytes)
        mime_type = mimetypes.guess_type(normalized)[0] or "text/plain"
        return await self._ingest(
            path=normalized,
            data=encoded,
            text=content,
            mime_type=mime_type,
            storage_key=None,
            occurred_at=occurred_at,
            document_type=extension(normalized).lstrip(".") or "text",
            extraction_method="text",
        )

    async def ingest_upload(
        self,
        *,
        path: str,
        data: bytes,
        content_type: str | None,
        occurred_at: datetime | None = None,
    ) -> FileSchema:
        """Create or version an uploaded file and index its extracted text."""
        normalized = self._normalized_path(path)
        suffix = extension(normalized)
        if suffix not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(suffix)
        if len(data) > self.max_upload_bytes:
            raise FileTooLargeError(len(data), self.max_upload_bytes)

        extracted = await self._extract_document(normalized, data)
        mime_type = (
            content_type
            or mimetypes.guess_type(normalized)[0]
            or "application/octet-stream"
        )
        storage_key = self._new_storage_key(suffix)
        await self.storage.save(storage_key, data)
        try:
            return await self._ingest(
                path=normalized,
                data=data,
                text=extracted.text,
                mime_type=mime_type,
                storage_key=storage_key,
                occurred_at=occurred_at,
                ai_summary=extracted.ai_summary,
                ai_tags=extracted.ai_tags,
                document_type=extracted.document_type,
                extraction_method=extracted.extraction_method,
            )
        except Exception:
            await self.storage.delete(storage_key)
            raise

    async def create_folder(self, path: str) -> DirectorySchema:
        """Create one folder plus missing ancestors, idempotently."""
        normalized = self._normalized_directory(path)
        occupied_file = await self.file_repository.get_current_by_path(normalized)
        if occupied_file is not None:
            raise TreePathConflictError(normalized)
        existing = await self.tree_repository.get_current_by_path(normalized)
        if existing is not None:
            if existing.kind != NODE_KIND_FOLDER:
                raise TreePathConflictError(normalized)
            return self._directory_schema(existing)

        node = await self._ensure_folder_chain(normalized)
        if node is None:  # pragma: no cover - the root path is rejected above
            raise InvalidPathError("A folder path must include a folder name.")
        await self.cache.bump_version()
        return self._directory_schema(node)

    async def _require_current_file(self, file_id: int) -> FileModel:
        file = await self.file_repository.get_by_id(file_id)
        if file is None or file.deleted_at is not None or not file.is_current:
            raise FileRecordNotFoundError(file_id)
        return file

    @staticmethod
    def _target_file_path(file: FileModel, raw: str) -> str:
        target = FileService._normalized_path(raw)
        if extension(target) != file.extension:
            raise InvalidPathError(
                "A moved or copied file must keep its original extension."
            )
        return target

    async def _target_is_occupied(self, path: str) -> bool:
        node = await self.tree_repository.get_current_by_path(path)
        if node is not None:
            return True
        return await self.file_repository.get_current_by_path(path) is not None

    def _merge_chunk_contents(self, chunks: list[ChunkModel]) -> str:
        """Rebuild text by removing the known overlap between adjacent chunks."""
        contents = [chunk.content for chunk in chunks if chunk.is_current]
        if not contents:
            return ""
        merged = contents[0]
        for content in contents[1:]:
            if not content:
                continue
            max_overlap = min(self.overlap_chars, len(merged), len(content))
            overlap = 0
            for size in range(max_overlap, 0, -1):
                if merged.endswith(content[:size]):
                    overlap = size
                    break
            if overlap:
                merged += content[overlap:]
                continue
            separator = (
                ""
                if merged.endswith(("\n", " ")) or content.startswith(("\n", " "))
                else "\n"
            )
            merged = f"{merged}{separator}{content}"
        return merged

    async def move_file(self, file_id: int, *, path: str) -> FileSchema:
        """Move one current file in place, preserving its identity and chunks."""
        file = await self._require_current_file(file_id)
        target = self._target_file_path(file, path)
        if target == file.raw_file_path:
            return self._to_schema(file)
        if await self._target_is_occupied(target):
            raise TreePathConflictError(target)

        parent_id = await self._ensure_parent_folder(target)
        old_node = await self.tree_repository.get_current_by_path(file.raw_file_path)
        if old_node is not None and (
            old_node.kind != NODE_KIND_FILE or old_node.file_id != file.id
        ):
            old_node = None

        name = file_name(target)
        depth = len(path_segments(target))
        await self.file_repository.update_location(file, path=target, file_name=name)
        if old_node is None:
            await self.tree_repository.add(
                TreeNodeModel(
                    parent_id=parent_id,
                    path=target,
                    name=name,
                    kind=NODE_KIND_FILE,
                    file_id=file.id,
                    depth=depth,
                )
            )
        else:
            await self.tree_repository.update_location(
                old_node,
                parent_id=parent_id,
                path=target,
                name=name,
                depth=depth,
            )
        await self.cache.bump_version()
        return self._to_schema(file)

    async def copy_file(self, file_id: int, *, path: str) -> FileSchema:
        """Copy one current file into a new file record with fresh chunks."""
        source = await self._require_current_file(file_id)
        target = self._target_file_path(source, path)
        if await self._target_is_occupied(target):
            raise TreePathConflictError(target)

        chunks = await self.chunk_repository.get_source_chunks(SOURCE_FILE, source.id)
        text = self._merge_chunk_contents(chunks)
        if not text.strip():
            raise EmptyContentError()

        storage_key: str | None = None
        if source.storage_key is not None:
            data = await self.storage.read(source.storage_key)
            storage_key = self._new_storage_key(source.extension)
            await self.storage.save(storage_key, data)
        else:
            data = text.encode("utf-8")

        try:
            return await self._ingest(
                path=target,
                data=data,
                text=text,
                mime_type=source.mime_type,
                storage_key=storage_key,
                occurred_at=None,
                ai_summary=source.ai_summary,
                ai_tags=list(source.ai_tags),
                document_type=source.document_type,
                extraction_method=source.extraction_method,
            )
        except Exception:
            if storage_key is not None:
                await self.storage.delete(storage_key)
            raise

    async def get_file(self, file_id: int) -> FileSchema:
        file = await self.file_repository.get_by_id(file_id)
        if file is None:
            raise FileRecordNotFoundError(file_id)
        return self._to_schema(file)

    async def read_chunks(
        self,
        file_id: int,
        *,
        chunk: int,
        chunk_range: int,
    ) -> FileChunksSchema:
        if chunk < 1:
            raise InvalidChunkWindowError("chunk must be at least 1.")
        if chunk_range < 0 or chunk_range > 25:
            raise InvalidChunkWindowError("chunk_range must be between 0 and 25.")
        file = await self.file_repository.get_by_id(file_id)
        if file is None:
            raise FileRecordNotFoundError(file_id)
        if file.total_chunks == 0:
            raise InvalidChunkWindowError("This file has no chunks.")
        if chunk > file.total_chunks:
            raise InvalidChunkWindowError(
                f"chunk {chunk} exceeds the file's {file.total_chunks} chunks."
            )
        start = max(1, chunk - chunk_range)
        end = min(file.total_chunks, chunk + chunk_range)
        chunks = await self.chunk_repository.get_chunk_window(
            SOURCE_FILE,
            file_id,
            start,
            end,
        )
        return FileChunksSchema(
            file_id=file.id,
            raw_file_path=file.raw_file_path,
            file_name=file.file_name,
            update_time=file.updated_at,
            total_chunks=file.total_chunks,
            chunk_start=start,
            chunk_end=end,
            chunks=[
                ChunkSchema(
                    chunk=item.chunk_index,
                    content=item.content,
                    char_count=item.char_count,
                    token_count=item.token_count,
                    is_current=item.is_current,
                )
                for item in chunks
            ],
        )

    async def list_path(
        self,
        *,
        path: str,
        path_depth: int,
        fuzzy_search: str | None,
    ) -> PathListingSchema:
        try:
            normalized = normalize_directory_path(path)
            fuzzy = normalize_fuzzy_search(fuzzy_search)
        except InvalidPathValueError as exc:
            raise InvalidPathError(str(exc)) from exc
        if path_depth < 1 or path_depth > 10:
            raise InvalidPathError("path_depth must be between 1 and 10.")

        if fuzzy is not None:
            files = await self.file_repository.search_paths(normalized, fuzzy, 50)
            return PathListingSchema(
                path=normalized,
                fuzzy_search=fuzzy,
                directories=[],
                files=[self._path_file_schema(file) for file in files],
            )

        folder = None if normalized == "/" else await self.tree_repository.get_current_by_path(
            normalized
        )
        if normalized != "/" and (folder is None or folder.kind != NODE_KIND_FOLDER):
            raise PathNotFoundError(normalized)

        if path_depth == 1 and folder is None:
            nodes = await self.tree_repository.get_current_children(None)
        elif path_depth == 1:
            if folder is None:
                raise PathNotFoundError(normalized)
            nodes = await self.tree_repository.get_current_children(folder.id)
        else:
            nodes = await self.tree_repository.list_nodes(
                root_path=normalized,
                root_depth=folder.depth if folder is not None else 0,
                max_depth=path_depth,
                include_history=False,
                limit=1000,
            )

        directories = [
            DirectorySchema(
                path=node.path,
                name=node.name,
                depth=node.depth,
            )
            for node in nodes
            if node.kind == NODE_KIND_FOLDER and node.path != normalized
        ]
        files = await self.file_repository.list_files_in_directory(normalized)
        return PathListingSchema(
            path=normalized,
            fuzzy_search=None,
            directories=directories,
            files=[self._path_file_schema(file) for file in files],
        )

    async def delete_file(self, file_id: int) -> None:
        file = await self.file_repository.get_by_id(file_id)
        if file is None or file.deleted_at is not None:
            raise FileRecordNotFoundError(file_id)
        now = utcnow()
        file.is_current = False
        file.deleted_at = now
        file.updated_at = now
        node = await self.tree_repository.get_current_by_path(file.raw_file_path)
        if node is not None and node.file_id == file.id:
            await self.tree_repository.mark_deleted(node)
        await self.chunk_repository.mark_source_not_current(SOURCE_FILE, file.id)
        await self.cache.bump_version()

    async def download(self, file_id: int) -> tuple[bytes, str, str]:
        original = await self.read_original(file_id)
        return original.data, original.file_name, original.mime_type

    async def read_original(self, file_id: int) -> FileOriginal:
        """Load the stored original for inline viewing or attachment download.

        Text created through ``POST /files/text`` has no stored original; its
        content is only available through the indexed chunks. That case keeps
        the existing ``file_content_unavailable`` domain error so callers can
        fall back explicitly instead of receiving an empty body.
        """
        file = await self.file_repository.get_by_id(file_id)
        if file is None:
            raise FileRecordNotFoundError(file_id)
        if not file.storage_key:
            raise FileContentUnavailableError(file_id)
        data = await self.storage.read(file.storage_key)
        return FileOriginal(
            data=data,
            file_name=file.file_name,
            mime_type=file.mime_type,
            content_hash=file.content_hash,
            updated_at=file.updated_at,
        )
