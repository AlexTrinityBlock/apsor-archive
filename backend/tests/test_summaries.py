"""Extractive summary fallback, indexing, and coverage accounting."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.helpers import create_memory


def test_summary_fallback_and_search(client: TestClient) -> None:
    now = datetime.now(UTC)
    first_time = (now - timedelta(days=2)).isoformat()
    second_time = (now - timedelta(days=1)).isoformat()
    first = create_memory(
        client,
        "The wrench slipped while the user repaired the chassis.",
        first_time,
    )
    second = create_memory(
        client,
        "The user bought a new wrench for the next repair.",
        second_time,
    )
    first_id = int(first["memory"]["memory_id"])
    second_id = int(second["memory"]["memory_id"])

    created = client.post(
        "/api/v1/summaries",
        json={"memory_ids": [first_id, second_id]},
    )
    assert created.status_code == 201, created.text
    summary = created.json()
    assert summary["generator"] == "extractive"
    assert summary["memory_count"] == 2
    assert set(summary["source_memory_ids"]) == {first_id, second_id}
    assert summary["themes"]

    search = client.get(
        "/api/v1/search",
        params={"query": "wrench", "result_number": 3},
    )
    assert search.status_code == 200
    assert search.json()["summary_results"]

    listed = client.get("/api/v1/summaries")
    assert listed.json()["total_results"] == 1

    covered = client.post("/api/v1/summaries", json={})
    assert covered.status_code == 422
    assert covered.json()["error"] == "not_enough_memories"
