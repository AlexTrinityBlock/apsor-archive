"""Memory supersession, trace reads, and neighbor ranges."""

from fastapi.testclient import TestClient

from tests.helpers import create_memory


def test_save_memory_supersede_and_trace(client: TestClient) -> None:
    first = create_memory(
        client,
        "The user prefers a manual transmission car.",
        "2026-09-01T10:00:00Z",
    )
    second = create_memory(
        client,
        "A colleague recommended a manual transmission car.",
        "2026-09-02T10:00:00Z",
    )
    first_id = int(first["memory"]["memory_id"])
    second_id = int(second["memory"]["memory_id"])

    replacement = create_memory(
        client,
        "The user switched to an automatic transmission car.",
        "2026-09-03T10:00:00Z",
        supersedes=[first_id, second_id],
    )
    replacement_id = int(replacement["memory"]["memory_id"])
    assert replacement["deprecated"][0]["status"] == "deprecated"
    assert replacement["deprecated"][0]["superseded_by_id"] == replacement_id

    old = client.get(f"/api/v1/memories/{first_id}")
    assert old.status_code == 200
    old_body = old.json()
    assert old_body["target"]["status"] == "deprecated"
    assert old_body["superseded_by"]["memory_id"] == replacement_id

    trace = client.get(f"/api/v1/memories/{replacement_id}", params={"memory_range": 0})
    assert trace.status_code == 200
    chain_ids = {memory["memory_id"] for memory in trace.json()["chain"]}
    assert {first_id, second_id, replacement_id} <= chain_ids

    tool = client.get(
        "/api/v1/tools/read_memory",
        params={"memory_id": replacement_id, "memory_range": 1},
    )
    assert tool.status_code == 200
    assert 'target="true"' in tool.text
    assert 'relation="supersedes"' in tool.text

    search = client.get(
        "/api/v1/search",
        params={"query": "manual", "result_number": 3},
    )
    assert search.status_code == 200
    memory_ids = {item["memory_id"] for item in search.json()["memory_results"]}
    assert first_id not in memory_ids
    assert second_id not in memory_ids


def test_read_memory_neighbors(client: TestClient) -> None:
    first = create_memory(client, "First memory.", "2026-09-10T10:00:00Z")
    middle = create_memory(client, "Middle memory.", "2026-09-11T10:00:00Z")
    last = create_memory(client, "Last memory.", "2026-09-12T10:00:00Z")

    response = client.get(
        f"/api/v1/memories/{middle['memory']['memory_id']}",
        params={"memory_range": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["memory_id"] for item in body["neighbors_before"]] == [
        first["memory"]["memory_id"]
    ]
    assert [item["memory_id"] for item in body["neighbors_after"]] == [
        last["memory"]["memory_id"]
    ]

    exact = client.get(
        f"/api/v1/memories/{middle['memory']['memory_id']}",
        params={"memory_range": 0},
    )
    assert exact.json()["neighbors_before"] == []
    assert exact.json()["neighbors_after"] == []
