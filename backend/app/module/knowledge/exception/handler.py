"""Register knowledge-domain errors with the global exception registry."""

from app.module.knowledge.exception.domain_error import (
    AiNotConfiguredError,
    AiProviderError,
    EmbeddingProviderError,
    EmptyContentError,
    FileContentUnavailableError,
    FileRecordNotFoundError,
    FileStorageUnavailableError,
    FileTooLargeError,
    FileVersionConflictError,
    IngestJobConflictError,
    IngestJobNotFoundError,
    IngestJobNotRetryableError,
    InvalidChunkWindowError,
    InvalidPathError,
    InvalidProviderConfigError,
    InvalidQueryError,
    InvalidTimelineRangeError,
    KnowledgeError,
    MemoryAlreadyDeprecatedError,
    MemoryNotFoundError,
    MemorySupersedeTargetError,
    PathNotFoundError,
    ProviderNotFoundError,
    SummaryNotEnoughMemoriesError,
    SummaryNotFoundError,
    TooManyChunksError,
    TreePathConflictError,
    UnsupportedFileTypeError,
    VisionExtractionError,
)
from app.shared.exception.registry import ExceptionRegistry


def register_exceptions() -> None:
    """Map each domain error to an HTTP status and a stable error code."""
    ExceptionRegistry.register(FileRecordNotFoundError, 404, "file_not_found")
    ExceptionRegistry.register(MemoryNotFoundError, 404, "memory_not_found")
    ExceptionRegistry.register(SummaryNotFoundError, 404, "summary_not_found")
    ExceptionRegistry.register(InvalidPathError, 422, "invalid_path")
    ExceptionRegistry.register(InvalidProviderConfigError, 422, "invalid_provider_config")
    ExceptionRegistry.register(ProviderNotFoundError, 404, "provider_not_found")
    ExceptionRegistry.register(PathNotFoundError, 404, "path_not_found")
    ExceptionRegistry.register(FileContentUnavailableError, 404, "file_content_unavailable")
    ExceptionRegistry.register(FileStorageUnavailableError, 503, "storage_unavailable")
    ExceptionRegistry.register(UnsupportedFileTypeError, 422, "unsupported_file_type")
    ExceptionRegistry.register(FileTooLargeError, 413, "file_too_large")
    ExceptionRegistry.register(FileVersionConflictError, 409, "file_version_conflict")
    ExceptionRegistry.register(EmptyContentError, 422, "empty_content")
    ExceptionRegistry.register(VisionExtractionError, 502, "vision_extraction_failed")
    ExceptionRegistry.register(TooManyChunksError, 422, "too_many_chunks")
    ExceptionRegistry.register(InvalidQueryError, 422, "invalid_query")
    ExceptionRegistry.register(InvalidChunkWindowError, 422, "invalid_chunk_window")
    ExceptionRegistry.register(InvalidTimelineRangeError, 422, "invalid_timeline_range")
    ExceptionRegistry.register(MemoryAlreadyDeprecatedError, 409, "memory_already_deprecated")
    ExceptionRegistry.register(MemorySupersedeTargetError, 409, "memory_supersede_target_invalid")
    ExceptionRegistry.register(SummaryNotEnoughMemoriesError, 422, "not_enough_memories")
    ExceptionRegistry.register(AiNotConfiguredError, 503, "ai_not_configured")
    ExceptionRegistry.register(AiProviderError, 502, "ai_provider_error")
    ExceptionRegistry.register(EmbeddingProviderError, 502, "embedding_provider_error")
    ExceptionRegistry.register(TreePathConflictError, 409, "tree_path_conflict")
    ExceptionRegistry.register(IngestJobNotFoundError, 404, "ingest_job_not_found")
    ExceptionRegistry.register(IngestJobConflictError, 409, "ingest_job_conflict")
    ExceptionRegistry.register(IngestJobNotRetryableError, 409, "ingest_job_not_retryable")
    ExceptionRegistry.register(KnowledgeError, 500, "knowledge_error")
