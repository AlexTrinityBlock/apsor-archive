"""Per-account usage allowances across chat, embedding, web search, and fetch.

All collaborators are deterministic fakes or the disposable PostgreSQL test
database. No live archive or provider is contacted.
"""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from starlette.datastructures import State

from app.infrastructure.ai import vision_client
from app.infrastructure.ai.vision_client import DeepSeekVisionClient
from app.infrastructure.database.session import Database
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
)
from app.module.auth.domain.quota_domain import (
    quota_allows,
    quota_base,
    quota_chat_allowed,
    quota_lifetime,
    quota_remaining,
    quota_used,
)
from app.module.auth.repository.auth_repository import SessionRepository, UserRepository
from app.module.auth.service.account_service import AccountService
from app.module.auth.service.quota_service import AccountQuotaService
from app.module.knowledge.dependencies import _build_indexer, build_ingest_worker
from app.module.knowledge.domain.chunking_domain import ChunkDraft
from app.module.knowledge.domain.vision_prompt_domain import (
    DEFAULT_VISION_DOCUMENT_PROMPT,
    DEFAULT_VISION_IMAGE_PROMPT,
)
from app.module.knowledge.exception.domain_error import (
    ChatUsageLimitExceededError,
    EmbeddingProviderError,
    EmbeddingUsageLimitExceededError,
)
from app.module.knowledge.protocol.text_generator_protocol import AiCompletion
from app.module.knowledge.protocol.vision_extractor_protocol import VisionDocument
from app.module.knowledge.repository.chunk_repository import ChunkRepository
from app.module.knowledge.repository.file_repository import FileRepository
from app.module.knowledge.repository.memory_repository import MemoryRepository
from app.module.knowledge.repository.summary_repository import SummaryRepository
from app.module.knowledge.service.file_service import FileService
from app.module.knowledge.service.indexer_service import (
    IndexerService,
    sum_embedding_characters,
)
from app.module.knowledge.service.ingest_job_service import ingest_error_code
from app.module.knowledge.service.memory_service import MemoryService
from app.module.knowledge.service.metered_text_generator import MeteredTextGenerator
from app.module.knowledge.service.search_service import SearchService
from app.module.knowledge.service.summary_service import SummaryService
from app.module.web_research.exception.domain_error import (
    WebProviderError,
    WebUsageLimitExceededError,
)
from app.module.web_research.schema.web_research_schema import (
    WebFetchResponse,
    WebSearchResponse,
)
from app.module.web_research.service.web_research_service import WebResearchService
from tests.conftest import TEST_DATABASE_URL, UserClient
from tests.helpers import create_memory

ACCOUNTS_URL = "/api/v1/accounts"
CATEGORY_ORDER = ["chat", "embedding", "web_search", "web_fetch"]
RETRIEVED_AT = datetime(2026, 11, 18, 0, 0, tzinfo=UTC)


@contextmanager
def _direct_engine() -> Iterator[Engine]:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        yield engine
    finally:
        engine.dispose()


def _set_user_columns(engine: Engine, user_id: int, **values: Any) -> None:
    """Update test-controlled ``app_user`` columns as the owning login."""
    assignments = ", ".join(f"{name} = :{name}" for name in values)
    with engine.begin() as connection:
        connection.execute(
            text(f"UPDATE app_user SET {assignments} WHERE id = :user_id"),
            {**values, "user_id": user_id},
        )


def _read_user_columns(engine: Engine, user_id: int, *names: str) -> tuple[Any, ...]:
    columns = ", ".join(names)
    with engine.begin() as connection:
        row = connection.execute(
            text(f"SELECT {columns} FROM app_user WHERE id = :user_id"),
            {"user_id": user_id},
        ).one()
    return tuple(row)


def _quota_by_category(account: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["category"]): item for item in account["quotas"]}


def _account_rows(client: TestClient) -> dict[int, dict[str, Any]]:
    response = client.get(ACCOUNTS_URL)
    assert response.status_code == 200, response.text
    return {int(item["user_id"]): item for item in response.json()["items"]}


def _all_quota_columns(**overrides: Any) -> SimpleNamespace:
    """Return a quota row with unlimited grants and no usage."""
    values: dict[str, Any] = {
        "chat_enabled": True,
        "chat_granted": None,
        "chat_used_before_reset": 0,
        "total_tokens": 0,
        "embedding_characters": 0,
        "embedding_enabled": True,
        "embedding_granted": None,
        "embedding_used_before_reset": 0,
        "web_search_calls": 0,
        "web_search_enabled": True,
        "web_search_granted": None,
        "web_search_used_before_reset": 0,
        "web_fetch_calls": 0,
        "web_fetch_enabled": True,
        "web_fetch_granted": None,
        "web_fetch_used_before_reset": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


def test_quota_domain_derives_used_and_remaining_from_the_reset_base() -> None:
    row = _all_quota_columns(
        total_tokens=100,
        chat_used_before_reset=25,
        chat_granted=100,
    )
    assert quota_lifetime(row, "chat") == 100
    assert quota_base(row, "chat") == 25
    assert quota_used(row, "chat") == 75
    assert quota_remaining(row, "chat") == 25
    assert quota_allows(row, "chat", 25) is True
    assert quota_allows(row, "chat", 26) is False

    # A reset base newer than the counter can happen only after a manual
    # correction; current usage clamps at zero instead of going negative.
    row = _all_quota_columns(
        embedding_characters=5,
        embedding_used_before_reset=10,
        embedding_granted=10,
    )
    assert quota_used(row, "embedding") == 0
    assert quota_remaining(row, "embedding") == 10


def test_quota_domain_unlimited_enabled_and_chat_boundaries() -> None:
    unlimited = _all_quota_columns()
    assert quota_remaining(unlimited, "web_search") is None
    assert quota_allows(unlimited, "web_search", 10**9) is True
    assert quota_chat_allowed(unlimited) is True

    disabled = _all_quota_columns(web_fetch_enabled=False)
    assert quota_remaining(disabled, "web_fetch") is None
    assert quota_allows(disabled, "web_fetch", 0) is False
    assert quota_allows(
        _all_quota_columns(chat_granted=0),
        "chat",
        0,
    ) is True  # embedding-style boundary; chat uses its own rule below

    assert quota_chat_allowed(_all_quota_columns(chat_granted=0)) is False
    exhausted = _all_quota_columns(chat_granted=10, total_tokens=10)
    assert quota_chat_allowed(exhausted) is False
    almost = _all_quota_columns(chat_granted=10, total_tokens=9)
    assert quota_chat_allowed(almost) is True


# ---------------------------------------------------------------------------
# Accounts API
# ---------------------------------------------------------------------------


def test_accounts_list_exposes_four_ordered_quotas_with_lifetime_math(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _set_user_columns(
        owner_engine,
        root_account.user_id,
        chat_enabled=False,
        chat_granted=100,
        chat_used_before_reset=10,
        total_tokens=40,
        embedding_characters=25,
        embedding_granted=100,
        embedding_used_before_reset=5,
        web_search_calls=3,
        web_search_granted=10,
        web_fetch_calls=2,
    )
    account = _account_rows(client)[root_account.user_id]
    quotas = _quota_by_category(account)
    assert [item["category"] for item in account["quotas"]] == CATEGORY_ORDER

    assert quotas["chat"]["enabled"] is False
    assert quotas["chat"]["granted"] == 100
    assert quotas["chat"]["lifetime"] == 40
    assert quotas["chat"]["used_before_reset"] == 10
    assert quotas["chat"]["used"] == 30
    assert quotas["chat"]["remaining"] == 70

    assert quotas["embedding"]["used"] == 20
    assert quotas["embedding"]["remaining"] == 80
    assert quotas["web_search"]["used"] == 3
    assert quotas["web_search"]["remaining"] == 7
    assert quotas["web_fetch"]["used"] == 2
    assert quotas["web_fetch"]["granted"] is None
    assert quotas["web_fetch"]["remaining"] is None


def test_new_account_defaults_to_enabled_unlimited_quotas(
    client: TestClient,
) -> None:
    created = client.post(
        ACCOUNTS_URL,
        json={"username": "quota.defaults", "display_name": "Quota Defaults"},
    )
    assert created.status_code == 201, created.text
    account = created.json()["user"]
    assert [item["category"] for item in account["quotas"]] == CATEGORY_ORDER
    for quota in account["quotas"]:
        assert quota["enabled"] is True
        assert quota["granted"] is None
        assert quota["used"] == 0
        assert quota["used_before_reset"] == 0
        assert quota["lifetime"] == 0
        assert quota["remaining"] is None


def test_root_can_update_top_up_and_reset_each_quota(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    updated = client.put(
        f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/embedding",
        json={"enabled": True, "granted": 100},
    )
    assert updated.status_code == 200, updated.text
    embedding = _quota_by_category(updated.json())["embedding"]
    assert embedding["enabled"] is True
    assert embedding["granted"] == 100
    assert embedding["remaining"] == 100

    topped = client.post(
        f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/embedding/top-up",
        json={"amount": 50},
    )
    assert topped.status_code == 200, topped.text
    embedding = _quota_by_category(topped.json())["embedding"]
    assert embedding["granted"] == 150

    second = client.post(
        f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/embedding/top-up",
        json={"amount": 25},
    )
    assert second.status_code == 200, second.text
    assert _quota_by_category(second.json())["embedding"]["granted"] == 175

    _set_user_columns(
        owner_engine,
        root_account.user_id,
        embedding_characters=80,
        embedding_used_before_reset=10,
    )
    reset = client.post(
        f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/embedding/reset",
        json={"granted": 200},
    )
    assert reset.status_code == 200, reset.text
    embedding = _quota_by_category(reset.json())["embedding"]
    assert embedding["lifetime"] == 80
    assert embedding["used_before_reset"] == 80
    assert embedding["used"] == 0
    assert embedding["granted"] == 200
    assert embedding["remaining"] == 200

    unlimited = client.post(
        f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/embedding/reset",
        json={"granted": None},
    )
    assert unlimited.status_code == 200, unlimited.text
    embedding = _quota_by_category(unlimited.json())["embedding"]
    assert embedding["granted"] is None
    assert embedding["remaining"] is None
    assert embedding["used_before_reset"] == 80


def test_quota_admin_rejects_invalid_values_and_non_root(
    client: TestClient,
    root_account: UserClient,
    user_client_factory,
) -> None:
    member = cast(UserClient, user_client_factory("quota.member"))
    forbidden = member.client.put(
        f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/chat",
        json={"enabled": True, "granted": 1},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"] == "forbidden"

    assert client.put(
        f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/unknown",
        json={"enabled": True, "granted": 1},
    ).status_code == 422

    negative_grant = client.put(
        f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/chat",
        json={"enabled": True, "granted": -1},
    )
    assert negative_grant.status_code == 422
    assert negative_grant.json()["error"] == "invalid_usage_quota"

    for amount in (0, -5, 10**13):
        topped = client.post(
            f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/chat/top-up",
            json={"amount": amount},
        )
        assert topped.status_code == 422, topped.text
        assert topped.json()["error"] == "invalid_usage_quota"

    unlimited = client.post(
        f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/web_fetch/top-up",
        json={"amount": 5},
    )
    assert unlimited.status_code == 422
    assert unlimited.json()["error"] == "invalid_usage_quota"

    negative_reset = client.post(
        f"{ACCOUNTS_URL}/{root_account.user_id}/quotas/chat/reset",
        json={"granted": -1},
    )
    assert negative_reset.status_code == 422
    assert negative_reset.json()["error"] == "invalid_usage_quota"

    missing = client.put(
        f"{ACCOUNTS_URL}/999999/quotas/chat",
        json={"enabled": True, "granted": 1},
    )
    assert missing.status_code == 404
    assert missing.json()["error"] == "account_not_found"


def test_quota_service_records_only_the_matching_lifetime_counter(
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _set_user_columns(
        owner_engine,
        root_account.user_id,
        total_tokens=11,
        embedding_characters=20,
        web_search_calls=2,
        web_fetch_calls=3,
    )

    async def run() -> None:
        database = Database(TEST_DATABASE_URL)
        try:
            service = AccountQuotaService(database, root_account.user_id)
            assert await service.chat_allowed() is True
            assert await service.embedding_allowed(10) is True
            await service.record_embedding(0)
            await service.record_embedding(-4)
            await service.record_embedding(7)
            await service.record_web_search()
            await service.record_web_fetch()
            await service.record_web_fetch()
        finally:
            await database.dispose()

    asyncio.run(run())
    counters = _read_user_columns(
        owner_engine,
        root_account.user_id,
        "total_tokens",
        "embedding_characters",
        "web_search_calls",
        "web_fetch_calls",
    )
    assert counters == (11, 27, 3, 5)


def test_concurrent_top_ups_do_not_lose_an_increment(
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _set_user_columns(owner_engine, root_account.user_id, chat_granted=100)

    async def top_up(database: Database, amount: int) -> None:
        async with database.system_session() as session:
            service = AccountService(
                user_repository=UserRepository(session),
                session_repository=SessionRepository(session),
                password_hasher=Argon2PasswordHasher(),
            )
            await service.top_up_quota(
                user_id=root_account.user_id,
                category="chat",
                amount=amount,
            )

    async def run() -> None:
        first = Database(TEST_DATABASE_URL)
        second = Database(TEST_DATABASE_URL)
        try:
            await asyncio.gather(
                top_up(first, 10),
                top_up(second, 20),
            )
        finally:
            await first.dispose()
            await second.dispose()

    asyncio.run(run())
    granted = _read_user_columns(owner_engine, root_account.user_id, "chat_granted")[0]
    assert granted == 130


# ---------------------------------------------------------------------------
# Chat enforcement
# ---------------------------------------------------------------------------


def _create_conversation(client: TestClient, title: str = "Quota chat") -> int:
    response = client.post("/api/v1/agent/conversations", json={"title": title})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _send_message(client: TestClient, conversation_id: int) -> Any:
    return client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Check the allowance."},
        headers={"Accept": "application/json"},
    )


def test_disabled_and_zero_grant_chat_never_create_a_run(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    conversation_id = _create_conversation(client)
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts("unused")

    _set_user_columns(owner_engine, root_account.user_id, chat_enabled=False)
    blocked = _send_message(client, conversation_id)
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "usage_limit_exceeded"

    _set_user_columns(
        owner_engine,
        root_account.user_id,
        chat_enabled=True,
        chat_granted=0,
    )
    zero = _send_message(client, conversation_id)
    assert zero.status_code == 429
    assert zero.json()["error"] == "usage_limit_exceeded"

    with _direct_engine() as engine:
        with engine.begin() as connection:
            runs = connection.execute(
                text("SELECT count(*) FROM agent_run WHERE user_id = :user_id"),
                {"user_id": root_account.user_id},
            ).scalar_one()
            entries = connection.execute(
                text(
                    "SELECT count(*) FROM agent_entry "
                    "WHERE user_id = :user_id AND kind = 'pi.user'"
                ),
                {"user_id": root_account.user_id},
            ).scalar_one()
    assert runs == 0
    assert entries == 0


def test_high_chat_grant_allows_a_turn_and_usage_comes_from_the_trigger(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _set_user_columns(
        owner_engine,
        root_account.user_id,
        chat_granted=1_000_000,
    )
    conversation_id = _create_conversation(client, "Allowed chat")
    client.app.state.agent_chat_generator = FakeChatGenerator.from_texts(
        "The allowance covers this answer.",
        usage={
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 12,
        },
    )

    turn = _send_message(client, conversation_id)
    assert turn.status_code == 200, turn.text
    body = turn.json()
    assert body["run"]["status"] == "completed"
    assert body["answer"] == "The allowance covers this answer."

    quota = _quota_by_category(_account_rows(client)[root_account.user_id])["chat"]
    assert quota["lifetime"] == 20
    assert quota["used"] == 20
    assert quota["granted"] == 1_000_000
    assert quota["remaining"] == 1_000_000 - 20


def test_mid_run_chat_guard_stops_before_the_second_provider_call(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _set_user_columns(owner_engine, root_account.user_id, chat_granted=15)
    conversation_id = _create_conversation(client, "Mid-run quota")
    fake = FakeChatGenerator(
        [
            tool_call_result(
                "search_knowledge",
                {"query": "anything", "result_number": 1},
                usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "prompt_cache_hit_tokens": 0,
                    "prompt_cache_miss_tokens": 10,
                },
            ),
            text_result("This second call must not run."),
        ]
    )
    client.app.state.agent_chat_generator = fake

    turn = _send_message(client, conversation_id)
    assert turn.status_code == 200, turn.text
    body = turn.json()
    assert body["run"]["status"] == "failed"
    assert body["run"]["error_code"] == "usage_limit_exceeded"
    assert body["error_code"] == "usage_limit_exceeded"
    assert fake.remaining == 1
    assert len(fake.requests) == 1

    assistant = [
        entry for entry in body["entries"] if entry["kind"] == "pi.assistant"
    ][-1]
    assert assistant["data"]["finish_reason"] == "error"
    assert assistant["data"]["error"]["code"] == "usage_limit_exceeded"
    assert "top it up or reset it" in assistant["data"]["error"]["detail"]


# ---------------------------------------------------------------------------
# Background chat usage
# ---------------------------------------------------------------------------


class _FakeChatQuota:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.recorded: list[dict[str, int]] = []

    async def chat_allowed(self) -> bool:
        return self.allowed

    async def record_chat_usage(self, usage: Any) -> None:
        self.recorded.append(dict(usage))


class _FakeInnerGenerator:
    configured = True
    model_name = "inner-text"

    def __init__(self, usage: dict[str, int] | None = None) -> None:
        self.usage = dict(usage or {})
        self.calls: list[tuple[str, str]] = []

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        self.calls.append((system_prompt, user_prompt))
        return AiCompletion(text="text result", model=self.model_name, usage=self.usage)

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        self.calls.append((system_prompt, user_prompt))
        return AiCompletion(text='{"ok": true}', model=self.model_name, usage=self.usage)


class _BlockedGenerator:
    configured = True
    model_name = "blocked"

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        del system_prompt, user_prompt
        raise ChatUsageLimitExceededError()

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        del system_prompt, user_prompt
        raise ChatUsageLimitExceededError()


def test_metered_generator_denies_before_calling_the_inner_generator() -> None:
    inner = _FakeInnerGenerator()
    quota = _FakeChatQuota(allowed=False)
    generator = MeteredTextGenerator(inner, quota)

    with pytest.raises(ChatUsageLimitExceededError):
        asyncio.run(generator.complete_text("system", "user"))
    with pytest.raises(ChatUsageLimitExceededError):
        asyncio.run(generator.complete_json("system", "user"))
    assert inner.calls == []
    assert quota.recorded == []


def test_metered_generator_records_exact_usage_once() -> None:
    usage = {
        "prompt_tokens": 11,
        "completion_tokens": 4,
        "total_tokens": 15,
        "prompt_cache_hit_tokens": 3,
    }
    inner = _FakeInnerGenerator(usage)
    quota = _FakeChatQuota()
    generator = MeteredTextGenerator(inner, quota)

    completion = asyncio.run(generator.complete_json("system", "user"))
    assert completion.text == '{"ok": true}'
    assert completion.usage == usage
    assert len(inner.calls) == 1
    assert quota.recorded == [usage]


def test_metered_generator_skips_an_empty_usage_object() -> None:
    inner = _FakeInnerGenerator({})
    quota = _FakeChatQuota()
    generator = MeteredTextGenerator(inner, quota)

    completion = asyncio.run(generator.complete_text("system", "user"))
    assert completion.text == "text result"
    assert len(inner.calls) == 1
    assert quota.recorded == []


def test_record_chat_usage_consumes_the_allowance_without_agent_metrics(
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    activity = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    _set_user_columns(
        owner_engine,
        root_account.user_id,
        chat_granted=70,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cached_tokens=0,
        api_calls=0,
        agent_turns=7,
        last_agent_activity_at=activity,
    )

    async def run() -> None:
        database = Database(TEST_DATABASE_URL)
        try:
            service = AccountQuotaService(database, root_account.user_id)
            await service.record_chat_usage(
                {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 20,
                    "prompt_cache_hit_tokens": 3,
                }
            )
            assert await service.chat_allowed() is True
            await service.record_chat_usage({})
            await service.record_chat_usage(
                {
                    "prompt_tokens": 20,
                    "completion_tokens": 30,
                    "cached_tokens": 4,
                }
            )
            assert await service.chat_allowed() is False
        finally:
            await database.dispose()

    asyncio.run(run())
    counters = _read_user_columns(
        owner_engine,
        root_account.user_id,
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cached_tokens",
        "api_calls",
        "agent_turns",
        "last_agent_activity_at",
    )
    assert counters[:6] == (30, 35, 70, 7, 2, 7)
    assert counters[6] == activity


def _file_service(
    *,
    text_generator: Any,
    vision_extractor: Any = None,
    chat_quota: Any = None,
) -> FileService:
    return FileService(
        user_id=1,
        file_repository=cast(Any, None),
        folder_repository=cast(Any, None),
        chunk_repository=cast(Any, None),
        indexer=cast(Any, None),
        storage=cast(Any, None),
        cache=cast(Any, None),
        text_generator=text_generator,
        vision_extractor=vision_extractor,
        vision_description_language="English",
        vision_image_prompt=DEFAULT_VISION_IMAGE_PROMPT,
        vision_document_prompt=DEFAULT_VISION_DOCUMENT_PROMPT,
        target_chars=1_000,
        overlap_chars=100,
        max_chunks=100,
        max_upload_bytes=1_000_000,
        max_text_bytes=1_000_000,
        vision_max_pages=4,
        pdf_text_threshold=100,
        chat_quota=chat_quota,
    )


def test_background_services_fall_back_when_chat_is_blocked() -> None:
    generator = _BlockedGenerator()
    summary = SummaryService(
        user_id=1,
        memory_repository=cast(Any, None),
        summary_repository=cast(Any, None),
        indexer=cast(Any, None),
        text_generator=generator,
        cache=cast(Any, None),
        ai_summary_enabled=True,
        auto_summary_threshold=10,
        min_memories=1,
    )
    memory = SimpleNamespace(
        id=1,
        memory_time=datetime(2026, 1, 1, tzinfo=UTC),
        content="A durable memory about a wrench.",
    )
    assert asyncio.run(summary._ai_draft([memory])) is None

    memory_service = MemoryService(
        user_id=1,
        memory_repository=cast(Any, None),
        chunk_repository=cast(Any, None),
        indexer=cast(Any, None),
        cache=cast(Any, None),
        summary_service=cast(Any, None),
        text_generator=generator,
    )
    assert asyncio.run(memory_service._generate_title("A durable memory")) == (
        "A durable memory"
    )

    service = _file_service(text_generator=generator)
    analysis = asyncio.run(
        service._analyze_text(
            "x" * 60,
            file_name_value="sample.txt",
            document_type="text",
        )
    )
    assert analysis.has_meaningful_text is True
    assert analysis.use_vision is False
    assert analysis.title == "sample.txt"


# ---------------------------------------------------------------------------
# Vision usage
# ---------------------------------------------------------------------------


class _UsageVisionExtractor:
    configured = True
    model_name = "fake-vision"

    def __init__(self, usage: dict[str, int] | None = None) -> None:
        self.usage = dict(
            usage
            or {
                "prompt_tokens": 12,
                "completion_tokens": 6,
                "total_tokens": 18,
            }
        )
        self.calls: list[bytes] = []

    async def extract(
        self,
        data: bytes,
        mime_type: str,
        *,
        system_prompt: str,
        mode: str = "image",
    ) -> VisionDocument:
        del mime_type, system_prompt, mode
        self.calls.append(data)
        return VisionDocument(
            text="page text",
            caption="",
            ocr_text="page text",
            title="Page",
            summary="",
            document_type="other",
            tags=[],
            language="en",
            usage=dict(self.usage),
        )


class _VisionChatQuota:
    def __init__(self, *, allowed: bool, stop_after_first: bool = False) -> None:
        self.allowed = allowed
        self.stop_after_first = stop_after_first
        self.recorded: list[dict[str, int]] = []

    async def chat_allowed(self) -> bool:
        return self.allowed

    async def record_chat_usage(self, usage: Any) -> None:
        self.recorded.append(dict(usage))
        if self.stop_after_first:
            self.allowed = False


def test_file_service_stops_vision_when_chat_is_denied() -> None:
    extractor = _UsageVisionExtractor()
    quota = _VisionChatQuota(allowed=False)
    service = _file_service(
        text_generator=_BlockedGenerator(),
        vision_extractor=extractor,
        chat_quota=quota,
    )

    asyncio.run(service._vision_images([(b"first", "image/png")]))
    assert extractor.calls == []
    assert quota.recorded == []


def test_file_service_records_vision_usage_and_stops_between_calls() -> None:
    extractor = _UsageVisionExtractor()
    quota = _VisionChatQuota(allowed=True, stop_after_first=True)
    service = _file_service(
        text_generator=_BlockedGenerator(),
        vision_extractor=extractor,
        chat_quota=quota,
    )

    asyncio.run(
        service._vision_images(
            [(b"first", "image/png"), (b"second", "image/png")]
        )
    )
    assert extractor.calls == [b"first"]
    assert quota.recorded == [extractor.usage]


def test_vision_document_usage_round_trips() -> None:
    document = VisionDocument(
        text="page",
        caption="",
        ocr_text="page",
        title="Page",
        summary="",
        document_type="other",
        tags=[],
        language="en",
        usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    )
    payload = document.model_dump()
    assert payload["usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    assert VisionDocument.model_validate(payload).usage == document.usage


def test_vision_client_captures_provider_usage(monkeypatch: Any) -> None:
    body = {
        "choices": [{"message": {"content": '{"text": "vision text"}'}}],
        "usage": {
            "prompt_tokens": 21,
            "completion_tokens": 7,
            "total_tokens": 28,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=body)

    real_client = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(vision_client.httpx, "AsyncClient", factory)
    client = DeepSeekVisionClient(
        api_key="test-key",
        base_url="https://vision.example",
        model="vision-test",
        timeout_seconds=1,
    )
    analysis = asyncio.run(
        client.analyze(
            b"image",
            "image/png",
            system_prompt="system",
            user_prompt="user",
        )
    )
    assert analysis.parsed["text"] == "vision text"
    assert analysis.usage == {
        "prompt_tokens": 21,
        "completion_tokens": 7,
        "total_tokens": 28,
    }


# ---------------------------------------------------------------------------
# Embedding enforcement
# ---------------------------------------------------------------------------


class _FakeChunkRepository:
    def __init__(self) -> None:
        self.chunks: list[Any] = []
        self.next_id = 1

    async def add(self, chunk: Any) -> Any:
        chunk.id = self.next_id
        self.next_id += 1
        self.chunks.append(chunk)
        return chunk

    async def add_ngrams(self, chunk_id: int, frequencies: dict[str, int]) -> None:
        del chunk_id, frequencies


class _FakeEmbedder:
    model_name = "fake-embedding"
    dimension = 3

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.1, 0.2, 0.3] for _text in texts]


class _FakeQuota:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed = allowed
        self.recorded: list[int] = []

    async def embedding_allowed(self, units: int) -> bool:
        del units
        return self.allowed

    async def record_embedding(self, units: int) -> None:
        self.recorded.append(units)


def _drafts() -> list[ChunkDraft]:
    return [
        ChunkDraft(index=1, content="abcdefgh", char_count=8, token_count=2),
        ChunkDraft(index=2, content="ijklmnop", char_count=8, token_count=1),
    ]


def test_indexer_strict_denial_keeps_text_and_leaves_vectors_pending() -> None:
    """A spent allowance never fails durable ingestion; vectors stay pending."""
    repository = _FakeChunkRepository()
    embedder = _FakeEmbedder()
    quota = _FakeQuota(allowed=False)
    indexer = IndexerService(
        cast(Any, repository),
        cast(Any, embedder),
        user_id=1,
        fail_on_embedding_error=True,
        quota=cast(Any, quota),
    )

    count = asyncio.run(
        indexer.index_chunks(
            source_kind="file",
            source_id=1,
            drafts=_drafts(),
        )
    )
    assert count == 2
    assert len(repository.chunks) == 2
    assert all(chunk.embedding is None for chunk in repository.chunks)
    assert embedder.calls == []
    assert quota.recorded == []


def test_indexer_lenient_denial_persists_text_only_chunks() -> None:
    repository = _FakeChunkRepository()
    embedder = _FakeEmbedder()
    quota = _FakeQuota(allowed=False)
    indexer = IndexerService(
        cast(Any, repository),
        cast(Any, embedder),
        user_id=1,
        fail_on_embedding_error=False,
        quota=cast(Any, quota),
    )

    count = asyncio.run(
        indexer.index_chunks(
            source_kind="file",
            source_id=1,
            drafts=_drafts(),
        )
    )
    assert count == 2
    assert len(repository.chunks) == 2
    assert all(chunk.embedding is None for chunk in repository.chunks)
    assert all(chunk.embedding_model is None for chunk in repository.chunks)
    assert embedder.calls == []
    assert quota.recorded == []


def test_indexer_records_characters_once_per_successful_batch() -> None:
    repository = _FakeChunkRepository()
    embedder = _FakeEmbedder()
    quota = _FakeQuota(allowed=True)
    drafts = _drafts()
    expected = sum(draft.char_count for draft in drafts)
    assert expected == sum_embedding_characters(drafts)
    indexer = IndexerService(
        cast(Any, repository),
        cast(Any, embedder),
        user_id=1,
        embedding_batch_size=1,
        quota=cast(Any, quota),
    )

    count = asyncio.run(
        indexer.index_chunks(
            source_kind="file",
            source_id=1,
            drafts=drafts,
        )
    )
    assert count == 2
    assert embedder.calls == [["abcdefgh"], ["ijklmnop"]]
    assert quota.recorded == [
        sum_embedding_characters([drafts[0]]),
        sum_embedding_characters([drafts[1]]),
    ]
    assert all(chunk.embedding is not None for chunk in repository.chunks)


def test_indexer_zero_character_batch_records_nothing() -> None:
    repository = _FakeChunkRepository()
    embedder = _FakeEmbedder()
    quota = _FakeQuota(allowed=True)
    indexer = IndexerService(
        cast(Any, repository),
        cast(Any, embedder),
        user_id=1,
        quota=cast(Any, quota),
    )

    count = asyncio.run(
        indexer.index_chunks(
            source_kind="file",
            source_id=1,
            drafts=[ChunkDraft(index=1, content="", char_count=0, token_count=5)],
        )
    )
    assert count == 1
    assert quota.recorded == []


def test_shared_indexer_composition_enforces_and_records_embedding_quota(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    """Memory, summary, and history share ``_build_indexer``; it must enforce."""
    state = State()
    state.db = client.app.state.db
    state.settings = client.app.state.settings
    state.ai_runtime = client.app.state.ai_runtime
    drafts = [
        ChunkDraft(
            index=1,
            content="A durable memory about a wrench.",
            char_count=32,
            token_count=6,
        )
    ]
    expected = sum_embedding_characters(drafts)

    async def index(source_id: int) -> None:
        async with client.app.state.db.user_session(
            root_account.user_id,
            "root",
        ) as session:
            _chunk_repository, indexer = _build_indexer(
                state,
                session,
                user_id=root_account.user_id,
            )
            assert indexer.quota is not None
            await indexer.index_chunks(
                source_kind="memory",
                source_id=source_id,
                drafts=drafts,
            )

    _set_user_columns(
        owner_engine,
        root_account.user_id,
        embedding_granted=0,
        embedding_characters=0,
        embedding_used_before_reset=0,
    )
    client.portal.call(index, 9001)
    denied_chunks = _read_chunks(owner_engine, root_account.user_id, 9001)
    assert len(denied_chunks) == 1
    assert denied_chunks[0][0] is True
    assert denied_chunks[0][1] is None
    assert _read_user_columns(
        owner_engine, root_account.user_id, "embedding_characters"
    )[0] == 0

    _set_user_columns(
        owner_engine,
        root_account.user_id,
        embedding_granted=1_000_000,
        embedding_characters=0,
        embedding_used_before_reset=0,
    )
    client.portal.call(index, 9002)
    allowed_chunks = _read_chunks(owner_engine, root_account.user_id, 9002)
    assert len(allowed_chunks) == 1
    assert allowed_chunks[0][0] is False
    assert allowed_chunks[0][1] == "apsor-hash-384"
    assert _read_user_columns(
        owner_engine, root_account.user_id, "embedding_characters"
    )[0] == expected


def _read_chunks(
    engine: Engine,
    user_id: int,
    source_id: int,
) -> list[tuple[bool, str | None]]:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                "SELECT (embedding IS NULL OR embedding = 'null'::jsonb), "
                "embedding_model FROM chunk "
                "WHERE user_id = :user_id AND source_kind = 'memory' "
                "AND source_id = :source_id"
            ),
            {"user_id": user_id, "source_id": source_id},
        ).all()
    return [(bool(row[0]), row[1]) for row in rows]


class _CountingQueryEmbedder:
    model_name = "fake-query-embedding"
    dimension = 3

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[0.2, 0.3, 0.4] for _text in texts]


class _SearchQuota:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed = allowed
        self.recorded: list[int] = []

    async def embedding_allowed(self, units: int) -> bool:
        del units
        return self.allowed

    async def record_embedding(self, units: int) -> None:
        self.recorded.append(units)


class _FailingQueryEmbedder:
    dimension = 3

    async def embed(self, texts: list[str]) -> list[list[float]]:
        del texts
        raise EmbeddingProviderError("temporary failure", status_code=503)


def test_search_query_embedding_provider_failure_does_not_record() -> None:
    quota = _SearchQuota(allowed=True)
    service = SearchService(
        user_id=1,
        chunk_repository=cast(Any, None),
        file_repository=cast(Any, None),
        memory_repository=cast(Any, None),
        summary_repository=cast(Any, None),
        embedder=cast(Any, _FailingQueryEmbedder()),
        cache=cast(Any, None),
        cache_ttl_seconds=5,
        candidate_limit=10,
        vector_scan_limit=10,
        quota=quota,
    )

    assert asyncio.run(service._query_embedding("wrench query")) is None
    assert quota.recorded == []


def test_search_query_embedding_obeys_the_allowance(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    """Denied queries stay keyword-only; an allowed query records once."""
    create_memory(
        client,
        "The wrench is a hand tool used for chassis repair.",
        "2026-09-05T09:00:00Z",
    )
    _set_user_columns(
        owner_engine,
        root_account.user_id,
        embedding_granted=0,
        embedding_characters=0,
        embedding_used_before_reset=0,
    )

    def run_search(query: str, embedder: _CountingQueryEmbedder, quota: Any):
        async def scenario() -> tuple[bool, int, list[int]]:
            async with client.app.state.db.user_session(
                root_account.user_id,
                "root",
            ) as session:
                service = SearchService(
                    user_id=root_account.user_id,
                    chunk_repository=ChunkRepository(session, root_account.user_id),
                    file_repository=FileRepository(session, root_account.user_id),
                    memory_repository=MemoryRepository(session, root_account.user_id),
                    summary_repository=SummaryRepository(
                        session,
                        root_account.user_id,
                    ),
                    embedder=embedder,
                    cache=client.app.state.cache,
                    cache_ttl_seconds=5,
                    candidate_limit=50,
                    vector_scan_limit=200,
                    quota=quota,
                )
                response = await service.search(
                    query,
                    result_number=5,
                    include_history=False,
                )
                recorded = list(getattr(quota, "recorded", []))
                return (
                    len(response.memory_results) > 0,
                    embedder.calls,
                    recorded,
                )

        return client.portal.call(scenario)

    denied_embedder = _CountingQueryEmbedder()
    denied_quota = _SearchQuota(allowed=False)
    has_results, calls, recorded = run_search(
        "wrench denied search",
        denied_embedder,
        denied_quota,
    )
    assert has_results is True
    assert calls == 0
    assert recorded == []

    _set_user_columns(
        owner_engine,
        root_account.user_id,
        embedding_granted=1_000_000,
        embedding_characters=0,
        embedding_used_before_reset=0,
    )
    allowed_query = "wrench allowed search"
    allowed_embedder = _CountingQueryEmbedder()
    allowed_quota = AccountQuotaService(
        client.app.state.db,
        root_account.user_id,
    )
    has_results, calls, _recorded = run_search(
        allowed_query,
        allowed_embedder,
        allowed_quota,
    )
    assert has_results is True
    assert calls == 1
    assert _read_user_columns(
        owner_engine, root_account.user_id, "embedding_characters"
    )[0] == len(allowed_query)


def test_durable_ingest_job_error_code_for_denied_embedding() -> None:
    assert (
        ingest_error_code(EmbeddingUsageLimitExceededError())
        == "embedding_usage_limit_exceeded"
    )


def test_durable_ingest_job_succeeds_with_pending_vectors_when_embedding_is_denied(
    client: TestClient,
    root_account: UserClient,
    owner_engine: Engine,
) -> None:
    _set_user_columns(owner_engine, root_account.user_id, embedding_granted=0)
    queued = client.post(
        "/api/v1/files/text/async",
        json={
            "path": "/quota/denied.md",
            "content": "Embedding quota denial keeps the text searchable.",
        },
    )
    assert queued.status_code == 202, queued.text
    job_id = int(queued.json()["id"])

    state = State()
    state.db = client.app.state.db
    state.settings = client.app.state.settings
    state.cache = client.app.state.cache
    state.storage = client.app.state.storage
    state.secret_cipher = client.app.state.secret_cipher
    state.ai_runtime = client.app.state.ai_runtime
    worker = build_ingest_worker(
        state,
        client.app.state.db.session_factory,
        client.app.state.settings,
    )
    try:
        assert client.portal.call(worker.run_once) is True
    finally:
        worker.close()

    job = client.get(f"/api/v1/files/ingest-jobs/{job_id}")
    assert job.status_code == 200, job.text
    body = job.json()
    assert body["status"] == "ready", body
    assert body["error_code"] is None
    # The text is indexed for keyword search; vectors wait for the backfill.
    with owner_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT embedding IS NULL AS pending FROM chunk "
                "WHERE user_id = :user_id AND source_kind = 'file'"
            ),
            {"user_id": root_account.user_id},
        ).all()
    assert rows
    assert all(row.pending for row in rows)


# ---------------------------------------------------------------------------
# Web enforcement
# ---------------------------------------------------------------------------


class _FakeWebConfig:
    capability = "web"
    provider = "tavily"
    base_url = None
    api_key = "test"
    enabled = True
    source = "test"


class _FakeWebCache:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    async def get_json(self, key: str) -> Any:
        return self.values.get(key)

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        del ttl_seconds
        self.values[key] = value

    async def get_version(self, scope: str = "index") -> int:
        del scope
        return 1


class _FakeWebQuota:
    def __init__(self, *, search: bool = True, fetch: bool = True) -> None:
        self.search_allowed = search
        self.fetch_allowed = fetch
        self.searches = 0
        self.fetches = 0

    async def web_search_allowed(self) -> bool:
        return self.search_allowed

    async def record_web_search(self) -> None:
        self.searches += 1

    async def web_fetch_allowed(self) -> bool:
        return self.fetch_allowed

    async def record_web_fetch(self) -> None:
        self.fetches += 1


class _FakeWebSearchClient:
    provider = "tavily"
    configured = True

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query: str, **kwargs: Any) -> WebSearchResponse:
        del kwargs
        self.calls += 1
        return WebSearchResponse(
            provider="tavily",
            query=query,
            results=[],
            elapsed_ms=1,
            truncated=False,
            cached=False,
            retrieved_at=RETRIEVED_AT,
        )


class _FakeWebFetchClient:
    provider = "tavily"
    configured = True

    def __init__(self, content: str = "A fetched page.") -> None:
        self.content = content
        self.calls = 0

    async def fetch(self, url: str, *, max_chars: int) -> WebFetchResponse:
        del max_chars
        self.calls += 1
        return WebFetchResponse(
            provider="tavily",
            url=url,
            content=self.content,
            elapsed_ms=1,
            truncated=False,
            cached=False,
            retrieved_at=RETRIEVED_AT,
        )


def _web_service(
    *,
    quota: _FakeWebQuota,
    search_client: _FakeWebSearchClient | None = None,
    fetch_client: _FakeWebFetchClient | None = None,
) -> tuple[WebResearchService, _FakeWebCache, _FakeWebSearchClient, _FakeWebFetchClient]:
    cache = _FakeWebCache()
    search = search_client or _FakeWebSearchClient()
    fetch = fetch_client or _FakeWebFetchClient()
    service = WebResearchService(
        search_config=cast(Any, _FakeWebConfig()),
        fetch_config=cast(Any, _FakeWebConfig()),
        search_client=cast(Any, search),
        fetch_client=cast(Any, fetch),
        cache=cast(Any, cache),
        quota=cast(Any, quota),
    )
    return service, cache, search, fetch


def test_web_quota_denial_never_calls_the_provider() -> None:
    quota = _FakeWebQuota(search=False, fetch=False)
    service, _cache, search, fetch = _web_service(quota=quota)

    with pytest.raises(WebUsageLimitExceededError):
        asyncio.run(
            service.search(
                "quota",
                max_results=5,
                search_depth="basic",
                include_domains=[],
                exclude_domains=[],
            )
        )
    with pytest.raises(WebUsageLimitExceededError):
        asyncio.run(service.fetch("https://example.com/quota"))
    assert search.calls == 0
    assert fetch.calls == 0
    assert quota.searches == 0
    assert quota.fetches == 0


def test_web_quota_records_a_successful_provider_call_exactly_once() -> None:
    quota = _FakeWebQuota()
    service, _cache, search, fetch = _web_service(quota=quota)

    async def run() -> None:
        await service.search(
            "quota",
            max_results=5,
            search_depth="basic",
            include_domains=[],
            exclude_domains=[],
        )
        await service.fetch("https://example.com/quota-page")
        await service.fetch("https://example.com/quota-page")

    asyncio.run(run())
    assert search.calls == 1
    assert fetch.calls == 1
    assert quota.searches == 1
    assert quota.fetches == 1


def test_web_quota_cache_hits_are_free() -> None:
    quota = _FakeWebQuota()
    service, _cache, _search, fetch = _web_service(quota=quota)

    async def run() -> None:
        first = await service.fetch("https://example.com/cached")
        second = await service.fetch("https://example.com/cached")
        assert first.cached is False
        assert second.cached is True

    asyncio.run(run())
    assert fetch.calls == 1
    assert quota.fetches == 1
    assert quota.searches == 0


def test_web_quota_empty_fetch_records_nothing() -> None:
    quota = _FakeWebQuota()
    empty_fetch = _FakeWebFetchClient(content="   ")
    service, _cache, _search, fetch = _web_service(
        quota=quota,
        fetch_client=empty_fetch,
    )

    with pytest.raises(WebProviderError):
        asyncio.run(service.fetch("https://example.com/empty"))
    assert fetch.calls == 1
    assert quota.fetches == 0


def test_agent_web_tool_returns_the_usage_limit_code(
    client: TestClient,
    root_account: UserClient,
) -> None:
    class _DeniedWebService:
        async def search(self, *args: Any, **kwargs: Any) -> WebSearchResponse:
            del args, kwargs
            raise WebUsageLimitExceededError("web search")

        async def fetch(self, *args: Any, **kwargs: Any) -> WebFetchResponse:
            del args, kwargs
            raise AssertionError("fetch must not run")

    client.app.state.web_research_service = _DeniedWebService()
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [
            tool_call_result(
                "web_search",
                {"query": "quota", "max_results": 3},
            ),
            text_result("The web allowance is spent."),
        ]
    )
    conversation = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Web quota"},
    )
    assert conversation.status_code == 201, conversation.text
    turn = client.post(
        f"/api/v1/agent/conversations/{conversation.json()['id']}/messages",
        json={"content": "Search the web for the quota behavior."},
        headers={"Accept": "application/json"},
    )
    assert turn.status_code == 200, turn.text
    tool_result = next(
        entry for entry in turn.json()["tool_results"] if entry["data"]["tool"] == "web_search"
    )
    assert tool_result["data"]["error_code"] == "web_usage_limit_exceeded"
