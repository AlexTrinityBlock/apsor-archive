"""Pure rules for tiny WebP file thumbnails.

Thumbnails are a fixed-cost preview: the long edge is at most
``THUMBNAIL_MAX_EDGE`` pixels and the encoded WebP aims for
``THUMBNAIL_TARGET_BYTES``. Bump ``GENERATOR_VERSION`` whenever the renderer
output changes so the backfill regenerates older rows.
"""

from dataclasses import dataclass

GENERATOR_VERSION = 2
THUMBNAIL_MAX_EDGE = 320
THUMBNAIL_FALLBACK_EDGE = 224
THUMBNAIL_TARGET_BYTES = 12 * 1024
THUMBNAIL_HARD_LIMIT_BYTES = 32 * 1024
THUMBNAIL_QUALITY_STEPS = (60, 50, 40)
MAX_SOURCE_PIXELS = 40_000_000
MAX_EMBEDDED_PREVIEW_BYTES = 4 * 1024 * 1024
MAX_THUMBNAIL_ATTEMPTS = 3
THUMBNAIL_VERSION_LENGTH = 16

IMAGE_THUMBNAIL_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
PDF_THUMBNAIL_EXTENSIONS = frozenset({".pdf"})
OFFICE_THUMBNAIL_EXTENSIONS = frozenset({".pptx", ".docx", ".xlsx", ".xlsm"})
OPENDOCUMENT_THUMBNAIL_EXTENSIONS = frozenset({".ods"})
THUMBNAIL_EXTENSIONS = (
    IMAGE_THUMBNAIL_EXTENSIONS
    | PDF_THUMBNAIL_EXTENSIONS
    | OFFICE_THUMBNAIL_EXTENSIONS
    | OPENDOCUMENT_THUMBNAIL_EXTENSIONS
)

# Package parts where Office and OpenDocument writers store their own preview.
OFFICE_PREVIEW_PARTS = (
    "docProps/thumbnail.jpeg",
    "docProps/thumbnail.jpg",
    "docProps/thumbnail.png",
)
OPENDOCUMENT_PREVIEW_PARTS = ("Thumbnails/thumbnail.png",)


@dataclass(frozen=True)
class RenderedThumbnail:
    """Encoded WebP bytes and their pixel size."""

    data: bytes
    width: int
    height: int


class ThumbnailRenderError(Exception):
    """A candidate file could not be turned into a thumbnail."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def is_thumbnail_candidate(extension: str) -> bool:
    """Whether a file extension can ever produce a visual thumbnail."""
    return extension.lower() in THUMBNAIL_EXTENSIONS


def thumbnail_version(sha256: str) -> str:
    """Short cache-busting token derived from the thumbnail hash."""
    return sha256[:THUMBNAIL_VERSION_LENGTH]


def fit_within(width: int, height: int, max_edge: int) -> tuple[int, int]:
    """Scale ``width``x``height`` so its long edge is at most ``max_edge``."""
    if width <= 0 or height <= 0:
        raise ValueError("dimensions must be positive")
    longest = max(width, height)
    if longest <= max_edge:
        return width, height
    scale = max_edge / longest
    return max(1, round(width * scale)), max(1, round(height * scale))
