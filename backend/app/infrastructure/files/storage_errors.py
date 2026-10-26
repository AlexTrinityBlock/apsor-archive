"""Storage failures with messages safe to return from an API boundary.

The object-storage adapter deliberately discards botocore messages. They can
contain bucket names, endpoint details, and request metadata that should never
reach an API response or a log record. Callers can distinguish a missing object
from a temporarily unavailable backend without inspecting provider errors.
"""


class StorageError(RuntimeError):
    """Base class for file-storage failures."""


class StorageConfigurationError(StorageError):
    """The requested backend is not configured for this process."""

    def __init__(self, detail: str = "Object storage is not configured.") -> None:
        super().__init__(detail)


class StorageObjectMissingError(StorageError):
    """The backend is reachable but the requested object does not exist."""

    def __init__(self) -> None:
        super().__init__("The stored object was not found.")


class StorageUnavailableError(StorageError):
    """The backend could not be reached or rejected the request.

    This includes authentication failures, missing buckets, timeouts, and
    throttling. The message is intentionally generic so credential and
    provider details cannot leak.
    """

    def __init__(self) -> None:
        super().__init__("Object storage is unavailable.")
