"""Hybrid search, union ranking, and summary retrieval."""

from fastapi.testclient import TestClient

from tests.helpers import create_memory, create_text


def test_hybrid_search_and_union_query(client: TestClient) -> None:
    create_text(
        client,
        "/research/tools.md",
        "The wrench slipped on the chassis. A wrench is a hand tool.",
        "2026-09-01T09:00:00Z",
    )
    memory = create_memory(
        client,
        "The user bought a wrench for the chassis repair.",
        "2026-09-02T10:00:00Z",
    )
    memory_id = int(memory["memory"]["memory_id"])

    summary = client.post(
        "/api/v1/summaries",
        json={"memory_ids": [memory_id], "force": True},
    )
    assert summary.status_code == 201

    search = client.get(
        "/api/v1/search",
        params={"query": "wrench", "result_number": 2},
    )
    assert search.status_code == 200
    body = search.json()
    assert body["file_results"]
    assert body["memory_results"]
    assert body["summary_results"]

    stats = body["stats"]
    assert stats["text_candidates"] <= 6
    assert stats["vector_candidates"] <= 6
    assert stats["merged"] <= 12
    assert stats["deduplicated"] == (
        stats["text_candidates"] + stats["vector_candidates"] - stats["merged"]
    )

    tool = client.get(
        "/api/v1/tools/search_knowledge",
        params={"query": "wrench", "result_number": 2},
    )
    assert tool.status_code == 200
    assert "<search_result" in tool.text
    assert "<file_result" in tool.text
    assert "<memory_result" in tool.text

    both = create_text(
        client,
        "/research/both.md",
        "Automobile history and Ford production changed transportation.",
        "2026-09-03T09:00:00Z",
    )
    only = create_text(
        client,
        "/research/only.md",
        "Automobile history changed transportation in many countries.",
        "2026-09-04T09:00:00Z",
    )

    union = client.get(
        "/api/v1/search",
        params={"query": "automobile ford", "result_number": 2},
    )
    assert union.status_code == 200
    file_results = union.json()["file_results"]
    file_ids = [item["file_id"] for item in file_results]
    assert file_ids[0] == both["id"]
    assert only["id"] in file_ids
