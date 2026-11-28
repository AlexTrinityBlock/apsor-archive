"""The one companion context pipeline: every input site, per-run caps, no repeats."""

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.module.agent.domain.companion_context_domain import (
    USER_SUFFIX_KEYS,
    merge_user_suffixes,
    render_contributions,
    signal_text,
)
from app.module.agent.domain.tool_catalog import PROMPT_VERSION, TOOLS_VERSION
from app.module.agent.protocol.companion_protocol import ContextContribution
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
)
from app.module.companion.domain.story_domain import (
    TEMPLATE_EQUAL_ADDRESS_RULE,
    TEMPLATE_PERSONA_RULES,
)
from app.module.companion.service.companion_context_contributor import (
    CompanionContextContributor,
)
from app.module.companion.service.lore_recall import RecalledLore
from app.module.companion.service.seed_catalog import seed_runtime_config
from app.module.companion.service.story_config import StaticStoryConfigProvider
from tests.helpers import create_text
from tests.test_chat_attachments import upload_image
from tests.test_companion_stories import (  # noqa: F401 - imported fixture
    _KeywordEmbedder,
    semantic_embedder,
)

DEFAULT_RUNTIME_CONFIG = seed_runtime_config()
PERSONA_RULES = DEFAULT_RUNTIME_CONFIG.template(TEMPLATE_PERSONA_RULES)
EQUAL_ADDRESS_RULE = DEFAULT_RUNTIME_CONFIG.template(TEMPLATE_EQUAL_ADDRESS_RULE)

CONVERSATIONS = "/api/v1/agent/conversations"


def _conversation(client: TestClient) -> int:
    response = client.post(CONVERSATIONS, json={"title": "Context"})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _send(client: TestClient, conversation_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"{CONVERSATIONS}/{conversation_id}/messages",
        json=payload,
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _user(turn: dict[str, Any]) -> dict[str, Any]:
    return next(entry for entry in turn["entries"] if entry["kind"] == "pi.user")


def _tool_results(turn: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in turn["entries"] if entry["kind"] == "pi.tool-result"]


def _offered_ids(turn: dict[str, Any]) -> list[str]:
    ids = list(_user(turn)["data"].get("companion_context_ids") or [])
    for result in _tool_results(turn):
        ids.extend(item["id"] for item in result["data"].get("lore", []))
    return ids


# --- pure rendering ---------------------------------------------------------------


def _item(fragment_id: str, moment: str = "topical", guidance: str = "G") -> ContextContribution:
    return ContextContribution(
        id=fragment_id,
        weight="everyday",
        text=f"Text <{fragment_id}>",
        moment=moment,  # type: ignore[arg-type]
        guidance=guidance,
    )


def test_render_contributions_is_one_block_with_guidance_once() -> None:
    assert render_contributions([]) == ""
    block = render_contributions([_item("a-1"), _item("a-2")])
    assert block.startswith('<librarian_memories moment="topical">')
    assert block.count("<guidance") == 1
    assert block.count("<librarian_memory ") == 2
    assert "&lt;a-1&gt;" in block, "memory text is escaped"
    mixed = render_contributions([_item("a-1", "story", "S"), _item("a-2", "self", "T")])
    assert mixed.startswith("<librarian_memories>")
    assert mixed.count("<guidance") == 2


def test_user_suffixes_keep_their_order_and_read_the_legacy_key() -> None:
    assert USER_SUFFIX_KEYS == ("time_context", "companion_context", "story_moment")
    data = {"story_moment": "legacy", "time_context": "time", "companion_context": "lore"}
    assert merge_user_suffixes(data) == ["time", "lore", "legacy"]
    assert merge_user_suffixes(None) == []
    assert signal_text("<a>Hello</a>", None, "  world ") == "Hello world"


# --- contributor policy (unit) ----------------------------------------------------


class _FakeRecall:
    def __init__(
        self,
        *,
        answered: Sequence[RecalledLore] = (),
        moment: RecalledLore | None = None,
    ) -> None:
        self.answered = list(answered)
        self.moment = moment
        self.calls: list[dict[str, Any]] = []

    async def recall(self, query: str, context: Sequence[str] = (), **kwargs: Any) -> Any:
        self.calls.append({"query": query, "context": tuple(context), **kwargs})
        return [item for item in self.answered if item.id not in kwargs["exclude"]][
            : kwargs["limit"]
        ]

    async def story_moment(self, *, exclude: frozenset[str] = frozenset()) -> Any:
        self.calls.append({"story_moment": True, "exclude": exclude})
        return self.moment if self.moment and self.moment.id not in exclude else None


def _lore(fragment_id: str, moment: str = "self") -> RecalledLore:
    return RecalledLore(id=fragment_id, text="t", weight="everyday", score=1.0, moment=moment)  # type: ignore[arg-type]


def test_user_message_prefers_self_query_then_story_moment() -> None:
    config = StaticStoryConfigProvider(DEFAULT_RUNTIME_CONFIG)
    recall = _FakeRecall(answered=[_lore("v-1")], moment=_lore("v-9", "story"))
    contributor = CompanionContextContributor(recall=recall, config=config)  # type: ignore[arg-type]
    answered = asyncio.run(contributor.contribute(site="user_message", text="Tell me about you"))
    assert [item.id for item in answered] == ["v-1"]
    assert recall.calls[0]["allow_topical"] is False

    recall = _FakeRecall(moment=_lore("v-9", "story"))
    contributor = CompanionContextContributor(recall=recall, config=config)  # type: ignore[arg-type]
    moment = asyncio.run(contributor.contribute(site="user_message", text="hello"))
    assert [item.id for item in moment] == ["v-9"]


def test_contributor_caps_each_run_and_never_repeats() -> None:
    config = StaticStoryConfigProvider(replace(DEFAULT_RUNTIME_CONFIG, max_contributions_per_run=2))
    recall = _FakeRecall(answered=[_lore("v-1"), _lore("v-2"), _lore("v-3")])
    contributor = CompanionContextContributor(recall=recall, config=config)  # type: ignore[arg-type]
    first = asyncio.run(
        contributor.contribute(site="tool_result", text="x", offered=frozenset({"v-1"}))
    )
    assert [item.id for item in first] == ["v-2"], "one slot left; v-1 already offered"
    assert recall.calls[-1]["allow_self_query"] is False, "no query means no self query"
    spent = asyncio.run(
        contributor.contribute(site="tool_result", text="x", offered=frozenset({"v-1", "v-2"}))
    )
    assert spent == []


# --- every input site through the agent ------------------------------------------


def test_page_context_offers_topical_lore_with_the_message(
    client: TestClient,
    semantic_embedder: _KeywordEmbedder,  # noqa: F811
) -> None:
    """A document preview the person is reading may surface a matching memory."""
    generator = FakeChatGenerator([text_result("ok.")])
    client.app.state.agent_chat_generator = generator
    turn = _send(
        client,
        _conversation(client),
        {
            "content": "What is this page about?",
            "page_context": {
                "key": "library:file:1",
                "path": "/library/garden.md",
                "title": "Garden notes",
                "text": "Planting every seed in spring rows.",
            },
        },
    )
    data = _user(turn)["data"]
    # Nothing is locked: any seed memory of hers may surface, everyday first.
    assert data["companion_context_ids"][0] == "vellum-001"
    assert data["companion_context"].startswith('<librarian_memories moment="topical"')
    sent = generator.requests[0].messages
    user_messages = [m["content"] for m in sent if m.get("role") == "user"]
    assert any("<librarian_memories" in content for content in user_messages)


def test_attachment_names_offer_topical_lore(
    client: TestClient,
    semantic_embedder: _KeywordEmbedder,  # noqa: F811
) -> None:
    """Only attachment display names are read (never bytes) to find a memory."""
    attachment = upload_image(client, "seed-packets.png")
    client.app.state.agent_chat_generator = FakeChatGenerator([text_result("ok.")])
    turn = _send(
        client,
        _conversation(client),
        {"content": "Look at this.", "attachment_ids": [attachment["id"]]},
    )
    assert _user(turn)["data"]["companion_context_ids"][0] == "vellum-001"


def test_tool_results_offer_lore_once_per_run_with_the_trace_shape(
    client: TestClient,
    semantic_embedder: _KeywordEmbedder,  # noqa: F811
) -> None:
    """read_file and present_resource results carry lore; a run never repeats one."""
    created = create_text(client, "/notes/clock.md", "The old clock and the seed tin.")
    file_id = int(created["id"])
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result("read_file", {"file_id": file_id}, call_id="call_read"),
            tool_call_result("read_file", {"file_id": file_id}, call_id="call_again"),
            tool_call_result(
                "present_resource",
                {"resource_type": "file", "resource_id": file_id},
                call_id="call_present",
            ),
            text_result("Here it is."),
        ]
    )
    turn = _send(client, _conversation(client), {"content": "Open my note."})
    results = _tool_results(turn)
    assert [result["data"]["tool"] for result in results] == [
        "read_file",
        "read_file",
        "present_resource",
    ]
    first_lore = results[0]["data"]["lore"]
    assert first_lore, "the first read surfaces the companion's own memory"
    for item in first_lore:
        assert set(item) == {"id", "weight", "text", "moment"}
        assert item["moment"] == "topical"
    content = results[0]["model"][0]["content"]
    assert content.index("<librarian_memories") > content.index("clock")
    offered = _offered_ids(turn)
    assert len(offered) == len(set(offered)), "no fragment repeats within a run"
    assert len(offered) <= DEFAULT_RUNTIME_CONFIG.max_contributions_per_run


def test_frozen_persona_carries_configured_rules_and_versions(client: TestClient) -> None:
    """Rules come from the config templates; versions record the pipeline change."""
    client.app.state.agent_chat_generator = FakeChatGenerator([])
    conversation_id = _conversation(client)
    detail = client.get(f"{CONVERSATIONS}/{conversation_id}").json()
    system = next(entry for entry in detail["entries"] if entry["kind"] == "pi.system")
    section = system["data"]["sections"][-1]["content"]
    assert section.index(PERSONA_RULES) < section.index(EQUAL_ADDRESS_RULE)
    assert section.endswith(EQUAL_ADDRESS_RULE)
    assert system["data"]["prompt_version"] == PROMPT_VERSION == "archive-agent-v22"
    catalog = client.get("/api/v1/agent/tools").json()
    assert catalog["tools_version"] == TOOLS_VERSION == "archive-tools-v21"


@pytest.mark.parametrize("disabled", [True])
def test_no_contributions_without_a_frozen_companion(
    client: TestClient,
    semantic_embedder: _KeywordEmbedder,  # noqa: F811
    disabled: bool,
) -> None:
    """A conversation started with the companion off gets nothing at any site."""
    client.patch("/api/v1/companions/preference", json={"enabled": not disabled})
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result("search_knowledge", {"query": "seed"}, call_id="call_s"),
            text_result("ok."),
        ]
    )
    turn = _send(client, _conversation(client), {"content": "Tell me about yourself"})
    assert _offered_ids(turn) == []
    assert "companion_context" not in _user(turn)["data"]
