"""Register web-research domain errors with the global exception registry."""

from app.module.web_research.exception.domain_error import (
    WebFetchNotConfiguredError,
    WebProviderAuthenticationError,
    WebProviderError,
    WebSearchNotConfiguredError,
    WebUrlInvalidError,
)
from app.shared.exception.registry import ExceptionRegistry


def register_exceptions() -> None:
    """Map each web-research error to an HTTP status and a stable error code."""
    ExceptionRegistry.register(WebSearchNotConfiguredError, 503, "web_search_not_configured")
    ExceptionRegistry.register(WebFetchNotConfiguredError, 503, "web_fetch_not_configured")
    ExceptionRegistry.register(WebUrlInvalidError, 422, "web_url_invalid")
    ExceptionRegistry.register(
        WebProviderAuthenticationError,
        502,
        "web_provider_authentication_failed",
    )
    ExceptionRegistry.register(WebProviderError, 502, "web_provider_error")
