"""Small API helpers shared by integration tests."""

import base64
import io

from fastapi.testclient import TestClient
from pptx import Presentation
from pptx.util import Inches

# A 1x1 blue PNG used to give a synthetic deck an embedded media part.
BLUE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def create_text(
    client: TestClient,
    path: str,
    content: str,
    occurred_at: str | None = None,
) -> dict[str, object]:
    """Create a text file through the public API."""
    payload: dict[str, object] = {"path": path, "content": content}
    if occurred_at is not None:
        payload["occurred_at"] = occurred_at
    response = client.post("/api/v1/files/text", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def build_pptx_deck() -> bytes:
    """Build a two-slide deck with text, a table, notes, and embedded media."""
    presentation = Presentation()
    blank = presentation.slide_layouts[6]

    first = presentation.slides.add_slide(blank)
    textbox = first.shapes.add_textbox(
        Inches(0.5),
        Inches(0.5),
        Inches(8),
        Inches(2),
    )
    textbox.text_frame.text = "Quarterly review of the workshop budget"
    first.notes_slide.notes_text_frame.text = (
        "Mention the bearing replacement timeline."
    )

    second = presentation.slides.add_slide(blank)
    table = second.shapes.add_table(
        2,
        2,
        Inches(0.5),
        Inches(0.5),
        Inches(8),
        Inches(2),
    ).table
    table.cell(0, 0).text = "Item"
    table.cell(0, 1).text = "Qty"
    table.cell(1, 0).text = "Bearing"
    table.cell(1, 1).text = "12"
    second.shapes.add_picture(
        io.BytesIO(BLUE_PNG),
        Inches(5),
        Inches(3),
        Inches(1),
        Inches(1),
    )

    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def create_memory(
    client: TestClient,
    content: str,
    occurred_at: str,
    supersedes: list[int] | None = None,
) -> dict[str, object]:
    """Create a memory through the public API."""
    response = client.post(
        "/api/v1/memories",
        json={
            "content": content,
            "occurred_at": occurred_at,
            "supersedes": supersedes or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
