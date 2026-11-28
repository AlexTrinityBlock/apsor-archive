"""Render one original into a tiny WebP thumbnail.

Every function here is synchronous and CPU-bound; callers run it on the
bounded extraction executor. A format without a visual returns ``None``; a
candidate that cannot be decoded raises ``ThumbnailRenderError`` with a stable
code. Re-encoding through Pillow also drops EXIF and other metadata.
"""

import warnings
import zipfile
from collections.abc import Callable, Iterable
from io import BytesIO

import pypdfium2 as pdfium
from PIL import Image, ImageOps, UnidentifiedImageError

from app.module.knowledge.domain.thumbnail_domain import (
    IMAGE_THUMBNAIL_EXTENSIONS,
    MAX_EMBEDDED_PREVIEW_BYTES,
    MAX_SOURCE_PIXELS,
    OFFICE_PREVIEW_PARTS,
    OFFICE_THUMBNAIL_EXTENSIONS,
    OPENDOCUMENT_PREVIEW_PARTS,
    OPENDOCUMENT_THUMBNAIL_EXTENSIONS,
    PDF_THUMBNAIL_EXTENSIONS,
    THUMBNAIL_FALLBACK_EDGE,
    THUMBNAIL_HARD_LIMIT_BYTES,
    THUMBNAIL_MAX_EDGE,
    THUMBNAIL_QUALITY_STEPS,
    THUMBNAIL_TARGET_BYTES,
    RenderedThumbnail,
    ThumbnailRenderError,
)
from app.module.knowledge.service.pdfium_lock import PDFIUM_RENDER_LOCK

ThumbnailRenderer = Callable[[bytes, str], RenderedThumbnail | None]

# Render PDF pages a little larger than the thumbnail, then downsample with
# LANCZOS for a sharper result than rendering straight at the target size.
_PDF_RENDER_EDGE = THUMBNAIL_MAX_EDGE * 2
# Embedded previews whose grey levels span no more than this are placeholders.
BLANK_PREVIEW_RANGE = 6


def render_thumbnail(data: bytes, extension: str) -> RenderedThumbnail | None:
    """Return a WebP thumbnail for ``data`` or ``None`` when it has no visual."""
    ext = extension.lower()
    if ext in IMAGE_THUMBNAIL_EXTENSIONS:
        return _encode(_open_image(data))
    if ext in PDF_THUMBNAIL_EXTENSIONS:
        return _encode(_render_pdf_first_page(data))
    if ext in OFFICE_THUMBNAIL_EXTENSIONS:
        return _encode_embedded(_embedded_preview(data, OFFICE_PREVIEW_PARTS))
    if ext in OPENDOCUMENT_THUMBNAIL_EXTENSIONS:
        return _encode_embedded(_embedded_preview(data, OPENDOCUMENT_PREVIEW_PARTS))
    return None


def _encode_embedded(preview: bytes | None) -> RenderedThumbnail | None:
    """Encode an embedded preview, treating a blank placeholder as no preview.

    Many generators (python-docx/python-pptx templates, some exporters) embed a
    single-colour placeholder ``docProps/thumbnail``. A blank card is worse than
    none: returning ``None`` lets the client render the real first page.
    """
    if preview is None:
        return None
    image = _open_image(preview)
    if _is_blank(image):
        return None
    return _encode(image)


def _is_blank(image: Image.Image) -> bool:
    """True when the image is a near-uniform placeholder."""
    grey = image.convert("L")
    grey.thumbnail((64, 64))
    extrema = grey.getextrema()
    if isinstance(extrema[0], tuple):  # multi-band; cannot happen after "L"
        return False
    return float(extrema[1]) - float(extrema[0]) <= BLANK_PREVIEW_RANGE


def _open_image(data: bytes) -> Image.Image:
    """Decode a still image after a header-only pixel-count check."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            opened = Image.open(BytesIO(data))
            width, height = opened.size
            if width * height > MAX_SOURCE_PIXELS:
                raise ThumbnailRenderError("image_too_large")
            # JPEG draft decoding skips most of the work for large photos.
            opened.draft("RGB", (THUMBNAIL_MAX_EDGE * 2, THUMBNAIL_MAX_EDGE * 2))
            image = ImageOps.exif_transpose(opened)
            image.load()
            return image
    except ThumbnailRenderError:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ThumbnailRenderError("image_too_large") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ThumbnailRenderError("image_unreadable") from exc


def _render_pdf_first_page(data: bytes) -> Image.Image:
    """Render page one under the shared PDFium lock."""
    try:
        with PDFIUM_RENDER_LOCK:
            pdf = pdfium.PdfDocument(data)
            try:
                if len(pdf) == 0:
                    raise ThumbnailRenderError("pdf_empty")
                page = pdf[0]
                try:
                    width, height = page.get_size()
                    longest = max(width, height)
                    if longest <= 0:
                        raise ThumbnailRenderError("pdf_unreadable")
                    bitmap = page.render(scale=_PDF_RENDER_EDGE / longest)
                    image: Image.Image = bitmap.to_pil()
                    image.load()
                finally:
                    page.close()
            finally:
                pdf.close()
    except ThumbnailRenderError:
        raise
    except (pdfium.PdfiumError, OSError, ValueError) as exc:
        raise ThumbnailRenderError("pdf_unreadable") from exc
    return image


def _embedded_preview(data: bytes, parts: Iterable[str]) -> bytes | None:
    """Return the preview image a document writer embedded, if any."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
            for part in parts:
                if part not in names:
                    continue
                info = archive.getinfo(part)
                if info.file_size > MAX_EMBEDDED_PREVIEW_BYTES:
                    raise ThumbnailRenderError("preview_too_large")
                return archive.read(part)
    except ThumbnailRenderError:
        raise
    except (zipfile.BadZipFile, OSError, KeyError, ValueError) as exc:
        raise ThumbnailRenderError("package_unreadable") from exc
    return None


def _has_transparency(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA"):
        low = image.getchannel("A").getextrema()[0]
        return isinstance(low, int | float) and low < 255
    return image.mode == "P" and "transparency" in image.info


def _prepare(image: Image.Image, max_edge: int) -> Image.Image:
    """Shrink and normalize the color mode for WebP."""
    mode = "RGBA" if _has_transparency(image) else "RGB"
    prepared = image.convert(mode) if image.mode != mode else image.copy()
    prepared.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return prepared


def _encode(image: Image.Image) -> RenderedThumbnail:
    """Encode within the byte budget, stepping quality and then size down."""
    best: tuple[bytes, int, int] | None = None
    for edge in (THUMBNAIL_MAX_EDGE, THUMBNAIL_FALLBACK_EDGE):
        prepared = _prepare(image, edge)
        for quality in THUMBNAIL_QUALITY_STEPS:
            buffer = BytesIO()
            prepared.save(buffer, format="WEBP", quality=quality, method=6)
            encoded = buffer.getvalue()
            if best is None or len(encoded) < len(best[0]):
                best = (encoded, prepared.width, prepared.height)
            if len(encoded) <= THUMBNAIL_TARGET_BYTES:
                return RenderedThumbnail(encoded, prepared.width, prepared.height)
    if best is None or len(best[0]) > THUMBNAIL_HARD_LIMIT_BYTES:
        raise ThumbnailRenderError("thumbnail_too_large")
    return RenderedThumbnail(*best)
