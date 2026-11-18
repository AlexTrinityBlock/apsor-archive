"""Domain errors for the knowledge slice."""


class KnowledgeError(Exception):
    """Base class for every knowledge-domain failure."""


class FileRecordNotFoundError(KnowledgeError):
    def __init__(self, file_id: int) -> None:
        super().__init__(f"File {file_id} was not found.")


class MemoryNotFoundError(KnowledgeError):
    def __init__(self, memory_id: int) -> None:
        super().__init__(f"Memory {memory_id} was not found.")


class SummaryNotFoundError(KnowledgeError):
    def __init__(self, summary_id: int) -> None:
        super().__init__(f"Summary {summary_id} was not found.")


class InvalidPathError(KnowledgeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class InvalidProviderConfigError(KnowledgeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ProviderNotFoundError(KnowledgeError):
    def __init__(self, provider_id: int) -> None:
        super().__init__(f"Provider {provider_id} was not found.")


class ProviderNoticeNotFoundError(KnowledgeError):
    def __init__(self, notice_id: int) -> None:
        super().__init__(f"Provider error notice {notice_id} was not found.")


class PathNotFoundError(KnowledgeError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Path {path} was not found.")


class FileContentUnavailableError(KnowledgeError):
    def __init__(self, file_id: int) -> None:
        super().__init__(f"File {file_id} has no stored original bytes.")


class FileStorageUnavailableError(KnowledgeError):
    """The object-storage backend could not be reached.

    The message is deliberately generic; provider, bucket, and credential
    details must never reach an API response or a log record.
    """

    def __init__(self) -> None:
        super().__init__("Object storage is temporarily unavailable.")


class UnsupportedFileTypeError(KnowledgeError):
    def __init__(self, extension: str) -> None:
        super().__init__(f"Unsupported file type: {extension or '(none)'}.")


class FileTooLargeError(KnowledgeError):
    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"File size {size} exceeds the {limit}-byte limit.")


class SpreadsheetArchiveTooLargeError(KnowledgeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class FileVersionConflictError(KnowledgeError):
    def __init__(self, file_id: int, expected_version: int, actual_version: int) -> None:
        super().__init__(
            f"File {file_id} is at version {actual_version}; "
            f"the client expected version {expected_version}."
        )


class EmptyContentError(KnowledgeError):
    def __init__(self) -> None:
        super().__init__("The document contains no extractable text.")


class VisionExtractionError(KnowledgeError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"Vision extraction failed: {detail}")


class TooManyChunksError(KnowledgeError):
    def __init__(self, count: int, limit: int) -> None:
        super().__init__(f"Document produced {count} chunks; the limit is {limit}.")


class InvalidQueryError(KnowledgeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class InvalidChunkWindowError(KnowledgeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class InvalidTimelineRangeError(KnowledgeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class MemoryAlreadyDeprecatedError(KnowledgeError):
    def __init__(self, memory_id: int) -> None:
        super().__init__(f"Memory {memory_id} is already deprecated.")


class MemorySupersedeTargetError(KnowledgeError):
    def __init__(self, memory_id: int) -> None:
        super().__init__(f"Memory {memory_id} cannot be superseded.")


class SummaryNotEnoughMemoriesError(KnowledgeError):
    def __init__(self, count: int, minimum: int) -> None:
        super().__init__(f"Only {count} memories are available; at least {minimum} are required.")


class AiNotConfiguredError(KnowledgeError):
    def __init__(self) -> None:
        super().__init__("No DeepSeek API key is configured for this instance.")


class AiProviderError(KnowledgeError):
    """A chat or extraction provider call that did not produce a usable result.

    The optional fields carry diagnostic context for logs. They never contain
    credentials or prompt content; they describe the transport failure so an
    operator can distinguish a temporary upstream outage from a bad key or an
    invalid request.
    """

    def __init__(
        self,
        detail: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        provider_request_id: str | None = None,
        provider_error_code: str | None = None,
        provider_error_type: str | None = None,
        provider_error_message: str | None = None,
    ) -> None:
        super().__init__(f"The AI provider failed: {detail}")
        self.status_code = status_code
        self.retryable = retryable
        self.provider_request_id = provider_request_id
        self.provider_error_code = provider_error_code
        self.provider_error_type = provider_error_type
        self.provider_error_message = provider_error_message


class AiContextWindowError(AiProviderError):
    """The provider rejected a request because its context was too long."""

    def __init__(self) -> None:
        super().__init__("context window exceeded")


class EmbeddingProviderError(KnowledgeError):
    """An embedding call that did not produce usable vectors.

    ``status_code`` carries the upstream HTTP status when one exists. It never
    contains credentials or input text; callers use it to distinguish an
    authentication failure (401/403, recoverable after a provider refresh) from
    a transient transport error.
    """

    def __init__(self, detail: str, *, status_code: int | None = None) -> None:
        super().__init__(f"The embedding provider failed: {detail}")
        self.status_code = status_code


class EmbeddingUsageLimitExceededError(KnowledgeError):
    """Strict ingestion cannot embed because the account allowance is spent."""

    DETAIL = (
        "The account has reached its embedding token allowance. "
        "Ask the administrator to top it up or reset it."
    )

    def __init__(self) -> None:
        super().__init__(self.DETAIL)


class TreePathConflictError(KnowledgeError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Path {path} is already occupied by a different node kind.")


class FolderCopyTooLargeError(KnowledgeError):
    def __init__(self, files: int, total_bytes: int) -> None:
        super().__init__(
            f"Folder copy needs {files} files / {total_bytes} bytes; "
            "split the folder or copy a smaller subtree."
        )


class IngestJobNotFoundError(KnowledgeError):
    def __init__(self, job_id: int) -> None:
        super().__init__(f"Ingestion job {job_id} was not found.")


class IngestJobConflictError(KnowledgeError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Path {path} already has an active ingestion job.")


class IngestJobNotRetryableError(KnowledgeError):
    def __init__(self, job_id: int, detail: str) -> None:
        super().__init__(f"Ingestion job {job_id} cannot be retried: {detail}")


class InvalidVisionPromptError(KnowledgeError):
    """The submitted vision prompt failed save-time validation."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class IngestSourceStaleError(KnowledgeError):
    """The source file changed or moved before re-ingest publication."""

    def __init__(self, file_id: int) -> None:
        super().__init__(
            f"File {file_id} changed or moved while its re-ingest was running."
        )
