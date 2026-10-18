"""Export the FastAPI OpenAPI schema for the committed frontend client.

Run from the backend directory:
    uv run python -m script.export_openapi

The output is deterministic so `make api-check` can detect contract drift with
a plain git diff.
"""

import json

from app.infrastructure.config.settings import BACKEND_ROOT
from app.main import create_app

OUTPUT_PATH = BACKEND_ROOT.parent / "frontend" / "openapi.json"


def main() -> None:
    app = create_app()
    schema = app.openapi()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
