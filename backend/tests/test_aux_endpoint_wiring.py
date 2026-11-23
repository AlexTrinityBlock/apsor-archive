"""Auxiliary endpoint wiring for knowledge services, vision, and the worker.

Every provider call is a deterministic fake installed on ``app.state`` or a
recording builder swapped in for the runtime, so no test reaches DeepSeek,
Anthropic, or any other endpoint. The migrated disposable database supplies
``app_user`` and the provider rows.
"""

import base64
import json
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from starlette.datastructures import State

from app.infrastructure.ai.anthropic_vision import AnthropicVisionExtractor
from app.infrastructure.ai.deepseek_client import NullTextGenerator
from app.infrastructure.ai.probe import ProbeOutcome
from app.infrastructure.ai.user_models import ChatAssignment
from app.infrastructure.ai.vision_extractor import (
    DeepSeekVisionExtractor,
    NullVisionExtractor,
)
from app.module.knowledge.dependencies import (
    _vision_extractor_for_state,
    build_file_service,
    build_memory_service,
    build_summary_service,
)
from app.module.knowledge.exception.domain_error import AiNotConfiguredError
from app.module.knowledge.protocol.provider_config import ProviderConfig
from app.module.knowledge.protocol.text_generator_protocol import AiCompletion
from app.module.knowledge.service.file_service import FileService
from app.module.knowledge.service.memory_service import MemoryService
from app.module.knowledge.service.metered_text_generator import MeteredTextGenerator
from app.module.knowledge.service.summary_service import SummaryService
from tests.conftest import UserClient

# A 1x1 blue PNG; enough to exercise the image path without a real provider.
BLUE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _OkProbe:
    """Accept every candidate so the assignment API writes the row."""

    async def probe(
        self,
        config: ProviderConfig,
        *,
        model: str,
        reasoning_effort: str | None,
    ) -> ProbeOutcome:
        del config, reasoning_effort
        return ProbeOutcome(
            ok=True,
            latency_ms=1,
            resolved_model=model,
            usage={"input_tokens": 1, "output_tokens": 1},
            detail=None,
        )


class _RecordingGenerator:
    """A configured generator that records the config it was built from."""

    configured = True

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.model_name = config.model or "unconfigured"

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        del system_prompt, user_prompt
        return AiCompletion(
            text="auxiliary reply",
            model=self.model_name,
            usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        )

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        del system_prompt, user_prompt
        body = {
            "has_meaningful_text": True,
            "use_vision": False,
            "document_type": "note",
            "title": "Worker note",
            "summary": "A worker note.",
            "tags": [],
            "language": "English",
        }
        return AiCompletion(
            text=json.dumps(body),
            model=self.model_name,
            usage={"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        )


class _SentinelGenerator:
    """The runtime-global generator; touching it fails the test."""

    configured = False
    model_name = "runtime-global"

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        del system_prompt, user_prompt
        raise AssertionError("runtime.text_generator must not serve a knowledge path")

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        del system_prompt, user_prompt
        raise AssertionError("runtime.text_generator must not serve a knowledge path")


class _RecordingBuilder:
    """Record every config that ``build_user_text_generator`` resolves."""

    def __init__(self) -> None:
        self.configs: list[ProviderConfig] = []

    def build_text_generator(self, config: ProviderConfig) -> _RecordingGenerator:
        self.configs.append(config)
        return _RecordingGenerator(config)


@contextmanager
def _recording_runtime(client: TestClient) -> Iterator[_RecordingBuilder]:
    """Swap the runtime for a recording builder plus an untouched global generator."""
    real = client.app.state.ai_runtime
    builder = _RecordingBuilder()
    client.app.state.ai_runtime = SimpleNamespace(
        builder=builder,
        chat_chain=real.chat_chain,
        text_generator=_SentinelGenerator(),
        embedder=real.embedder,
    )
    try:
        yield builder
    finally:
        client.app.state.ai_runtime = real


def _call(
    client: TestClient,
    factory: Any,
    *,
    user_id: int,
    role: str = "root",
) -> Any:
    """Run one async builder on an owner-scoped session through the portal."""
    assert client.portal is not None

    async def run() -> Any:
        async with client.app.state.db.user_session(user_id, role) as session:
            return await factory(client.app.state, session, user_id=user_id)

    return client.portal.call(run)


def _build(
    client: TestClient,
    factory: Any,
    *,
    user_id: int,
    role: str = "root",
) -> tuple[Any, list[ProviderConfig]]:
    with _recording_runtime(client) as builder:
        service = _call(client, factory, user_id=user_id, role=role)
    return service, builder.configs


def _create_chat_row(
    client: TestClient,
    *,
    label: str,
    model: str = "deepseek-chat",
    api_key: str | None = "sk-aux-wiring-1234",
    provider: str = "deepseek",
    base_url: str = "https://api.deepseek.com",
    activate: bool = True,
) -> int:
    body: dict[str, Any] = {
        "provider": provider,
        "label": label,
        "model": model,
        "base_url": base_url,
        "activate": activate,
    }
    if api_key is not None:
        body["api_key"] = api_key
    response = client.post("/api/v1/settings/providers/chat", json=body)
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
    primary_id: int,
    auxiliary_id: int,
    *,
    chat_model: str = "primary-assigned",
    auxiliary_model: str = "aux-assigned",
    chat_effort: str = "high",
    auxiliary_effort: str = "low",
) -> None:
    client.app.state.provider_probe = _OkProbe()
    response = client.put(
        f"/api/v1/model-assignments/{user_id}",
        json={
            "chat_provider_config_id": primary_id,
            "chat_model": chat_model,
            "chat_reasoning_effort": chat_effort,
            "aux_provider_config_id": auxiliary_id,
            "aux_model": auxiliary_model,
            "aux_reasoning_effort": auxiliary_effort,
            "context_window_tokens": None,
            "compaction_threshold_tokens": None,
        },
    )
    assert response.status_code == 200, response.text


def _store_assignment(
    engine: Engine,
    user_id: int,
    *,
    primary_id: int | None,
    primary_model: str | None,
    primary_effort: str | None,
    auxiliary_id: int | None,
    auxiliary_model: str | None,
    auxiliary_effort: str = "low",
) -> None:
    """Write the raw columns so Q1 and broken-slot shapes are reproducible."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE app_user SET "
                "chat_provider_config_id = :primary_id, "
                "chat_model = :primary_model, "
                "chat_reasoning_effort = :primary_effort, "
                "aux_provider_config_id = :auxiliary_id, "
                "aux_model = :auxiliary_model, "
                "aux_reasoning_effort = :auxiliary_effort "
                "WHERE id = :user_id"
            ),
            {
                "primary_id": primary_id,
                "primary_model": primary_model,
                "primary_effort": primary_effort,
                "auxiliary_id": auxiliary_id,
                "auxiliary_model": auxiliary_model,
                "auxiliary_effort": auxiliary_effort,
                "user_id": user_id,
            },
        )


def _shapes(configs: list[ProviderConfig]) -> list[tuple[int | None, str | None, str | None]]:
    return [
        (config.row_id, config.model, config.reasoning_effort)
        for config in configs
    ]


def test_knowledge_builders_use_the_auxiliary_endpoint(
    client: TestClient,
    root_account: UserClient,
) -> None:
    """Summary, memory, and file services all resolve the auxiliary slot."""
    primary_id = _create_chat_row(client, label="primary", model="primary-row-model")
    auxiliary_id = _create_chat_row(client, label="auxiliary", model="aux-row-model")
    _assign(client, root_account.user_id, primary_id, auxiliary_id)

    expectations = (
        (build_summary_service, SummaryService),
        (build_memory_service, MemoryService),
        (build_file_service, FileService),
    )
    for factory, service_type in expectations:
        service, configs = _build(
            client,
            factory,
            user_id=root_account.user_id,
        )
        assert isinstance(service, service_type)
        assert configs
        assert _shapes(configs) == [(auxiliary_id, "aux-assigned", "low")] * len(configs)
        assert all(config.provider == "deepseek" for config in configs)
        assert all(config.api_key == "sk-aux-wiring-1234" for config in configs)
        # The runtime-global generator is never wrapped; the recorded one is.
        assert isinstance(service.text_generator, MeteredTextGenerator)
        assert service.text_generator.configured is True
        assert service.text_generator.model_name == "aux-assigned"


def test_changing_the_primary_assignment_does_not_change_auxiliary_paths(
    client: TestClient,
    root_account: UserClient,
) -> None:
    """The auxiliary slot is independent of the agent's primary selection."""
    primary_a = _create_chat_row(client, label="primary-a", model="primary-a-row")
    primary_b = _create_chat_row(client, label="primary-b", model="primary-b-row")
    auxiliary_id = _create_chat_row(client, label="auxiliary", model="aux-row-model")
    _assign(client, root_account.user_id, primary_a, auxiliary_id)

    _, before = _build(client, build_file_service, user_id=root_account.user_id)
    assert _shapes(before) == [(auxiliary_id, "aux-assigned", "low")]

    _assign(
        client,
        root_account.user_id,
        primary_b,
        auxiliary_id,
        chat_model="primary-b-assigned",
        chat_effort="max",
    )
    me = client.get("/api/v1/model-assignments/me")
    assert me.status_code == 200, me.text
    assert me.json()["chat_provider_config_id"] == primary_b
    assert me.json()["chat_model"] == "primary-b-assigned"

    _, after = _build(client, build_file_service, user_id=root_account.user_id)
    assert _shapes(after) == _shapes(before)
    assert {config.row_id for config in after} == {auxiliary_id}


def test_null_auxiliary_inherits_the_primary_with_low_effort(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    """The Q1 shape reuses the primary row and model but keeps auxiliary effort."""
    primary_id = _create_chat_row(client, label="primary", model="inherited-row-model")
    _store_assignment(
        owner_engine,
        root_account.user_id,
        primary_id=primary_id,
        primary_model="inherited-assigned",
        primary_effort="high",
        auxiliary_id=None,
        auxiliary_model=None,
        auxiliary_effort="low",
    )

    service, configs = _build(client, build_file_service, user_id=root_account.user_id)
    assert _shapes(configs) == [(primary_id, "inherited-assigned", "low")]
    assert isinstance(service.vision_extractor, DeepSeekVisionExtractor)
    assert service.vision_extractor.model_name == "inherited-assigned"
    assert service.vision_extractor._client.api_key == "sk-aux-wiring-1234"


def test_broken_auxiliary_rows_yield_null_generator_and_ai_not_configured(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    """A row that is not in the chain or has no key stays null; nothing rescues it."""
    primary_id = _create_chat_row(client, label="primary", model="primary-row-model")
    inactive_id = _create_chat_row(
        client,
        label="auxiliary-inactive",
        model="inactive-row-model",
        activate=False,
    )
    _store_assignment(
        owner_engine,
        root_account.user_id,
        primary_id=primary_id,
        primary_model="primary-assigned",
        primary_effort="high",
        auxiliary_id=inactive_id,
        auxiliary_model="stale-aux-model",
        auxiliary_effort="low",
    )

    service, configs = _build(client, build_file_service, user_id=root_account.user_id)
    assert configs == []
    assert isinstance(service.text_generator, MeteredTextGenerator)
    assert isinstance(service.text_generator._inner, NullTextGenerator)
    assert service.text_generator.configured is False
    assert isinstance(service.vision_extractor, NullVisionExtractor)

    assert client.portal is not None
    with pytest.raises(AiNotConfiguredError):
        client.portal.call(
            service.text_generator.complete_json,
            "system prompt",
            "user prompt",
        )

    uploaded = client.post(
        "/api/v1/files",
        data={"path": "/aux/inactive-scan.png"},
        files={"file": ("inactive-scan.png", BLUE_PNG, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["extraction_method"] == "filename"
    reingest = client.post(
        f"/api/v1/files/{uploaded.json()['id']}/reingest",
        json={"expected_version": 1},
    )
    assert reingest.status_code == 503, reingest.text
    assert reingest.json()["error"] == "ai_not_configured"

    # A keyless active row is in the chain but cannot serve a call.
    keyless_id = _create_chat_row(
        client,
        label="auxiliary-keyless",
        model="keyless-row-model",
        api_key=None,
    )
    _store_assignment(
        owner_engine,
        root_account.user_id,
        primary_id=primary_id,
        primary_model="primary-assigned",
        primary_effort="high",
        auxiliary_id=keyless_id,
        auxiliary_model="keyless-aux-model",
        auxiliary_effort="low",
    )
    keyless_service, keyless_configs = _build(
        client,
        build_file_service,
        user_id=root_account.user_id,
    )
    assert keyless_configs == []
    assert isinstance(keyless_service.text_generator._inner, NullTextGenerator)
    assert isinstance(keyless_service.vision_extractor, NullVisionExtractor)


def test_worker_resolves_the_auxiliary_assignment_for_the_job_owner(
    client: TestClient,
    user_client_factory: Any,
) -> None:
    """``build_ingest_worker`` reaches ``build_file_service`` in the job's session."""
    primary_id = _create_chat_row(client, label="primary", model="primary-row-model")
    auxiliary_id = _create_chat_row(client, label="auxiliary", model="aux-row-model")
    member: UserClient = user_client_factory()
    _assign(
        client,
        member.user_id,
        primary_id,
        auxiliary_id,
        auxiliary_model="worker-aux-model",
        chat_model="member-primary-model",
    )

    worker = client.app.state.ingest_worker
    with _recording_runtime(client) as builder:
        queued = member.client.post(
            "/api/v1/files/text/async",
            json={
                "path": "/aux/worker-note.md",
                "content": "Worker assignment notes for the auxiliary endpoint. " * 30,
            },
        )
        assert queued.status_code == 202, queued.text
        job_id = int(queued.json()["id"])

        assert client.portal is not None
        assert client.portal.call(worker.run_once) is True

    ready = member.client.get(f"/api/v1/files/ingest-jobs/{job_id}")
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "ready"
    assert builder.configs
    assert {config.row_id for config in builder.configs} == {auxiliary_id}
    assert {config.model for config in builder.configs} == {"worker-aux-model"}
    assert {config.reasoning_effort for config in builder.configs} == {"low"}


def _row_config(
    row_id: int,
    provider: str,
    *,
    model: str = "row-model",
    base_url: str | None = "https://provider.example/v1",
    api_key: str = "row-key",
) -> ProviderConfig:
    return ProviderConfig(
        capability="chat",
        provider=provider,
        label=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        dimension=None,
        enabled=True,
        source="database",
        row_id=row_id,
    )


def _auxiliary_assignment(
    row_id: int | None,
    model: str | None,
    *,
    effort: str = "low",
) -> ChatAssignment:
    return ChatAssignment(
        user_id=1,
        provider_config_id=None,
        model=None,
        reasoning_effort=None,
        aux_provider_config_id=row_id,
        aux_model=model,
        aux_reasoning_effort=effort,
        context_window_tokens=None,
        compaction_threshold_tokens=None,
    )


def test_vision_selection_uses_only_the_resolved_auxiliary_row() -> None:
    """Vision never scans the chain for "the first active provider"."""
    deepseek = _row_config(1, "deepseek", base_url="https://api.deepseek.com")
    anthropic = _row_config(2, "anthropic", base_url=None, api_key="anthropic-key")
    other = _row_config(3, "openai-compatible", base_url="https://gateway.example/v1")
    state = State()
    state.settings = SimpleNamespace(
        anthropic_base_url="https://api.anthropic.com",
        anthropic_timeout_seconds=120.0,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_timeout_seconds=60.0,
    )
    state.ai_runtime = SimpleNamespace(chat_chain=(deepseek, anthropic, other))

    anthropic_extractor = _vision_extractor_for_state(
        state,
        _auxiliary_assignment(2, "aux-anthropic", effort="high"),
    )
    assert isinstance(anthropic_extractor, AnthropicVisionExtractor)
    assert anthropic_extractor.model_name == "aux-anthropic"
    assert anthropic_extractor._image_client.api_key == "anthropic-key"
    assert anthropic_extractor._image_client.base_url == "https://api.anthropic.com"
    assert anthropic_extractor._image_client.reasoning_effort == "high"

    deepseek_extractor = _vision_extractor_for_state(
        state,
        _auxiliary_assignment(1, "aux-deepseek"),
    )
    assert isinstance(deepseek_extractor, DeepSeekVisionExtractor)
    assert deepseek_extractor.model_name == "aux-deepseek"
    assert deepseek_extractor._client.base_url == "https://api.deepseek.com"

    # An assigned OpenAI-compatible row stays null even with a DeepSeek row
    # active in the chain; the old code would have picked DeepSeek.
    assert isinstance(
        _vision_extractor_for_state(state, _auxiliary_assignment(3, "aux-gateway")),
        NullVisionExtractor,
    )
    # An unassigned auxiliary slot is not vision, even with active rows.
    assert isinstance(
        _vision_extractor_for_state(state, _auxiliary_assignment(None, None)),
        NullVisionExtractor,
    )
    # A deleted row id is absent from the chain and stays null.
    assert isinstance(
        _vision_extractor_for_state(state, _auxiliary_assignment(99, "gone")),
        NullVisionExtractor,
    )
