"""Media-domain errors."""


class MediaError(Exception):
    """Base class for media failures."""


class MediaNotFoundError(MediaError):
    def __init__(self, media_id: int) -> None:
        super().__init__(f"Media {media_id} was not found.")


class UnsupportedMediaTypeError(MediaError):
    def __init__(self, mime_type: str) -> None:
        super().__init__(f"Unsupported media type: {mime_type or '(unknown)'}.")


class MediaTooLargeError(MediaError):
    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"Media size {size} exceeds the {limit}-byte limit.")


class MediaCaptionFailedError(MediaError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"Image captioning failed: {detail}")


class InvalidMediaPathError(MediaError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class MediaNotConfiguredError(MediaError):
    def __init__(self) -> None:
        super().__init__("No vision-capable chat provider is configured.")


class InvalidMediaQueryError(MediaError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
