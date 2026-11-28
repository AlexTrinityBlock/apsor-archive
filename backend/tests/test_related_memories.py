"""Related memories ranked from stored embeddings, keywords, and summaries."""

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import UserClient
from tests.helpers import create_memory, create_text


def _memory_id(created: dict[str, object]) -> int:
    memory = created["memory"]
    assert isinstance(memory, dict)
    return int(memory["memory_id"])


def _related(client: TestClient, memory_id: int, **params: object) -> dict[str, object]:
    response = client.get(f"/api/v1/memories/{memory_id}/related", params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _ids(body: dict[str, object]) -> list[int]:
    resources = body["resources"]
    assert isinstance(resources, list)
    return [int(item["memory"]["memory_id"]) for item in resources]


def test_similar_memory_ranks_above_unrelated(client: TestClient) -> None:
    source = _memory_id(
        create_memory(
            client,
            "The sourdough starter needs rye flour and warm water every morning.",
            "2026-09-01T08:00:00Z",
        )
    )
    similar = _memory_id(
        create_memory(
            client,
            "Feed the sourdough starter with rye flour before baking bread.",
            "2026-09-02T08:00:00Z",
        )
    )
    unrelated = _memory_id(
        create_memory(
            client,
            "The bicycle chain was replaced at the downtown repair shop.",
            "2026-03-01T08:00:00Z",
        )
    )

    body = _related(client, source)
    assert body["source_kind"] == "memory"
    assert body["source_id"] == source
    ids = _ids(body)
    assert source not in ids
    assert similar in ids
    if unrelated in ids:
        assert ids.index(similar) < ids.index(unrelated)
    resources = body["resources"]
    assert isinstance(resources, list)
    first = resources[ids.index(similar)]
    assert "keyword" in first["reasons"] or "similar" in first["reasons"]
    assert "nearby" in first["reasons"]


def test_chain_and_deprecated_memories_are_excluded(client: TestClient) -> None:
    old = _memory_id(
        create_memory(
            client,
            "The garden tomatoes grow beside the basil planter.",
            "2026-09-01T08:00:00Z",
        )
    )
    source = _memory_id(
        create_memory(
            client,
            "The garden tomatoes now grow beside the basil and mint planter.",
            "2026-09-02T08:00:00Z",
            supersedes=[old],
        )
    )
    retired = _memory_id(
        create_memory(
            client,
            "Garden tomatoes and basil share the sunny planter.",
            "2026-09-03T08:00:00Z",
        )
    )
    deprecated = client.post(f"/api/v1/memories/{retired}/deprecate", json={})
    assert deprecated.status_code == 200, deprecated.text

    default_ids = _ids(_related(client, source))
    assert old not in default_ids
    assert source not in default_ids
    assert retired not in default_ids

    with_deprecated = _ids(_related(client, source, include_deprecated="true"))
    assert retired in with_deprecated
    assert old not in with_deprecated


def test_shared_summary_adds_reason(client: TestClient) -> None:
    first = _memory_id(
        create_memory(client, "Quarterly tax forms were mailed.", "2026-09-01T08:00:00Z")
    )
    second = _memory_id(
        create_memory(client, "The violin lesson moved to Thursday.", "2026-09-02T08:00:00Z")
    )
    summary = client.post("/api/v1/summaries", json={"memory_ids": [first, second]})
    assert summary.status_code == 201, summary.text
    summary_id = int(summary.json()["memory_summary_id"])

    body = _related(client, first)
    resources = body["resources"]
    assert isinstance(resources, list)
    match = next(item for item in resources if item["memory"]["memory_id"] == second)
    assert "summary" in match["reasons"]
    assert match["shared_summary_ids"] == [summary_id]


def test_file_related_memories(client: TestClient) -> None:
    memory = _memory_id(
        create_memory(
            client,
            "The lighthouse keeper logbook records storms along the northern coast.",
            "2026-09-01T08:00:00Z",
        )
    )
    created = create_text(
        client,
        "/notes/lighthouse.md",
        "Lighthouse keeper logbook: storms on the northern coast damaged the lamp.",
    )
    file_id = int(str(created["id"]))

    response = client.get(f"/api/v1/memories/related/files/{file_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_kind"] == "file"
    assert body["source_id"] == file_id
    assert memory in _ids(body)

    deleted = client.delete(f"/api/v1/files/{file_id}")
    assert deleted.status_code in {200, 204}, deleted.text
    missing = client.get(f"/api/v1/memories/related/files/{file_id}")
    assert missing.status_code == 404
    assert missing.json()["error"] == "file_not_found"


def test_related_validation_and_not_found(client: TestClient) -> None:
    memory = _memory_id(create_memory(client, "A single memory.", "2026-09-01T08:00:00Z"))
    for limit in (0, 21):
        response = client.get(f"/api/v1/memories/{memory}/related", params={"limit": limit})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_request"

    unknown = client.get("/api/v1/memories/999999/related")
    assert unknown.status_code == 404
    assert unknown.json()["error"] == "memory_not_found"

    unknown_file = client.get("/api/v1/memories/related/files/999999")
    assert unknown_file.status_code == 404


def test_related_memories_stay_inside_the_account(
    client: TestClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    text = "The orchard apple harvest filled twelve wooden crates."
    owner_memory = _memory_id(create_memory(client, text, "2026-09-01T08:00:00Z"))
    member = user_client_factory("related.member")
    member_source = _memory_id(create_memory(member.client, text, "2026-09-01T08:00:00Z"))
    member_twin = _memory_id(
        create_memory(member.client, text + " Again.", "2026-09-02T08:00:00Z")
    )

    member_ids = _ids(_related(member.client, member_source))
    assert owner_memory not in member_ids
    assert member_twin in member_ids

    foreign = member.client.get(f"/api/v1/memories/{owner_memory}/related")
    assert foreign.status_code == 404
