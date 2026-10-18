"""Offline visual features for image-to-image retrieval.

This is a deterministic, CPU-only descriptor: a dHash bit vector plus a coarse
colour grid and a per-channel histogram. It captures visual similarity (layout,
tone, palette) without a neural network or GPU.
"""

import math
from dataclasses import dataclass
from io import BytesIO
from typing import cast

from PIL import Image, ImageOps, ImageStat

VECTOR_DIMENSION = 115
MODEL_NAME = "dendro-visual-115"


class InvalidImageError(ValueError):
    """Raised when the uploaded bytes are not a decodable image."""


@dataclass(frozen=True)
class VisualFeatures:
    """The visual descriptor and image metadata."""

    vector: list[float]
    perceptual_hash: str
    width: int
    height: int


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def extract_visual_features(data: bytes) -> VisualFeatures:
    """Decode one image and produce a normalized 115-dimensional descriptor."""
    try:
        with Image.open(BytesIO(data)) as raw:
            raw.load()
            image = ImageOps.exif_transpose(raw).convert("RGB")
    except Exception as exc:
        raise InvalidImageError("The upload is not a decodable image.") from exc

    width, height = image.size
    small = image.resize((32, 32), Image.Resampling.LANCZOS)
    gray = small.convert("L").resize((9, 8), Image.Resampling.LANCZOS)

    bits: list[float] = []
    hash_value = 0
    pixels = cast(list[int], list(gray.get_flattened_data()))
    for row in range(8):
        for column in range(8):
            left = pixels[row * 9 + column]
            right = pixels[row * 9 + column + 1]
            bit = 1 if left > right else 0
            hash_value = (hash_value << 1) | bit
            bits.append(1.0 if bit else -1.0)

    colour_grid: list[float] = []
    for grid_row in range(3):
        for grid_column in range(3):
            box = (
                grid_column * 32 // 3,
                grid_row * 32 // 3,
                (grid_column + 1) * 32 // 3,
                (grid_row + 1) * 32 // 3,
            )
            means = ImageStat.Stat(small.crop(box)).mean
            if isinstance(means, tuple):
                colour_grid.extend(channel / 255.0 for channel in means[:3])

    histogram: list[float] = []
    sample = image.resize((64, 64), Image.Resampling.LANCZOS)
    for channel in range(3):
        values = list(sample.getchannel(channel).histogram())
        bins = [sum(values[index : index + 32]) for index in range(0, 256, 32)]
        total = sum(bins) or 1
        histogram.extend(bucket / total for bucket in bins[:8])

    vector = _normalize([*bits, *colour_grid, *histogram])
    return VisualFeatures(
        vector=vector,
        perceptual_hash=f"{hash_value:016x}",
        width=width,
        height=height,
    )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity for two non-empty vectors of the same dimension."""
    if len(left) != len(right) or not left:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
