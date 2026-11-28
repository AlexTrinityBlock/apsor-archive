"""Decode, sanitize, and re-encode one uploaded companion frame as small AVIF.

The function is synchronous and CPU-bound; the service runs it in a worker
thread. Re-encoding drops EXIF, ICC, XMP, and any other opaque metadata, and the
client-supplied content type is never trusted. AVIF keeps alpha at roughly half
the size of WebP; WebP is the fallback only when the running Pillow build has
no AVIF codec.
"""

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError, features

from app.module.companion.domain.companion_domain import (
    FRAME_MAX_ENCODED_BYTES,
    FRAME_MAX_HEIGHT,
    FRAME_MAX_WIDTH,
    MAX_SOURCE_PIXELS,
)
from app.module.companion.exception.domain_error import CompanionFrameUnsupportedError

_ACCEPTED_FORMATS = frozenset({"PNG", "JPEG", "WEBP", "AVIF"})
_AVIF_QUALITY_STEPS = (60, 52, 44, 36, 28)
_WEBP_QUALITY_STEPS = (82, 72, 62, 52, 42)
# Speed 4 keeps request-time encoding near a few hundred milliseconds for a
# 384x576 frame while staying close to the slower presets' compression.
_AVIF_SPEED = 4
_MIN_EDGE = 48


@dataclass(frozen=True)
class EncodedFrame:
    """One sanitized frame ready for storage."""

    data: bytes
    width: int
    height: int
    mime_type: str


def avif_available() -> bool:
    """Return whether this Pillow build can encode AVIF."""
    return bool(features.check("avif"))


def encode_frame(data: bytes, *, prefer_avif: bool | None = None) -> EncodedFrame:
    """Return a frame that fits 384x576 and the encoded byte budget.

    Transparency is preserved. When the highest quality step is still too large,
    the quality is lowered first and then the image is shrunk until it fits.
    """
    image = _decode(data)
    use_avif = avif_available() if prefer_avif is None else prefer_avif
    if use_avif:
        return _fit(image, "image/avif", _AVIF_QUALITY_STEPS, _encode_avif)
    return _fit(image, "image/webp", _WEBP_QUALITY_STEPS, _encode_webp)


def _decode(data: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(data)) as opened:
            image_format = (opened.format or "").upper()
            if image_format not in _ACCEPTED_FORMATS:
                raise CompanionFrameUnsupportedError()
            if getattr(opened, "is_animated", False):
                raise CompanionFrameUnsupportedError()
            source_width, source_height = opened.size
            if source_width * source_height > MAX_SOURCE_PIXELS:
                raise CompanionFrameUnsupportedError()
            opened.load()
            oriented = ImageOps.exif_transpose(opened)
            has_alpha = oriented.mode in {"RGBA", "LA", "PA"} or (
                oriented.mode == "P" and "transparency" in oriented.info
            )
            image = oriented.convert("RGBA" if has_alpha else "RGB")
    except CompanionFrameUnsupportedError:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise CompanionFrameUnsupportedError() from exc
    image.thumbnail((FRAME_MAX_WIDTH, FRAME_MAX_HEIGHT), Image.Resampling.LANCZOS)
    return image


def _fit(
    image: Image.Image,
    mime_type: str,
    quality_steps: tuple[int, ...],
    encoder: Callable[[Image.Image, int], bytes],
) -> EncodedFrame:
    while True:
        for quality in quality_steps:
            encoded = encoder(image, quality)
            if len(encoded) <= FRAME_MAX_ENCODED_BYTES:
                return EncodedFrame(
                    data=encoded,
                    width=image.width,
                    height=image.height,
                    mime_type=mime_type,
                )
        next_width = int(image.width * 0.8)
        next_height = int(image.height * 0.8)
        if min(next_width, next_height) < _MIN_EDGE:
            raise CompanionFrameUnsupportedError()
        image = image.resize((next_width, next_height), Image.Resampling.LANCZOS)


def _encode_avif(image: Image.Image, quality: int) -> bytes:
    output = BytesIO()
    image.save(output, format="AVIF", quality=quality, speed=_AVIF_SPEED)
    return output.getvalue()


def _encode_webp(image: Image.Image, quality: int) -> bytes:
    output = BytesIO()
    image.save(output, format="WEBP", quality=quality, method=6)
    return output.getvalue()


__all__ = ["EncodedFrame", "avif_available", "encode_frame"]
