"""Turn approved companion PNGs into the committed WebP sprite set.

Input: ``<work>/<id>/<action>.png`` (approved picks, 1024x1536 RGBA).
Output: ``frontend/public/companions/<id>/{<action>[-N].avif, portrait.avif, manifest.json}``
and ``frontend/public/companions/index.json``.

Usage (from the repository root):

    uv run --no-project --with pillow --with numpy --with scipy \
        python frontend/scripts/companion/postprocess.py --work <dir> [--only id,...]
    ... postprocess.py --work <dir> --sheet <out.png> --pattern '<action>-*.png' --only id

``--sheet`` renders a review contact sheet instead of exporting.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT_ROOT = REPO / "frontend/public/companions"
FRAME_W, FRAME_H = 384, 576
PORTRAIT = 192
MAX_BYTES = 25 * 1024
TARGET_BYTES = 15 * 1024
AVIF_FLOOR = 54
ACTIONS = [
    "idle", "greet", "listening", "thinking", "searching", "reading", "writing", "calculating",
    "browsing", "presenting", "speaking", "waiting", "success", "confused", "sleeping", "held",
]


def clean_alpha(img: Image.Image) -> Image.Image:
    """Drop faint haze and tiny disconnected specks while keeping deliberate props."""
    rgba = np.array(img.convert("RGBA"))
    alpha = rgba[:, :, 3].astype(np.int32)
    alpha[alpha < 28] = 0
    solid = alpha > 96
    labels, count = ndimage.label(solid, structure=np.ones((3, 3)))
    if count:
        sizes = ndimage.sum(solid, labels, range(1, count + 1))
        keep = np.zeros(count + 1, dtype=bool)
        keep[1:] = sizes >= 220
        grown = ndimage.binary_dilation(keep[labels], iterations=4)
        alpha[~grown] = 0
    rgba[:, :, 3] = alpha.astype(np.uint8)
    rgba[alpha == 0, :3] = 0
    return Image.fromarray(rgba, "RGBA")


def bbox(img: Image.Image) -> tuple[int, int, int, int]:
    box = img.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    if box is None:
        raise ValueError("empty frame")
    return box


def encode_avif(img: Image.Image) -> bytes:
    """Highest AVIF quality that meets the size target.

    Quality never drops below ``AVIF_FLOOR`` while the frame fits the hard
    cap: hair strands and gold trim soften visibly below it.
    """
    best = b""
    for quality in (64, 60, 56, AVIF_FLOOR, 48, 44, 40):
        buffer = io.BytesIO()
        img.save(buffer, "AVIF", quality=quality, speed=2, subsampling="4:2:0")
        best = buffer.getvalue()
        if len(best) <= TARGET_BYTES or (quality <= AVIF_FLOOR and len(best) <= MAX_BYTES):
            break
    if len(best) > MAX_BYTES:
        raise ValueError(f"frame too large: {len(best)} bytes")
    return best


def group_of(name: str) -> str:
    """``idle-2`` animates relative to ``idle``; single poses are their own group."""
    head, _, tail = name.rpartition("-")
    return head if tail.isdigit() else name


def layout(frames: dict[str, Image.Image]) -> dict[str, Image.Image]:
    """Scale every frame uniformly and bottom-align it on one baseline.

    Animation frames reuse their first frame's placement so the unchanged
    parts stay pixel-locked; separate poses are centered on their own box.
    """
    boxes = {name: bbox(img) for name, img in frames.items()}
    max_w = max(b[2] - b[0] for b in boxes.values())
    max_h = max(b[3] - b[1] for b in boxes.values())
    scale = min((FRAME_H * 0.95) / max_h, (FRAME_W * 0.98) / max_w)
    baseline = FRAME_H - int(FRAME_H * 0.015)
    out: dict[str, Image.Image] = {}
    for name, img in frames.items():
        left, top, right, bottom = boxes[group_of(name)]
        x = (FRAME_W - (right - left) * scale) / 2 - left * scale
        y = baseline - bottom * scale
        full = img.resize((round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
        canvas.paste(full, (round(x), round(y)), full)
        out[name] = canvas
    return out


def _ramp(y: np.ndarray, full: float, zero: float) -> np.ndarray:
    """1 above ``full``, 0 below ``zero``, smoothstep in between."""
    t = np.clip((zero - y) / max(1.0, zero - full), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def warp(img: Image.Image, tilt: float = 0.0, nod: float = 0.0, lift: float = 0.0, bob: float = 0.0) -> Image.Image:
    """Pixel-locked free-standing motion: the head pivots at the neck, the chest
    rises, and detached props (sparkles, ribbons, cards) float upward."""
    rgba = np.array(img.convert("RGBA"), dtype=np.float32) / 255.0
    alpha = rgba[:, :, 3]
    premul = rgba.copy()
    premul[:, :, :3] *= alpha[:, :, None]

    labels, count = ndimage.label(alpha > 0.25, structure=np.ones((3, 3)))
    props = np.zeros(alpha.shape, dtype=bool)
    body_mask = alpha > 0.25
    if count > 1:
        sizes = ndimage.sum(alpha > 0.25, labels, range(1, count + 1))
        body = int(np.argmax(sizes)) + 1
        body_mask = labels == body
        props = ndimage.binary_dilation((labels > 0) & (labels != body), iterations=3)
    prop_layer = np.where(props[:, :, None], premul, 0.0)
    base = np.where(props[:, :, None], 0.0, premul)

    # Measure the figure from the body alone so floating props don't move the neck.
    body_rows = np.where(body_mask.any(axis=1))[0]
    body_cols = np.where(body_mask.any(axis=0))[0]
    top, bottom = int(body_rows[0]), int(body_rows[-1])
    left, right = int(body_cols[0]), int(body_cols[-1])
    height = bottom - top
    neck = top + 0.21 * height
    rows = np.arange(alpha.shape[0], dtype=np.float32)
    band = alpha[int(neck - 0.02 * height) : int(neck + 0.02 * height)]
    cols = np.where(band.max(axis=0) > 0.3)[0]
    pivot_x = float(cols.mean()) if len(cols) else (left + right) / 2

    yy, xx = np.mgrid[0 : alpha.shape[0], 0 : alpha.shape[1]].astype(np.float32)
    head_w = _ramp(rows, neck, neck + 0.06 * height)[:, None]
    chest_w = _ramp(rows, top + 0.42 * height, top + 0.58 * height)[:, None]
    theta = np.deg2rad(tilt) * head_w
    dx, dy = xx - pivot_x, yy - neck
    src_x = pivot_x + np.cos(theta) * dx + np.sin(theta) * dy
    src_y = neck - np.sin(theta) * dx + np.cos(theta) * dy
    src_y = src_y - nod * head_w + lift * chest_w
    moved = np.stack(
        [ndimage.map_coordinates(base[:, :, c], [src_y, src_x], order=1, mode="constant") for c in range(4)],
        axis=2,
    )
    if bob:
        prop_layer = ndimage.shift(prop_layer, (-bob, 0, 0), order=1, mode="constant")
    out = moved + prop_layer * (1.0 - moved[:, :, 3:4])
    a = np.clip(out[:, :, 3:4], 1e-6, 1.0)
    rgb = np.where(out[:, :, 3:4] > 1e-6, out[:, :, :3] / a, 0.0)
    final = np.concatenate([np.clip(rgb, 0, 1), np.clip(out[:, :, 3:4], 0, 1)], axis=2)
    return Image.fromarray((final * 255 + 0.5).astype(np.uint8), "RGBA")


def portrait(frame: Image.Image) -> Image.Image:
    alpha = np.array(frame.getchannel("A"))
    rows = np.where(alpha.max(axis=1) > 40)[0]
    top = int(rows[0])
    height = int(rows[-1]) - top
    side = int(height * 0.34)
    band = alpha[top : top + int(height * 0.14)]
    cols = np.where(band.max(axis=0) > 40)[0]
    cx = int(cols.mean()) if len(cols) else FRAME_W // 2
    left = max(0, min(FRAME_W - side, cx - side // 2))
    crop = frame.crop((left, max(0, top - side // 12), left + side, max(0, top - side // 12) + side))
    return crop.resize((PORTRAIT, PORTRAIT), Image.Resampling.LANCZOS)


def export(work: Path, catalog: dict, only: set[str]) -> None:
    index = []
    total = 0
    largest = 0
    for spec in catalog["characters"]:
        index.append({"id": spec["id"], "name": spec["name"], "gender": spec["gender"]})
        if only and spec["id"] not in only:
            continue
        src = work / spec["id"]
        raw = {a: Image.open(src / f"{a}.png").convert("RGBA") for a in ACTIONS}
        actions: dict[str, dict] = {a: {"frames": [f"{a}.avif"], "fps": 0, "loop": True} for a in ACTIONS}
        cleaned = {name: clean_alpha(img) for name, img in raw.items()}
        for action, plan in animation_plans(catalog):
            names = [action]
            for step, key in enumerate(plan["keys"], start=2):
                cleaned[f"{action}-{step}"] = warp(cleaned[action], **key)
                names.append(f"{action}-{step}")
            actions[action] = {
                "frames": [f"{n}.avif" for n in names],
                "fps": plan["fps"],
                "loop": True,
                "pingpong": plan["pingpong"],
            }
        placed = layout(cleaned)
        dest = OUT_ROOT / spec["id"]
        dest.mkdir(parents=True, exist_ok=True)
        for old in [*dest.glob("*.webp"), *dest.glob("*.avif")]:
            old.unlink()
        sizes = []
        for name, img in placed.items():
            blob = encode_avif(img)
            (dest / f"{name}.avif").write_bytes(blob)
            sizes.append(len(blob))
            largest = max(largest, len(blob))
        blob = encode_avif(portrait(placed["idle"]))
        (dest / "portrait.avif").write_bytes(blob)
        sizes.append(len(blob))
        total += sum(sizes)
        print(f"{spec['id']}: {len(sizes)} files, {sum(sizes)} bytes, max {max(sizes)}")
        manifest = {
            "schema": 1,
            "id": spec["id"],
            "name": spec["name"],
            "gender": spec["gender"],
            "palette": {"accent": spec["accent"]},
            "size": {"width": FRAME_W, "height": FRAME_H},
            "portrait": "portrait.avif",
            "actions": actions,
        }
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (OUT_ROOT / "index.json").write_text(
        json.dumps({"schema": 1, "default": catalog["characters"][0]["id"], "presets": index}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"total {total} bytes, largest frame {largest} bytes")


def sheet(paths: list[Path], out: Path, cell: int = 200) -> None:
    cols = 8
    rows = (len(paths) + cols - 1) // cols
    h = int(cell * 1.5)
    canvas = Image.new("RGB", (cols * cell, rows * (h + 18)), (236, 233, 226))
    draw = ImageDraw.Draw(canvas)
    for i, path in enumerate(paths):
        img = clean_alpha(Image.open(path))
        img.thumbnail((cell - 6, h - 6), Image.Resampling.LANCZOS)
        x, y = (i % cols) * cell, (i // cols) * (h + 18)
        tile = Image.new("RGB", (cell, h), (214, 220, 228) if (i // cols + i) % 2 else (228, 222, 210))
        tile.paste(img, ((cell - img.width) // 2, (h - img.height) // 2), img)
        canvas.paste(tile, (x, y))
        draw.text((x + 4, y + h + 3), f"{path.parent.name}/{path.stem}", fill=(30, 30, 30))
    canvas.save(out)
    print("sheet", out)


def animation_plans(catalog: dict) -> list[tuple[str, dict]]:
    return [(a, p) for a, p in catalog.get("frames", {}).items() if not a.startswith("_")]


def flipbook(work: Path, catalog: dict, char_id: str, out: Path, cell: int = 210) -> None:
    """Review sheet: each animation's frames side by side, an onion-skin of the
    extremes, and a motion heat map (black = pixel-identical)."""
    src = work / char_id
    rows: list[list[tuple[str, Image.Image]]] = []
    for action, plan in animation_plans(catalog):
        first = clean_alpha(Image.open(src / f"{action}.png"))
        frames = [first] + [warp(first, **key) for key in plan["keys"]]
        left, top, right, bottom = bbox(first)
        window = (max(0, left - 60), max(0, top - 60), min(first.width, right + 60), int(top + 0.62 * (bottom - top)))
        row = [(f"{action} f{i + 1}", f.crop(window)) for i, f in enumerate(frames)]
        onion = Image.blend(frames[0], frames[-1], 0.5).crop(window)
        row.append(("onion 1+last", onion))
        diff = np.abs(np.array(frames[-1], dtype=np.int16) - np.array(first, dtype=np.int16)).max(axis=2)
        heat = Image.fromarray(np.clip(diff * 3, 0, 255).astype(np.uint8), "L")
        row.append(("motion", heat.crop(window).convert("RGBA")))
        rows.append(row)
    cols = max(len(r) for r in rows)
    h = int(cell * 1.1)
    canvas = Image.new("RGB", (cols * cell, len(rows) * (h + 16)), (236, 233, 226))
    draw = ImageDraw.Draw(canvas)
    for r, row in enumerate(rows):
        for c, (label, img) in enumerate(row):
            img = img.copy()
            img.thumbnail((cell - 4, h - 4), Image.Resampling.LANCZOS)
            tile = Image.new("RGB", (cell, h), (214, 220, 228))
            tile.paste(img, ((cell - img.width) // 2, (h - img.height) // 2), img)
            canvas.paste(tile, (c * cell, r * (h + 16)))
            draw.text((c * cell + 4, r * (h + 16) + h + 2), label, fill=(20, 20, 20))
    canvas.save(out)
    print("flipbook", out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--only", default="")
    parser.add_argument("--sheet", type=Path)
    parser.add_argument("--flipbook", type=Path, help="directory for animation review sheets")
    parser.add_argument("--pattern", default="*-[0-9].png")
    args = parser.parse_args()
    catalog = json.loads((HERE / "characters.json").read_text(encoding="utf-8"))
    only = {s for s in args.only.split(",") if s}
    if args.flipbook:
        for spec in catalog["characters"]:
            if not only or spec["id"] in only:
                flipbook(args.work, catalog, spec["id"], args.flipbook / f"{spec['id']}-flipbook.png")
        return
    if args.sheet:
        paths: list[Path] = []
        for spec in catalog["characters"]:
            if only and spec["id"] not in only:
                continue
            paths += sorted((args.work / spec["id"]).glob(args.pattern))
        sheet(paths, args.sheet)
        return
    export(args.work, catalog, only)


if __name__ == "__main__":
    main()
