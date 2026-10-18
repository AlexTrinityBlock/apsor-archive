"""Sparse timeline sampling and density accounting."""

from fastapi.testclient import TestClient

from tests.helpers import create_memory, create_text


def test_timeline_sparse_sampling(client: TestClient) -> None:
    for index in range(8):
        day = 18 + index
        create_memory(
            client,
            f"Timeline memory number {index} about workshop routines.",
            f"2026-09-{day:02d}T10:00:00Z",
        )
    for index in range(6):
        day = 19 + index
        create_text(
            client,
            f"/timeline/note-{index}.md",
            f"Timeline file number {index} about workshop routines.",
            f"2026-09-{day:02d}T15:00:00Z",
        )

    response = client.get(
        "/api/v1/timeline",
        params={"year": 2026, "month": 9, "day": 30, "day_range": 14},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 14
    assert body["sampled"] <= 10
    assert body["skipped"] == body["total"] - body["sampled"]

    events = body["events"]
    assert sum(1 for event in events if event["kind"] == "memory") <= 5
    assert sum(1 for event in events if event["kind"] == "file_update") <= 5
    anchors = {event["anchor"] for event in events}
    assert 0.0 in anchors
    assert 1.0 in anchors

    memory_density = sum(item["memory_count"] for item in body["density"])
    file_density = sum(item["file_count"] for item in body["density"])
    assert memory_density == 8
    assert file_density == 6

    tool = client.get(
        "/api/v1/tools/read_timeline",
        params={"year": 2026, "month": 9, "day": 30, "day_range": 14},
    )
    assert tool.status_code == 200
    assert "<timeline" in tool.text
    assert "<memory_result" in tool.text
    assert "<file_update" in tool.text
