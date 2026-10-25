"""Domain errors for the prompt slice."""


class FrequentPromptError(Exception):
    """Base class for every frequent-prompt failure."""


class FrequentPromptNotFoundError(FrequentPromptError):
    def __init__(self, prompt_id: int) -> None:
        super().__init__(f"Frequently used prompt {prompt_id} was not found.")


class InvalidFrequentPromptError(FrequentPromptError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class TooManyFrequentPromptsError(FrequentPromptError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"At most {limit} frequently used prompts are allowed.")


__all__ = [
    "FrequentPromptError",
    "FrequentPromptNotFoundError",
    "InvalidFrequentPromptError",
    "TooManyFrequentPromptsError",
]
