"""Generate companion sprite candidates with the OpenAI image edit API.

The API key is read from the env file named by ``COMPANION_OPENAI_ENV``
(default: ``.secrets/openai_image.env`` at the repository root). It is never
printed. Raw candidates land under ``COMPANION_WORK_DIR`` (outside the repo).

Usage (from the repository root):

    uv run --no-project --with httpx python frontend/scripts/companion/generate.py \
        base --reference path/to/reference.png [--only vellum,atlas] [--n 2]
    uv run --no-project --with httpx python frontend/scripts/companion/generate.py \
        poses --reference path/to/reference.png [--only atlas] [--actions idle,greet] [--n 2]

``base`` writes ``<work>/<id>/base-<k>.png``. Pick one and copy it to
``<work>/<id>/base.png`` before running ``poses``, which writes
``<work>/<id>/<action>-<k>.png`` using the approved base (first image), the
owner's reference, and an optional ``<work>/<id>/anchor.png`` approved pose as
identity references.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MODEL = os.environ.get("COMPANION_IMAGE_MODEL", "gpt-image-2.6-sunburst")
ENDPOINT = "https://api.openai.com/v1/images/edits"


def load_key() -> str:
    env_path = Path(os.environ.get("COMPANION_OPENAI_ENV", REPO / ".secrets/openai_image.env"))
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"OPENAI_API_KEY missing in {env_path.name}")


def work_dir() -> Path:
    value = os.environ.get("COMPANION_WORK_DIR")
    if not value:
        raise SystemExit("Set COMPANION_WORK_DIR to a directory outside the repository.")
    return Path(value)


def edit(
    key: str,
    prompt: str,
    images: list[Path],
    n: int,
    mask: Path | None = None,
    size: str = "1024x1536",
) -> list[bytes]:
    files = [("image[]", (p.name, p.read_bytes(), "image/png")) for p in images]
    if mask is not None:
        files.append(("mask", (mask.name, mask.read_bytes(), "image/png")))
    data = {
        "model": MODEL,
        "prompt": prompt,
        "background": "transparent",
        "output_format": "png",
        "size": size,
        "quality": "high",
        "n": str(n),
    }
    for attempt in range(5):
        try:
            response = httpx.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {key}"},
                data=data,
                files=files,
                timeout=600,
            )
        except httpx.HTTPError as exc:
            print(f"  network error ({type(exc).__name__}), retrying", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
            continue
        if response.status_code == 200:
            return [base64.b64decode(item["b64_json"]) for item in response.json()["data"]]
        if response.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * (attempt + 1))
            continue
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:400]}")
    raise RuntimeError("gave up after retries")


def build_prompt(spec: dict, style: str, action_text: str, is_base: bool) -> str:
    action_text = action_text.replace("{props}", spec["props"])
    if is_base:
        lead = (
            "Using the first image as the art-style and character-concept reference, draw this character: "
            f"{spec['design']}"
        )
    else:
        lead = (
            "The FIRST image is the approved design of this exact character; keep the same character, "
            "hair, costume, colors, proportions, accessories and art style precisely. The other images "
            "are additional style references only. Redraw the same character in a new pose. "
            f"Character: {spec['design']}"
        )
    return f"{lead}\n\nPose: {action_text}\n\n{style}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["base", "poses", "icon", "fix"])
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--only", default="")
    parser.add_argument("--actions", default="")
    parser.add_argument("--n", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--suffix", default="")
    parser.add_argument("--image", type=Path, help="fix mode: image to edit")
    parser.add_argument("--mask", type=Path, help="fix mode: mask png")
    parser.add_argument("--prompt", default="", help="fix mode: instruction")
    parser.add_argument("--out", type=Path, help="fix mode: output path prefix")
    args = parser.parse_args()

    catalog = json.loads((HERE / "characters.json").read_text(encoding="utf-8"))
    key = load_key()
    work = work_dir()
    only = {s for s in args.only.split(",") if s}
    chars = [c for c in catalog["characters"] if not only or c["id"] in only]

    if args.mode == "fix":
        spec = chars[0]
        prompt = (
            f"Edit only the masked region of the first image. {args.prompt} Keep everything else identical. "
            f"Character: {spec['design']}\n\n{catalog['style']}"
        )
        refs = [args.image, args.reference]
        outs = edit(key, prompt, refs, args.n, args.mask)
        for k, blob in enumerate(outs, 1):
            path = args.out.with_name(f"{args.out.name}-fix{args.suffix}{k}.png")
            path.write_bytes(blob)
            print("wrote", path.relative_to(work))
        return

    if args.mode == "icon":
        out_dir = work / "icon"
        out_dir.mkdir(parents=True, exist_ok=True)
        blobs = edit(key, catalog["icon"], [args.reference], args.n, size="1024x1024")
        for k, blob in enumerate(blobs, 1):
            (out_dir / f"bust{args.suffix}-{k}.png").write_bytes(blob)
        print(f"ok icon ({len(blobs)})")
        return

    jobs: list[tuple[str, str, list[Path], Path]] = []
    for spec in chars:
        out_dir = work / spec["id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.mode == "base":
            prompt = build_prompt(spec, catalog["style"], catalog["actions"]["base"], True)
            jobs.append((spec["id"] + "/base", prompt, [args.reference], out_dir / f"base{args.suffix}"))
            continue
        base = out_dir / "base.png"
        if not base.exists():
            print(f"skip {spec['id']}: no approved base.png", file=sys.stderr)
            continue
        refs = [base]
        if base.read_bytes() != args.reference.read_bytes():
            refs.append(args.reference)
        anchor = out_dir / "anchor.png"
        if anchor.exists():
            refs.append(anchor)
        wanted = [a for a in args.actions.split(",") if a] or [
            a for a in catalog["actions"] if a != "base"
        ]
        for action in wanted:
            prompt = build_prompt(spec, catalog["style"], catalog["actions"][action], False)
            jobs.append((f"{spec['id']}/{action}", prompt, refs, out_dir / f"{action}{args.suffix}"))

    print(f"{len(jobs)} requests x n={args.n} with {MODEL}")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(edit, key, prompt, refs, args.n): (label, stem) for label, prompt, refs, stem in jobs}
        for future in as_completed(futures):
            label, stem = futures[future]
            try:
                blobs = future.result()
            except Exception as exc:  # report and keep going
                print(f"FAIL {label}: {exc}", file=sys.stderr)
                continue
            for k, blob in enumerate(blobs, 1):
                stem.with_name(f"{stem.name}-{k}.png").write_bytes(blob)
            print(f"ok {label} ({len(blobs)})", flush=True)


if __name__ == "__main__":
    main()
