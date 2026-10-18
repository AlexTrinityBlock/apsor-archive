"""Register media-domain errors with the global exception registry."""

from app.module.media.exception.domain_error import (
    InvalidMediaPathError,
    InvalidMediaQueryError,
    MediaCaptionFailedError,
    MediaNotConfiguredError,
    MediaNotFoundError,
    MediaTooLargeError,
    UnsupportedMediaTypeError,
)
from app.shared.exception.registry import ExceptionRegistry


def register_exceptions() -> None:
    ExceptionRegistry.register(MediaNotFoundError, 404, "media_not_found")
    ExceptionRegistry.register(UnsupportedMediaTypeError, 422, "unsupported_media_type")
    ExceptionRegistry.register(MediaTooLargeError, 413, "media_too_large")
    ExceptionRegistry.register(MediaCaptionFailedError, 502, "media_caption_failed")
    ExceptionRegistry.register(InvalidMediaPathError, 422, "invalid_media_path")
    ExceptionRegistry.register(InvalidMediaQueryError, 422, "invalid_media_query")
    ExceptionRegistry.register(MediaNotConfiguredError, 503, "media_not_configured")
