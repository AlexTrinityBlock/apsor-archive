"""Domain errors for custom companions and the companion preference."""


class CompanionError(Exception):
    """Base class for every companion failure."""


class CompanionNotFoundError(CompanionError):
    def __init__(self, companion_id: int) -> None:
        super().__init__(f"Companion {companion_id} was not found.")


class CompanionFrameNotFoundError(CompanionError):
    def __init__(self, frame_id: int) -> None:
        super().__init__(f"Companion frame {frame_id} was not found.")


class CompanionLimitError(CompanionError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"An account can have at most {limit} companions.")


class CompanionFrameLimitError(CompanionError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"An action can have at most {limit} frames.")


class CompanionFrameTooLargeError(CompanionError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"Each companion image must be at most {limit} bytes.")


class CompanionFrameUnsupportedError(CompanionError):
    def __init__(self) -> None:
        super().__init__(
            "Companion images must be still PNG, JPEG, or WebP files within the size limits."
        )


class CompanionInvalidError(CompanionError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class CompanionStorageError(CompanionError):
    def __init__(self) -> None:
        super().__init__("Companion image storage is unavailable.")


__all__ = [
    "CompanionError",
    "CompanionFrameLimitError",
    "CompanionFrameNotFoundError",
    "CompanionFrameTooLargeError",
    "CompanionFrameUnsupportedError",
    "CompanionInvalidError",
    "CompanionLimitError",
    "CompanionNotFoundError",
    "CompanionStorageError",
]
