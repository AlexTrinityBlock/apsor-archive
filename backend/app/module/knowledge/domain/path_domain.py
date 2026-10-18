"""Path validation and normalization for the File Library."""

import unicodedata

MAX_PATH_LENGTH = 1024
FORBIDDEN_SEGMENTS = {".", ".."}


class InvalidPathValueError(ValueError):
    """Raised when a path cannot be safely normalized."""


def _normalize_common(raw: str) -> str:
    value = unicodedata.normalize("NFC", raw).strip()
    if not value:
        raise InvalidPathValueError("Path must not be empty.")
    if len(value) > MAX_PATH_LENGTH:
        raise InvalidPathValueError(f"Path exceeds {MAX_PATH_LENGTH} characters.")
    if "\\" in value:
        raise InvalidPathValueError("Backslashes are not allowed in paths.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise InvalidPathValueError("Control characters are not allowed in paths.")
    if not value.startswith("/"):
        raise InvalidPathValueError("Paths must start with '/'.")
    if "//" in value:
        raise InvalidPathValueError("Empty path segments are not allowed.")
    return value


def normalize_file_path(raw: str) -> str:
    """Return a canonical file path such as ``/history/industrial/car.md``."""
    value = _normalize_common(raw)
    if value == "/":
        raise InvalidPathValueError("A file path must include a file name.")
    if value.endswith("/"):
        raise InvalidPathValueError("A file path must not end with '/'.")
    segments = value.strip("/").split("/")
    if any(segment in FORBIDDEN_SEGMENTS for segment in segments):
        raise InvalidPathValueError("Traversal segments are not allowed.")
    if any(not segment for segment in segments):
        raise InvalidPathValueError("Empty path segments are not allowed.")
    return value


def normalize_directory_path(raw: str) -> str:
    """Return a canonical directory path; ``/`` is the root."""
    value = _normalize_common(raw)
    if value == "/":
        return value
    value = value.rstrip("/")
    segments = value.strip("/").split("/")
    if any(segment in FORBIDDEN_SEGMENTS for segment in segments):
        raise InvalidPathValueError("Traversal segments are not allowed.")
    if any(not segment for segment in segments):
        raise InvalidPathValueError("Empty path segments are not allowed.")
    return value


def path_segments(path: str) -> list[str]:
    """Split a canonical path into non-empty segments."""
    return [segment for segment in path.split("/") if segment]


def parent_directory(path: str) -> str:
    """Return the parent directory of a canonical file path."""
    segments = path_segments(path)
    if len(segments) <= 1:
        return "/"
    return "/" + "/".join(segments[:-1])


def file_name(path: str) -> str:
    """Return the last segment of a file path."""
    return path_segments(path)[-1]


def extension(path: str) -> str:
    """Return a lower-case extension including the dot, or an empty string."""
    name = file_name(path)
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[1].lower()


def directory_chain(path: str) -> list[str]:
    """Return every ancestor directory, root first."""
    segments = path_segments(path)
    return ["/"] + ["/" + "/".join(segments[:index]) for index in range(1, len(segments))]


def normalize_fuzzy_search(raw: str | None) -> str | None:
    """Trim and bound a fuzzy path query."""
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if len(value) > 120:
        raise InvalidPathValueError("Fuzzy search text exceeds 120 characters.")
    return value
