"""The local context budget: forced compaction, clipping, and truncation.

The HTTP cases seed a large immutable transcript directly (the public message
limit is 32K characters) and then drive a real turn through deterministic
fakes. The pure cases exercise the message-level ladder without a database.
"""

import json
import re
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.module.agent.domain.agent_domain import ProviderContext
from app.module.agent.domain.compaction_domain import (
    estimate_provider_context_tokens,
)
from app.module.agent.service import agent_service as agent_service_module
from app.module.agent.service.agent_service import _fit_provider_context
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
)
from tests.conftest import UserClient

CHARS_PER_TOKEN = 3.0
TRUNCATION_PREFIX = "[… truncated "


def _seed_archive_context(
    engine: Engine,
    *,
    user_id: int,
    conversation_id: int,
    entries: int,
    chars: int,
) -> None:
    """Insert an immutable user/assistant history directly for a size test."""
    with engine.begin() as connection:
        for index in range(entries):
            kind = "pi.user" if index % 2 == 0 else "pi.assistant"
            role = "user" if index % 2 == 0 else "assistant"
            content = f"entry {index:03d} " + ("x" if role == "user" else "y") * chars
            connection.execute(
                text(
                    "INSERT INTO agent_entry "
                    "(user_id, conversation_id, kind, model, created_at) "
                    "VALUES (:user_id, :conversation_id, :kind, "
                    "CAST(:model AS jsonb), now())"
                ),
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "kind": kind,
                    "model": json.dumps([{"role": role, "content": content}]),
                },
            )


def _new_conversation(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Context budget"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _send(client: TestClient, conversation_id: int, content: str) -> Any:
    return client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": content},
        headers={"Accept": "application/json"},
    )


def _context_from_request(request: Any) -> ProviderContext:
    """Rebuild the provider context a fake recorded, without the status block."""
    messages = list(request.messages)
    if (
        messages
        and messages[-1].get("role") == "system"
        and isinstance(messages[-1].get("content"), str)
        and messages[-1]["content"].startswith("<agent_status")
    ):
        messages.pop()
    return ProviderContext(
        system_message=messages[0],
        tools=request.tools,
        messages=messages[1:],
        source_entry_ids=[],
        cache_prefix_hash="",
    )


def _status_attributes(request: Any) -> dict[str, int]:
    """Read the numeric attributes from the trailing agent status block."""
    content = request.messages[-1]["content"]
    return {
        name: int(value)
        for name, value in re.findall(r' ([a-z_]+)="(\d+)"', content)
    }


def _baseline_tokens(client: TestClient) -> int:
    """Measure the frozen system/tools prefix with a warm-up turn."""
    defaults = client.get("/api/v1/agent/settings").json()["defaults"]
    assert defaults["context_window_tokens"] == 1_000_000
    fake = FakeChatGenerator.from_texts("Warm-up.")
    client.app.state.agent_chat_generator = fake
    conversation = _new_conversation(client)
    turn = _send(client, int(conversation["id"]), "warm up")
    assert turn.status_code == 200, turn.text
    return estimate_provider_context_tokens(
        _context_from_request(fake.requests[0]),
        chars_per_token=CHARS_PER_TOKEN,
    )


def test_three_hundred_k_context_truncates_once_and_completes(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    """A ~300K-token history forces compaction, truncation, and one notice."""
    # The budget below is measured to the token; a companion story moment on a
    # later run would add text the warm-up never saw.
    client.patch("/api/v1/companions/preference", json={"enabled": False})
    baseline = _baseline_tokens(client)
    defaults = client.get("/api/v1/agent/settings").json()["defaults"]
    window = min(2_000_000, baseline + 10_500)
    updated = client.put(
        "/api/v1/agent/settings",
        json={
            **defaults,
            "context_window_tokens": window,
            "compaction_threshold_tokens": 1_000,
        },
    )
    assert updated.status_code == 200, updated.text

    fake = FakeChatGenerator.from_texts("The turn still completed.")
    client.app.state.agent_chat_generator = fake
    conversation = _new_conversation(client)
    # 30 entries x 30K characters is ~900K characters, ~300K tokens at the
    # DeepSeek ratio of 3.0 used by the fake runtime model.
    _seed_archive_context(
        owner_engine,
        user_id=root_account.user_id,
        conversation_id=int(conversation["id"]),
        entries=30,
        chars=30_000,
    )
    user_text = "BEGIN " + "q" * 31_900 + " END"
    turn = _send(client, int(conversation["id"]), user_text)
    assert turn.status_code == 200, turn.text
    body = turn.json()
    assert body["run"]["status"] == "completed"
    assert body["answer"] == "The turn still completed."

    # The stored transcript keeps the complete user message.
    assert body["user_entry"]["model"][0]["content"] == user_text

    notices = [entry for entry in body["entries"] if entry["kind"] == "ui.notice"]
    assert len(notices) == 1
    notice = notices[0]["data"]
    assert notice["reason"] == "context_budget_truncated"
    assert notice["budget_tokens"] == window
    assert notice["truncated_user_chars"] > 0
    assert notice["dropped_page_contexts"] == 0
    assert notice["dropped_messages"] == 0

    # Only the outbound copy is shortened, and it keeps both ends.
    outbound_users = [
        message
        for message in fake.requests[0].messages
        if message.get("role") == "user"
    ]
    outbound = outbound_users[-1]["content"]
    assert isinstance(outbound, str)
    assert len(outbound) < len(user_text)
    assert outbound.startswith("BEGIN")
    assert TRUNCATION_PREFIX in outbound


def test_chinese_context_is_counted_conservatively_before_the_call(
    client: TestClient,
) -> None:
    """A CJK-heavy request that fits the old ratio must still hit the ladder."""
    baseline = _baseline_tokens(client)
    defaults = client.get("/api/v1/agent/settings").json()["defaults"]
    window = baseline + 9_000
    updated = client.put(
        "/api/v1/agent/settings",
        json={
            **defaults,
            "context_window_tokens": window,
            "compaction_threshold_tokens": max(1_000, window - 1_000),
            "auto_compaction_enabled": False,
        },
    )
    assert updated.status_code == 200, updated.text

    fake = FakeChatGenerator.from_texts("收到。")
    client.app.state.agent_chat_generator = fake
    conversation = _new_conversation(client)
    user_text = "這是一段需要被計入上下文的中文內容。" * 1_200
    assert 20_000 <= len(user_text) <= 32_000
    # The historical English ratio would keep this request under the budget.
    assert baseline + len(user_text) / CHARS_PER_TOKEN < window
    # A conservative CJK density makes it exceed the budget before the call.
    assert baseline + len(user_text) / 1.6 > window

    turn = _send(client, int(conversation["id"]), user_text)
    assert turn.status_code == 200, turn.text
    body = turn.json()
    assert body["run"]["status"] == "completed"
    assert body["answer"] == "收到。"

    notices = [entry for entry in body["entries"] if entry["kind"] == "ui.notice"]
    assert len(notices) == 1
    assert notices[0]["data"]["reason"] == "context_budget_truncated"
    assert notices[0]["data"]["truncated_user_chars"] > 0

    # The provider never saw the full message, and the status block reports the
    # same conservative estimate for exactly the request that was sent.
    request = fake.requests[0]
    status = _status_attributes(request)
    exact = estimate_provider_context_tokens(
        ProviderContext(
            system_message=request.messages[0],
            tools=request.tools,
            messages=request.messages[1:],
            source_entry_ids=[],
            cache_prefix_hash="",
        ),
        strip_image_data=True,
        chars_per_token=CHARS_PER_TOKEN,
    )
    assert int(status["context_used"]) == exact
    assert int(status["context_used"]) <= window
    assert int(status["context_limit"]) == window


def test_provider_reported_prompt_tokens_force_the_next_step_to_fit(
    client: TestClient,
) -> None:
    """A reported overshoot becomes the floor for the next outbound request."""
    defaults = client.get("/api/v1/agent/settings").json()["defaults"]
    window = 8_000
    updated = client.put(
        "/api/v1/agent/settings",
        json={
            **defaults,
            "context_window_tokens": window,
            "compaction_threshold_tokens": 1_000,
            "auto_compaction_enabled": False,
        },
    )
    assert updated.status_code == 200, updated.text

    fake = FakeChatGenerator(
        [
            tool_call_result(
                "calculate",
                {"expression": "1 + 1"},
                call_id="call_floor",
                usage={
                    "prompt_tokens": 8_100,
                    "completion_tokens": 20,
                    "total_tokens": 8_120,
                },
            ),
            text_result("The answer is 2."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation = _new_conversation(client)
    turn = _send(client, int(conversation["id"]), "Add one and one.")
    assert turn.status_code == 200, turn.text
    body = turn.json()
    assert body["run"]["status"] == "completed"

    notices = [entry for entry in body["entries"] if entry["kind"] == "ui.notice"]
    assert len(notices) == 1
    notice = notices[0]["data"]
    assert notice["reason"] == "context_budget_truncated"
    assert notice["dropped_messages"] >= 1
    assert notice["truncated_user_chars"] > 0

    # The next request cannot drop the provider floor, so every removable
    # message is gone and the status block reports the reported prompt size.
    second = fake.requests[1]
    assert [message["role"] for message in second.messages] == ["system", "system"]
    status = _status_attributes(second)
    assert int(status["context_used"]) == 8_100
    assert int(status["context_remaining"]) == 0
    assert int(status["compaction_in"]) == 0


def test_forced_compaction_targets_sixty_percent_of_the_budget(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
    monkeypatch: Any,
) -> None:
    """The overflow backstop compacts to 60% of the operator's budget."""
    defaults = client.get("/api/v1/agent/settings").json()["defaults"]
    budget = 8_000
    updated = client.put(
        "/api/v1/agent/settings",
        json={
            **defaults,
            "context_window_tokens": budget,
            "compaction_threshold_tokens": 1_000,
        },
    )
    assert updated.status_code == 200, updated.text

    calls: list[dict[str, Any]] = []
    original = agent_service_module.build_compaction_draft

    def recording_build(entries: Any, **kwargs: Any) -> Any:
        calls.append(dict(kwargs))
        return original(entries, **kwargs)

    monkeypatch.setattr(
        agent_service_module,
        "build_compaction_draft",
        recording_build,
    )

    fake = FakeChatGenerator.from_texts("Compacted answer.")
    client.app.state.agent_chat_generator = fake
    conversation = _new_conversation(client)
    _seed_archive_context(
        owner_engine,
        user_id=root_account.user_id,
        conversation_id=int(conversation["id"]),
        entries=4,
        chars=15_000,
    )
    turn = _send(client, int(conversation["id"]), "Summarize " + "s" * 31_900)
    assert turn.status_code == 200, turn.text

    forced = [
        call for call in calls if call.get("reason") == "forced_context_budget"
    ]
    assert forced
    assert forced[0]["target_tokens"] == int(budget * 0.6)
    assert forced[0]["chars_per_token"] == CHARS_PER_TOKEN


def _context(messages: list[dict[str, Any]]) -> ProviderContext:
    return ProviderContext(
        system_message={"role": "system", "content": "You are Apsor Archive."},
        tools=[],
        messages=messages,
        source_entry_ids=[],
        cache_prefix_hash="hash",
    )


def _tool_message(content: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "read_file",
        "content": (
            '<tool_result name="read_file" call_id="call_1">'
            f"{content}"
            "</tool_result>"
        ),
    }


def test_page_context_is_dropped_before_tool_results_are_clipped() -> None:
    """The ladder never clips a tool result while a page snapshot is present."""
    page = {
        "role": "user",
        "content": "<page_context key=\"/library\">" + "p" * 40_000 + "</page_context>",
    }
    tool_body = "t" * 1_500
    context = _context(
        [
            page,
            _tool_message(tool_body),
            {"role": "user", "content": "current question"},
        ]
    )
    budget = estimate_provider_context_tokens(
        _context(
            [
                _tool_message(tool_body),
                {"role": "user", "content": "current question"},
            ]
        ),
        chars_per_token=CHARS_PER_TOKEN,
    ) + 20

    fitted, stats = _fit_provider_context(
        context,
        budget_tokens=budget,
        chars_per_token=CHARS_PER_TOKEN,
    )

    assert stats.dropped_page_contexts == 1
    assert stats.clipped_tool_results == 0
    assert stats.truncated_user_chars == 0
    assert all(
        not (
            isinstance(message.get("content"), str)
            and message["content"].startswith("<page_context")
        )
        for message in fitted.messages
    )


def test_tool_result_clipping_keeps_the_envelope_and_oldest_first_caps() -> None:
    """A large tool body is clipped through the 8K/2K/500 passes, envelope intact."""
    first_body = "a" * 30_000
    second_body = "b" * 100
    context = _context(
        [
            {"role": "user", "content": "read both files"},
            _tool_message(first_body),
            _tool_message(second_body),
            {"role": "user", "content": "now summarize"},
        ]
    )
    # After the 8K pass the estimate is still over this budget, so the ladder
    # must take the next cap rather than stopping at the first pass.
    budget = 900

    fitted, stats = _fit_provider_context(
        context,
        budget_tokens=budget,
        chars_per_token=CHARS_PER_TOKEN,
    )

    assert stats.dropped_page_contexts == 0
    assert stats.clipped_tool_results == 1
    clipped = fitted.messages[1]["content"]
    assert clipped.startswith('<tool_result name="read_file" call_id="call_1">')
    assert clipped.endswith("</tool_result>")
    body = clipped.split(">", 1)[1].rsplit("</tool_result>", 1)[0]
    assert len(body) <= 2_000
    # The small, newer result is untouched.
    assert fitted.messages[2]["content"] == context.messages[2]["content"]
    assert stats.truncated_user_chars == 0


def test_current_user_message_is_truncated_head_and_tail() -> None:
    """The last user message survives at both ends; the input copy is unchanged."""
    original = "OPENING " + "z" * 30_000 + " CLOSING"
    context = _context([{"role": "user", "content": original}])

    fitted, stats = _fit_provider_context(
        context,
        budget_tokens=500,
        chars_per_token=CHARS_PER_TOKEN,
    )

    outbound = fitted.messages[0]["content"]
    assert isinstance(outbound, str)
    assert stats.truncated_user_chars == len(original)
    assert outbound.startswith("OPENING ")
    assert outbound.endswith(" CLOSING")
    assert TRUNCATION_PREFIX in outbound
    assert context.messages[0]["content"] == original


def test_inline_image_is_dropped_after_text_cannot_fit() -> None:
    """A multimodal message drops images only after its text is already over."""
    image = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64," + "A" * 20_000},
    }
    context = _context(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    image,
                ],
            }
        ]
    )

    fitted, stats = _fit_provider_context(
        context,
        budget_tokens=100,
        chars_per_token=CHARS_PER_TOKEN,
    )

    parts = fitted.messages[0]["content"]
    assert isinstance(parts, list)
    assert stats.truncated_attachments == 1
    assert any(
        part.get("text") == "[image omitted: context budget]" for part in parts
    )
