"""Assignment-driven model selection, pinning, and the escalation ladder.

Every provider call is a deterministic fake built by a recording factory; the
suite never reaches a real endpoint. Assignments are written through the root
API with the provider probe seam, exactly as an operator would write them.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.ai.probe import ProbeOutcome
from app.infrastructure.ai.runtime import AiRuntime
from app.module.agent.protocol.chat_generator_protocol import ChatGeneratorProtocol
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
)
from app.module.knowledge.protocol.provider_config import ProviderConfig
from tests.conftest import UserClient

DEFAULT_COMPACTION_PROMPT_BOUND = "{max_output_tokens}"


class FakeProviderProbe:
    """Deterministic probe so an assignment save never calls a provider."""

    async def probe(
        self,
        config: ProviderConfig,
        *,
        model: str,
        reasoning_effort: str | None,
    ) -> ProbeOutcome:
        del config, model, reasoning_effort
        return ProbeOutcome(
            ok=True,
            latency_ms=2,
            resolved_model="ok",
            usage={"input_tokens": 1, "output_tokens": 1},
            detail=None,
        )


class RecordingBuilder:
    """Return one scripted fake per model string and record every build."""

    def __init__(self, generators: dict[str, FakeChatGenerator]) -> None:
        self.generators = generators
        self.built_models: list[str] = []

    def build_text_generator(self, config: ProviderConfig) -> ChatGeneratorProtocol:
        model = config.model or ""
        self.built_models.append(model)
        generator = self.generators.get(model)
        if generator is None:
            generator = FakeChatGenerator.from_texts(f"No generator for {model}.")
            self.generators[model] = generator
        return generator


def _create_chat_row(
    client: TestClient,
    *,
    label: str,
    model: str,
    provider: str,
    base_url: str,
    api_key: str = "sk-routing-key-1234",
) -> int:
    response = client.post(
        "/api/v1/settings/providers/chat",
        json={
            "provider": provider,
            "label": label,
            "model": model,
            "base_url": base_url,
            "api_key": api_key,
            "activate": True,
        },
    )
    assert response.status_code == 200, response.text
    chat = next(
        group
        for group in response.json()["capabilities"]
        if group["capability"] == "chat"
    )
    return int(next(item["id"] for item in chat["providers"] if item["label"] == label))


def _assign(
    client: TestClient,
    user_id: int,
    row_id: int,
    *,
    chat_model: str,
    effort: str | None = "low",
    window: int | None = None,
    threshold: int | None = None,
) -> None:
    response = client.put(
        f"/api/v1/model-assignments/{user_id}",
        json={
            "chat_provider_config_id": row_id,
            "chat_model": chat_model,
            "chat_reasoning_effort": effort,
            "aux_provider_config_id": row_id,
            "aux_model": chat_model,
            "aux_reasoning_effort": "low",
            "context_window_tokens": window,
            "compaction_threshold_tokens": threshold,
        },
    )
    assert response.status_code == 200, response.text


def _new_conversation(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/agent/conversations", json={"title": "Routing"})
    assert response.status_code == 201, response.text
    return response.json()


def _send(client: TestClient, conversation_id: int, content: str = "Hello.") -> Any:
    return client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": content},
        headers={"Accept": "application/json"},
    )


def _install_builder(client: TestClient, builder: RecordingBuilder) -> None:
    runtime = client.app.state.ai_runtime
    assert isinstance(runtime, AiRuntime)
    runtime.builder = builder


def _notices(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in body["entries"] if entry["kind"] == "ui.notice"]


def test_primary_assignment_is_used_instead_of_the_runtime_default(
    client: TestClient,
    root_account: UserClient,
) -> None:
    """The assigned primary supplies the model, not ``runtime.chat_config``."""
    client.app.state.provider_probe = FakeProviderProbe()
    row_id = _create_chat_row(
        client,
        label="primary",
        model="row-placeholder",
        provider="deepseek",
        base_url="https://api.deepseek.com",
    )
    _assign(
        client,
        root_account.user_id,
        row_id,
        chat_model="claude-haiku-5-5",
        effort="high",
    )
    runtime = client.app.state.ai_runtime
    assert runtime.chat_config.model != "claude-haiku-5-5"

    haiku = FakeChatGenerator.from_texts("Assigned answer.")
    builder = RecordingBuilder({"claude-haiku-5-5": haiku})
    _install_builder(client, builder)

    conversation = _new_conversation(client)
    builder.built_models.clear()
    assert conversation["model"] == "claude-haiku-5-5"
    assert conversation["provider"] == "deepseek"

    turn = _send(client, int(conversation["id"]))
    assert turn.status_code == 200, turn.text
    body = turn.json()
    assert body["run"]["status"] == "completed"
    assert body["answer"] == "Assigned answer."
    assert builder.built_models == ["claude-haiku-5-5"]
    assert haiku.requests[0].model == "claude-haiku-5-5"
    assert not _notices(body)


def test_unknown_model_is_pinned_without_escalation(
    client: TestClient,
    root_account: UserClient,
) -> None:
    """An unknown primary has ``tier=None``: it never escalates."""
    client.app.state.provider_probe = FakeProviderProbe()
    row_id = _create_chat_row(
        client,
        label="primary",
        model="claude-haiku-5-5",
        provider="anthropic",
        base_url="https://api.anthropic.com",
    )
    _assign(
        client,
        root_account.user_id,
        row_id,
        chat_model="totally-unknown-model",
    )
    pinned = FakeChatGenerator(
        [text_result("Pinned refusal.", finish_reason="refusal")]
    )
    builder = RecordingBuilder({"totally-unknown-model": pinned})
    _install_builder(client, builder)

    conversation = _new_conversation(client)
    builder.built_models.clear()
    turn = _send(client, int(conversation["id"]))
    assert turn.status_code == 200, turn.text
    body = turn.json()
    assert body["run"]["status"] == "completed"
    assert body["answer"] == "Pinned refusal."
    assert builder.built_models == ["totally-unknown-model"]
    assert len(pinned.requests) == 1
    assert not _notices(body)


def test_refusal_escalates_once_to_the_next_catalog_tier(
    client: TestClient,
    root_account: UserClient,
) -> None:
    """One refusal swaps to the next tier on the same row and notices it."""
    client.app.state.provider_probe = FakeProviderProbe()
    row_id = _create_chat_row(
        client,
        label="primary",
        model="claude-haiku-5-5",
        provider="anthropic",
        base_url="https://api.anthropic.com",
    )
    _assign(
        client,
        root_account.user_id,
        row_id,
        chat_model="claude-haiku-5-5",
    )
    haiku = FakeChatGenerator(
        [text_result("I cannot help with that.", finish_reason="refusal")]
    )
    sonnet = FakeChatGenerator.from_texts("Escalated answer.")
    builder = RecordingBuilder(
        {"claude-haiku-5-5": haiku, "claude-sonnet-5-5": sonnet}
    )
    _install_builder(client, builder)

    conversation = _new_conversation(client)
    builder.built_models.clear()
    turn = _send(client, int(conversation["id"]))
    assert turn.status_code == 200, turn.text
    body = turn.json()
    assert body["run"]["status"] == "completed"
    assert body["answer"] == "Escalated answer."
    assert builder.built_models == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    assert haiku.requests[0].model == "claude-haiku-5-5"
    assert sonnet.requests[0].model == "claude-sonnet-5-5"
    notices = _notices(body)
    assert len(notices) == 1
    assert notices[0]["data"] == {
        "reason": "refusal",
        "from_model": "claude-haiku-5-5",
        "to_model": "claude-sonnet-5-5",
    }


def test_top_tier_primary_has_no_escalation_target(
    client: TestClient,
    root_account: UserClient,
) -> None:
    """A frontier primary is legal, pinned, and never escalates."""
    client.app.state.provider_probe = FakeProviderProbe()
    row_id = _create_chat_row(
        client,
        label="primary",
        model="claude-fable-5-2",
        provider="anthropic",
        base_url="https://api.anthropic.com",
    )
    _assign(
        client,
        root_account.user_id,
        row_id,
        chat_model="claude-fable-5-2",
    )
    fable = FakeChatGenerator(
        [text_result("Frontier refusal.", finish_reason="refusal")]
    )
    builder = RecordingBuilder({"claude-fable-5-2": fable})
    _install_builder(client, builder)

    conversation = _new_conversation(client)
    builder.built_models.clear()
    turn = _send(client, int(conversation["id"]))
    assert turn.status_code == 200, turn.text
    body = turn.json()
    assert body["run"]["status"] == "completed"
    assert body["answer"] == "Frontier refusal."
    assert builder.built_models == ["claude-fable-5-2"]
    assert len(fable.requests) == 1
    assert not _notices(body)


def test_account_context_window_overrides_the_global_budget(
    client: TestClient,
    root_account: UserClient,
) -> None:
    """The assignment's stored window drives the local budget, not the global row."""
    client.app.state.provider_probe = FakeProviderProbe()
    row_id = _create_chat_row(
        client,
        label="primary",
        model="claude-haiku-5-5",
        provider="anthropic",
        base_url="https://api.anthropic.com",
    )
    _assign(
        client,
        root_account.user_id,
        row_id,
        chat_model="claude-haiku-5-5",
        window=8_000,
        threshold=1_000,
    )
    fake = FakeChatGenerator.from_texts("Budgeted answer.")
    builder = RecordingBuilder({"claude-haiku-5-5": fake})
    _install_builder(client, builder)

    conversation = _new_conversation(client)
    builder.built_models.clear()
    turn = _send(client, int(conversation["id"]), "BEGIN " + "q" * 31_900)
    assert turn.status_code == 200, turn.text
    body = turn.json()
    assert body["run"]["status"] == "completed"
    assert body["answer"] == "Budgeted answer."
    notices = _notices(body)
    assert len(notices) == 1
    assert notices[0]["data"]["reason"] == "context_budget_truncated"
    assert notices[0]["data"]["budget_tokens"] == 8_000


def test_anthropic_is_an_accepted_conversation_provider(client: TestClient) -> None:
    """The transcript provider literal accepts the native Anthropic adapter."""
    response = client.post(
        "/api/v1/agent/conversations",
        json={"provider": "anthropic", "model": "claude-haiku-5-5"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-haiku-5-5"


def test_missing_assignment_is_a_configuration_error(client: TestClient) -> None:
    """No assignment is 409 ``model_not_assigned`` before the stream starts."""
    conversation = _new_conversation(client)
    turn = _send(client, int(conversation["id"]))
    assert turn.status_code == 409, turn.text
    assert turn.json()["error"] == "model_not_assigned"


def test_inactive_endpoint_is_a_provider_configuration_error(
    client: TestClient,
    root_account: UserClient,
) -> None:
    """Deactivating the assigned row becomes 409 ``provider_inactive``."""
    client.app.state.provider_probe = FakeProviderProbe()
    row_id = _create_chat_row(
        client,
        label="primary",
        model="claude-haiku-5-5",
        provider="anthropic",
        base_url="https://api.anthropic.com",
    )
    _assign(
        client,
        root_account.user_id,
        row_id,
        chat_model="claude-haiku-5-5",
    )
    deactivated = client.post(
        f"/api/v1/settings/providers/chat/{row_id}/deactivate"
    )
    assert deactivated.status_code == 200, deactivated.text

    conversation = _new_conversation(client)
    turn = _send(client, int(conversation["id"]))
    assert turn.status_code == 409, turn.text
    assert turn.json()["error"] == "provider_inactive"


@pytest.mark.parametrize(
    "template",
    [
        "No output bound at all.",
        "Bound by {max_output_tokens} and {unknown_placeholder}.",
        "Bound by {max_output_tokens",
    ],
)
def test_invalid_compaction_prompt_is_a_stable_422(
    client: TestClient,
    template: str,
) -> None:
    """A template the renderer cannot substitute is 422, not 400."""
    defaults = client.get("/api/v1/agent/settings").json()["defaults"]
    response = client.put(
        "/api/v1/agent/settings",
        json={**defaults, "compaction_prompt": template},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "compaction_prompt_invalid"


def test_settings_round_trip_includes_the_four_new_fields(client: TestClient) -> None:
    """The settings surface reads and writes the compaction and cap fields."""
    defaults = client.get("/api/v1/agent/settings").json()["defaults"]
    assert defaults["compaction_prompt"].count(DEFAULT_COMPACTION_PROMPT_BOUND) == 1
    assert defaults["compaction_max_output_tokens"] == 2_600
    assert defaults["model_escalation_enabled"] is True
    assert defaults["agent_max_output_tokens"] == 64_000

    updated = client.put(
        "/api/v1/agent/settings",
        json={
            **defaults,
            "compaction_prompt": "Summarize within {max_output_tokens} tokens.",
            "compaction_max_output_tokens": 4_096,
            "model_escalation_enabled": False,
            "agent_max_output_tokens": 32_000,
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()["config"]
    assert body["compaction_prompt"] == (
        "Summarize within {max_output_tokens} tokens."
    )
    assert body["compaction_max_output_tokens"] == 4_096
    assert body["model_escalation_enabled"] is False
    assert body["agent_max_output_tokens"] == 32_000

    reset = client.post("/api/v1/agent/settings/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["config"] == defaults
