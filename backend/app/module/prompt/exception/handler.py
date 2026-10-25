"""Register prompt-domain errors with the global exception registry."""

from app.module.prompt.exception.domain_error import (
    FrequentPromptNotFoundError,
    InvalidFrequentPromptError,
    TooManyFrequentPromptsError,
)
from app.shared.exception.registry import ExceptionRegistry


def register_prompt_exceptions() -> None:
    """Map prompt errors to HTTP statuses and stable error codes."""
    ExceptionRegistry.register(FrequentPromptNotFoundError, 404, "frequent_prompt_not_found")
    ExceptionRegistry.register(InvalidFrequentPromptError, 422, "invalid_frequent_prompt")
    ExceptionRegistry.register(TooManyFrequentPromptsError, 422, "too_many_frequent_prompts")


__all__ = ["register_prompt_exceptions"]
