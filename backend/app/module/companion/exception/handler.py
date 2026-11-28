"""Register companion errors with the global exception registry."""

from app.module.companion.exception.domain_error import (
    CompanionFrameLimitError,
    CompanionFrameNotFoundError,
    CompanionFrameTooLargeError,
    CompanionFrameUnsupportedError,
    CompanionInvalidError,
    CompanionLimitError,
    CompanionNotFoundError,
    CompanionStorageError,
)
from app.shared.exception.registry import ExceptionRegistry


def register_exceptions() -> None:
    """Map companion errors to HTTP statuses and stable error codes."""
    ExceptionRegistry.register(CompanionNotFoundError, 404, "companion_not_found")
    ExceptionRegistry.register(CompanionFrameNotFoundError, 404, "companion_frame_not_found")
    ExceptionRegistry.register(CompanionLimitError, 409, "companion_limit")
    ExceptionRegistry.register(CompanionFrameLimitError, 409, "companion_frame_limit")
    ExceptionRegistry.register(CompanionFrameTooLargeError, 413, "companion_frame_too_large")
    ExceptionRegistry.register(
        CompanionFrameUnsupportedError,
        422,
        "companion_frame_unsupported",
    )
    ExceptionRegistry.register(CompanionInvalidError, 422, "companion_invalid")
    ExceptionRegistry.register(CompanionStorageError, 503, "companion_storage_unavailable")


__all__ = ["register_exceptions"]
