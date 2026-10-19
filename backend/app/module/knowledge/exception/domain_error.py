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


class PathNotFoundError(KnowledgeError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Path {path} was not found.")


class FileContentUnavailableError(KnowledgeError):
    def __init__(self, file_id: int) -> None:
        super().__init__(f"File {file_id} has no stored original bytes.")


class UnsupportedFileTypeError(KnowledgeError):
    def __init__(self, extension: str) -> None:
        super().__init__(f"Unsupported file type: {extension or '(none)'}.")


class FileTooLargeError(KnowledgeError):
    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"File size {size} exceeds the {limit}-byte limit.")


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
    def __init__(self, detail: str) -> None:
        super().__init__(f"The AI provider failed: {detail}")


class EmbeddingProviderError(KnowledgeError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"The embedding provider failed: {detail}")


class TreePathConflictError(KnowledgeError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Path {path} is already occupied by a different node kind.")


class IngestJobNotFoundError(KnowledgeError):
    def __init__(self, job_id: int) -> None:
        super().__init__(f"Ingestion job {job_id} was not found.")


class IngestJobConflictError(KnowledgeError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Path {path} already has an active ingestion job.")


class IngestJobNotRetryableError(KnowledgeError):
    def __init__(self, job_id: int, detail: str) -> None:
        super().__init__(f"Ingestion job {job_id} cannot be retried: {detail}")


class DemoAlreadySeededError(KnowledgeError):
    def __init__(self) -> None:
        super().__init__("Demo data can only be seeded into an empty library.")
