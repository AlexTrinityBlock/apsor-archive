"""Sparse and complete timeline reads with density accounting."""

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
    assert body["mode"] == "sparse"
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


def test_timeline_complete_returns_every_event(client: TestClient) -> None:
    for index in range(8):
        day = 18 + index
        create_memory(
            client,
            f"Complete timeline memory number {index} about workshop routines.",
            f"2026-09-{day:02d}T10:00:00Z",
        )
    for index in range(6):
        day = 19 + index
        create_text(
            client,
            f"/timeline/complete-note-{index}.md",
            f"Complete timeline file number {index} about workshop routines.",
            f"2026-09-{day:02d}T15:00:00Z",
        )

    params = {"year": 2026, "month": 9, "day": 30, "day_range": 14}

    sparse_before = client.get("/api/v1/timeline", params=params)
    assert sparse_before.status_code == 200
    assert sparse_before.json()["mode"] == "sparse"

    response = client.get("/api/v1/timeline", params={**params, "complete": True})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "complete"
    assert body["total"] == 14
    assert body["sampled"] == 14
    assert body["skipped"] == 0
    assert body["skips"] == []
    assert len(body["events"]) == 14
    assert all(event["anchor"] is None for event in body["events"])
    assert sum(item["memory_count"] for item in body["density"]) == 8
    assert sum(item["file_count"] for item in body["density"]) == 6

    sparse_after = client.get("/api/v1/timeline", params=params)
    assert sparse_after.status_code == 200
    sparse_body = sparse_after.json()
    assert sparse_body["mode"] == "sparse"
    assert sparse_body["sampled"] <= 10
    assert sum(1 for event in sparse_body["events"] if event["kind"] == "memory") <= 5
    assert sum(1 for event in sparse_body["events"] if event["kind"] == "file_update") <= 5
