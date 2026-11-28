"""Short web ids: every web page a conversation sees gets a stable [web:wN]."""

import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.module.agent.domain.web_source_domain import (
    clean_title,
    ephemeral_refs,
    parse_web_ref,
    web_ref,
)
from app.module.agent.service.agent_service import CITATION_PATTERN
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
)
from app.module.web_research.schema.web_research_schema import WebSearchHit
from tests.conftest import UserClient
from tests.test_agent import ANSWER_USAGE, TOOL_USAGE, FakeWebResearchService

HITS = [
    WebSearchHit(
        title="Tea ceremony history",
        url="https://example.com/tea",
        content="The ceremony took its form in the sixteenth century.",
        score=0.9,
    ),
    WebSearchHit(
        title="Kyoto gardens",
        url="https://example.com/gardens",
        content="Moss gardens need shade and patience.",
        score=0.7,
    ),
]


def _turn(
    client: TestClient,
    conversation_id: int,
    steps: list[Any],
    content: str,
) -> dict[str, Any]:
    client.app.state.agent_chat_generator = FakeChatGenerator(steps)
    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": content},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["run"]["status"] == "completed"
    return body


def _search(call_id: str) -> Any:
    return tool_call_result(
        "web_search",
        {"query": "tea ceremony", "objective": "Find the ceremony's history."},
        call_id=call_id,
        usage=TOOL_USAGE,
    )


def _fetch(url: str, call_id: str) -> Any:
    return tool_call_result("web_fetch", {"url": url}, call_id=call_id, usage=TOOL_USAGE)


def _result_ids(xml: str) -> list[str]:
    start = xml.index("<web_search ")
    end = xml.index("</web_search>") + len("</web_search>")
    root = ElementTree.fromstring(xml[start:end])
    return [hit.attrib["id"] for hit in root.findall("result")]


def test_web_ids_are_numbered_by_first_appearance_and_reused(client: TestClient) -> None:
    client.app.state.web_research_service = FakeWebResearchService(search_results=HITS)
    conversation = client.post("/api/v1/agent/conversations", json={"title": "Tea"})
    assert conversation.status_code == 201, conversation.text
    conversation_id = conversation.json()["id"]

    first = _turn(
        client,
        conversation_id,
        [
            _search("call_search"),
            _fetch("https://example.com/gardens", "call_fetch_known"),
            _fetch("https://example.com/new-page", "call_fetch_new"),
            text_result(
                "The ceremony is old [web:w1], and gardens need shade ［web:w2］.",
                usage=ANSWER_USAGE,
            ),
        ],
        "Tell me about the tea ceremony.",
    )
    search_result, known_fetch, new_fetch = first["tool_results"]
    assert _result_ids(search_result["model"][0]["content"]) == ["w1", "w2"]
    assert [item["ref"] for item in search_result["data"]["results"]] == ["w1", "w2"]
    assert "[web:w3]" in search_result["model"][0]["content"]  # the hint's example
    assert 'id="w2"' in known_fetch["model"][0]["content"]
    assert known_fetch["data"]["ref"] == "w2"
    assert new_fetch["data"]["ref"] == "w3"
    assistant = [entry for entry in first["entries"] if entry["kind"] == "pi.assistant"][-1]
    assert assistant["data"]["citations"] == ["[web:w1]", "［web:w2］"]

    # A later turn keeps the numbers: the same URL comes back as w1.
    second = _turn(
        client,
        conversation_id,
        [_search("call_search_again"), text_result("Same sources.", usage=ANSWER_USAGE)],
        "Search again.",
    )
    assert _result_ids(second["tool_results"][0]["model"][0]["content"]) == ["w1", "w2"]

    sources = client.get(f"/api/v1/agent/conversations/{conversation_id}/web-sources")
    assert sources.status_code == 200, sources.text
    assert sources.json() == [
        {"ref": "w1", "url": "https://example.com/tea", "title": "Tea ceremony history"},
        {"ref": "w2", "url": "https://example.com/gardens", "title": "Kyoto gardens"},
        {"ref": "w3", "url": "https://example.com/new-page", "title": None},
    ]


def test_web_ids_restart_per_conversation_and_stay_private(
    client: TestClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    client.app.state.web_research_service = FakeWebResearchService(search_results=HITS[1:])
    first = client.post("/api/v1/agent/conversations", json={"title": "One"}).json()["id"]
    second = client.post("/api/v1/agent/conversations", json={"title": "Two"}).json()["id"]
    _turn(client, first, [_search("a"), text_result("ok", usage=ANSWER_USAGE)], "Find it.")
    body = _turn(client, second, [_search("b"), text_result("ok", usage=ANSWER_USAGE)], "Find.")
    assert _result_ids(body["tool_results"][0]["model"][0]["content"]) == ["w1"]

    other = user_client_factory().client
    response = other.get(f"/api/v1/agent/conversations/{first}/web-sources")
    assert response.status_code == 404
    assert response.json()["error"] == "agent_conversation_not_found"


def test_web_source_domain_helpers() -> None:
    assert web_ref(3) == "w3"
    assert parse_web_ref("w12") == 12
    assert parse_web_ref("w0") is None
    assert parse_web_ref("x3") is None
    assert clean_title("  Moss \n gardens ") == "Moss gardens"
    assert clean_title("   ") is None
    assert ephemeral_refs(["a", "b", "a", "c"]) == {"a": 1, "b": 2, "c": 3}
    assert CITATION_PATTERN.findall("see [web:w4] and [web:w0] and [web:x1]") == ["[web:w4]"]
