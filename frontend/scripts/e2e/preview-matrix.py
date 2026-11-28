"""Preview matrix: open every file in a Library folder and record failures.

Manual check, not part of CI. Run against a throwaway local stack, never a
live archive:

    APSOR_E2E_BASE=http://127.0.0.1:18931 APSOR_E2E_USER=previewroot \
    APSOR_E2E_PASSWORD=... APSOR_E2E_FOLDER=/Samples \
    uv run --no-project --with playwright python frontend/scripts/e2e/preview-matrix.py

Upload samples first (frontend/scripts/e2e/make-preview-samples.py writes one
small real file per accepted type). For each file the script opens the Library
preview at desktop and phone width, waits for the renderer, saves a
screenshot, and reports console errors, failed requests, HTTP >= 400 and any
visible failure text. Set APSOR_E2E_CHROME to a Chromium binary if Playwright's
own download is not installed.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("APSOR_E2E_BASE", "http://127.0.0.1:8000").rstrip("/")
USER = os.environ["APSOR_E2E_USER"]
PASSWORD = os.environ["APSOR_E2E_PASSWORD"]
FOLDER = os.environ.get("APSOR_E2E_FOLDER", "/Samples")
OUT = Path(os.environ.get("APSOR_E2E_OUT", "preview-matrix-shots"))
CHROME = os.environ.get("APSOR_E2E_CHROME") or None
FAILURE_TEXT = ("could not", "couldn't", "Unable", "failed to", "無法", "无法")
VIEWPORTS = {"desktop": {"width": 1280, "height": 800}, "phone": {"width": 390, "height": 844}}


def folder_files() -> list[dict[str, object]]:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    login = urllib.request.Request(
        f"{BASE}/api/v1/auth/login",
        data=json.dumps({"username": USER, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener.open(login)
    query = urllib.parse.urlencode({"path": FOLDER})
    listing = json.load(opener.open(f"{BASE}/api/v1/paths?{query}"))
    return [item for item in listing.get("files", []) if isinstance(item, dict)]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files = folder_files()
    problems: dict[str, list[str]] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROME)
        for label, viewport in VIEWPORTS.items():
            page = browser.new_page(viewport=viewport)
            errors: list[str] = []
            page.on("pageerror", lambda error, errors=errors: errors.append(f"pageerror: {error}"))
            page.on("console", lambda m, errors=errors: errors.append(m.text) if m.type == "error" else None)
            page.on("requestfailed", lambda r, errors=errors: errors.append(f"requestfailed {r.url}"))
            page.on("response", lambda r, errors=errors: errors.append(f"http {r.status} {r.url}") if r.status >= 400 else None)
            page.goto(f"{BASE}/login")
            page.fill("input[autocomplete=username]", USER)
            page.fill("input[type=password]", PASSWORD)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2500)
            for item in files:
                errors.clear()
                file_id, name = item.get("file_id"), str(item.get("file_name"))
                page.goto(f"{BASE}/library/files/{file_id}")
                page.wait_for_timeout(4000)
                page.screenshot(path=str(OUT / f"{label}-{name}.png"))
                body = page.inner_text("body")
                found = list(errors) + (["failure text visible"] if any(t in body for t in FAILURE_TEXT) else [])
                if found:
                    problems[f"{label}:{name}"] = found[:8]
            page.close()
        browser.close()
    (OUT / "report.json").write_text(json.dumps(problems, indent=1, ensure_ascii=False))
    for key, found in problems.items():
        print(key, found)
    print(f"{len(files)} files × {len(VIEWPORTS)} viewports; {len(problems)} with problems; shots in {OUT}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
