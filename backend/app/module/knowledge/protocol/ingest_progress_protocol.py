"""Progress callbacks emitted by the file ingestion pipeline."""

from typing import Protocol


class IngestProgressProtocol(Protocol):
    """Receive coarse progress updates while a job is being processed.

    Implementations must be safe to call from the worker that owns the job.
    The file service only emits milestones (chunk count, file id, embedded
    batches); persistence and throttling stay in the worker.
    """

    async def chunked(self, total: int) -> None: ...

    async def file_created(self, file_id: int) -> None: ...

    async def embedded(self, done: int, total: int) -> None: ...
