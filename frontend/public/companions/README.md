# Chat companion presets

Built-in sprite sets for the chat companion: faceless, ball-jointed doll
librarians who stand freely beside the chat and change pose with the agent's
work. No strings hold them; they move on their own.

## Roster

`index.json` lists the presets in display order. `vellum` is the default.

| id | Name | Presentation | Accent | Signature props |
|---|---|---|---|---|
| `vellum` | Vellum | female | `#c9a24a` | gilded book; the owner's original character |
| `atlas` | Atlas | male | `#3f6fa8` | armillary globe, rolled maps |
| `herbaria` | Herbaria | female | `#6f8f4e` | herbarium folio, loupe |
| `horologe` | Horologe | male | `#b8733a` | brass gears, pocket watch, archive keys |
| `nocturne` | Nocturne | female | `#7a5fb0` | lantern, star chart |
| `quill` | Quill | male | `#9e3b3b` | feather quill, inkwell, scroll |

Every character has a blank porcelain face (no eyes, mouth, or nose). The small
brass rings on the head and shoulders are ornaments from the generated art; the
overlay draws no strings or control bar. Older manifests may still carry an
`anchor` field, which the parser ignores.

## Layout

```
<id>/manifest.json      schema 1: name, gender, accent, frame size, actions
<id>/<action>.avif      384×576 transparent AVIF, feet on a shared baseline
<id>/<action>-N.avif    further animation frames (N = 2, 3)
<id>/portrait.avif      192×192 head-and-shoulders crop for the picker
```

Each manifest action is `{ "frames": [...], "fps": n, "loop": true }`. Animated
actions (`idle`, `thinking`, `speaking`, `sleeping`, `success`, `searching`)
carry three frames, an `fps` of 3–5, and `"pingpong": true`, meaning the
player runs 1→2→3→2→1. A frame is at most 25 KB.

Actions: `idle`, `greet`, `listening`, `thinking`, `searching`, `reading`,
`writing`, `calculating`, `browsing`, `presenting`, `speaking`, `waiting`,
`success`, `confused`, `sleeping`, `held`.

## Provenance

The art was generated with an OpenAI image model (`gpt-image-2.6-sunburst`,
image edit endpoint) from the project owner's own faceless librarian
reference. Vellum's poses were edited directly from that original image; the
other five characters were first redesigned from it, then each pose was edited
from the approved character base with the original as a style reference.
Two or three candidates were made per pose and the picks were chosen by eye.

Animation frames are not separate generations: an image model redraws the
whole figure even under a mask, so its frames do not register. Instead,
`postprocess.py` derives them from the approved pose with pixel-locked warps
(head tilt around the neck, chest rise, detached props floating), so every
unchanged pixel stays identical and the loop is seamless.

## App icon and GitHub artwork

`frontend/public/favicon.ico`, `icon-192.png`, `icon-512.png`,
`apple-touch-icon.png`, `docs/assets/avatar.png`, and
`docs/assets/social-preview.png` are built by `icons.py` from a dedicated
Vellum bust generated from the same original. GitHub has no API for a
repository's social preview: upload `docs/assets/social-preview.png` under the
repository's Settings → General → Social preview, and use
`docs/assets/avatar.png` as the organization or profile avatar if wanted.

## Regenerating

The scripts live in `frontend/scripts/companion/`. `characters.json` holds the
designs, pose prompts, the icon prompt, and the animation keys. The API key is
read from an untracked env file (`COMPANION_OPENAI_ENV`, default
`.secrets/openai_image.env`), and raw candidates are written to
`COMPANION_WORK_DIR`, which must be outside the repository.

```bash
export COMPANION_WORK_DIR=/path/outside/repo COMPANION_OPENAI_ENV=.secrets/openai_image.env
gen="uv run --no-project --with httpx --with pillow python frontend/scripts/companion/generate.py"
post="uv run --no-project --with pillow --with numpy --with scipy python frontend/scripts/companion/postprocess.py"

$gen base --reference reference.png --only atlas          # pick one → $COMPANION_WORK_DIR/atlas/base.png
$gen poses --reference reference.png --only atlas --n 2   # pick one per action → atlas/<action>.png
$post --work "$COMPANION_WORK_DIR" --sheet sheet.png --only atlas   # review candidates
$post --work "$COMPANION_WORK_DIR" --flipbook review/ --only atlas  # review animation
$post --work "$COMPANION_WORK_DIR" --only atlas                     # export AVIF + manifest
$gen icon --reference reference.png --n 4                 # pick one → icon/bust.png
uv run --no-project --with pillow --with numpy python frontend/scripts/companion/icons.py --work "$COMPANION_WORK_DIR"
```

`generate.py fix --image … --mask … --prompt …` repairs one region of a frame
through the edit endpoint's mask.
