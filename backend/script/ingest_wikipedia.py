"""Ingest Wikipedia articles into a running DendroMatrix instance.

Example:
    uv run python -m script.ingest_wikipedia \
        --lang en --titles Automobile Dendrochronology \
        --prefix /wikipedia/en

The script uses the MediaWiki plain-text extract API and then calls the public
`POST /api/v1/files/text` endpoint, so the normal chunking, indexing, and cache
invalidation path is exercised.
"""

import argparse
import re
from datetime import UTC, datetime

import httpx

USER_AGENT = "DendroMatrix/0.1 (local knowledge archive)"


def _slug(title: str) -> str:
    value = re.sub(r"\s+", "-", title.strip())
    value = value.replace("/", "-")
    return value or "article"


def fetch_extract(client: httpx.Client, lang: str, title: str) -> str:
    """Fetch the plain-text extract of one Wikipedia article."""
    response = client.get(
        f"https://{lang}.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "redirects": 1,
            "format": "json",
            "titles": title,
        },
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    pages = response.json()["query"]["pages"]
    page = next(iter(pages.values()))
    extract = page.get("extract", "")
    if not extract:
        raise RuntimeError(f"No extract returned for {title!r}.")
    return re.sub(r"\n{3,}", "\n\n", extract).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Wikipedia extracts into DendroMatrix.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--prefix", default="/wikipedia/en")
    parser.add_argument("--titles", nargs="+", required=True)
    parser.add_argument(
        "--occurred-at",
        default=datetime.now(UTC).isoformat(),
        help="Timeline timestamp for the ingested files.",
    )
    arguments = parser.parse_args()

    with httpx.Client(timeout=120) as client:
        for title in arguments.titles:
            content = fetch_extract(client, arguments.lang, title)
            path = f"{arguments.prefix.rstrip('/')}/{_slug(title)}.md"
            response = client.post(
                f"{arguments.base_url.rstrip('/')}/api/v1/files/text",
                json={
                    "path": path,
                    "content": content,
                    "occurred_at": arguments.occurred_at,
                },
            )
            response.raise_for_status()
            body = response.json()
            print(f"{path}: file_id={body['id']} chunks={body['total_chunks']}")


if __name__ == "__main__":
    main()
