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

    # Direct edit and deprecation: the row keeps its identity, gains a title,
    # and leaves retrieval without creating a replacement memory.
    editable = create_memory(
        client,
        "Buy toilet paper.",
        "2026-09-20T10:00:00Z",
    )
    editable_id = int(editable["memory"]["memory_id"])
    assert editable["memory"]["title"] == "Buy toilet paper"
    assert editable["memory"]["deprecated_at"] is None
    before_edit_total = client.get("/api/v1/memories").json()["total_results"]

    edited = client.patch(
        f"/api/v1/memories/{editable_id}",
        json={"content": "Buy kitchen towels for the kitchen."},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Buy kitchen towels for the kitchen"
    assert edited.json()["content"] == "Buy kitchen towels for the kitchen."

    missing_edit = client.patch(
        "/api/v1/memories/999999",
        json={"content": "Nothing here."},
    )
    assert missing_edit.status_code == 404

    before_deprecation_total = client.get("/api/v1/memories").json()["total_results"]
    assert before_deprecation_total == before_edit_total
    deprecated = client.post(
        f"/api/v1/memories/{editable_id}/deprecate",
        json={"reason": "Already bought."},
    )
    assert deprecated.status_code == 200, deprecated.text
    deprecated_body = deprecated.json()
    assert deprecated_body["status"] == "deprecated"
    assert deprecated_body["superseded_by_id"] is None
    assert deprecated_body["deprecated_reason"] == "Already bought."
    assert deprecated_body["deprecated_at"] is not None
    assert client.get("/api/v1/memories").json()["total_results"] == before_edit_total

    read_deprecated = client.get(f"/api/v1/memories/{editable_id}")
    assert read_deprecated.status_code == 200
    assert read_deprecated.json()["superseded_by"] is None
    assert read_deprecated.json()["target"]["deprecated_at"] is not None

    already_deprecated = client.post(
        f"/api/v1/memories/{editable_id}/deprecate",
        json={"reason": "Again."},
    )
    assert already_deprecated.status_code == 409
    assert already_deprecated.json()["error"] == "memory_already_deprecated"

    missing_deprecate = client.post(
        "/api/v1/memories/999999/deprecate",
        json={},
    )
    assert missing_deprecate.status_code == 404

    direct_search = client.get(
        "/api/v1/search",
        params={"query": "kitchen towels", "result_number": 5},
    )
    assert direct_search.status_code == 200
    assert editable_id not in {item["memory_id"] for item in direct_search.json()["memory_results"]}

    neighbor_first = create_memory(client, "First memory.", "2026-09-10T10:00:00Z")
    neighbor_middle = create_memory(client, "Middle memory.", "2026-09-11T10:00:00Z")
    neighbor_last = create_memory(client, "Last memory.", "2026-09-12T10:00:00Z")

    neighbors = client.get(
        f"/api/v1/memories/{neighbor_middle['memory']['memory_id']}",
        params={"memory_range": 1},
    )
    assert neighbors.status_code == 200
    neighbors_body = neighbors.json()
    assert [item["memory_id"] for item in neighbors_body["neighbors_before"]] == [
        neighbor_first["memory"]["memory_id"]
    ]
    assert [item["memory_id"] for item in neighbors_body["neighbors_after"]] == [
        neighbor_last["memory"]["memory_id"]
    ]

    exact = client.get(
        f"/api/v1/memories/{neighbor_middle['memory']['memory_id']}",
        params={"memory_range": 0},
    )
    assert exact.json()["neighbors_before"] == []
    assert exact.json()["neighbors_after"] == []
