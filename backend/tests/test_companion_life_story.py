"""Generated life stories: scheduling, the worker job, judging, and isolation."""

import asyncio
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database
from app.module.agent.test.fake_chat_generator import FakeChatGenerator, text_result
from app.module.companion.dependencies import (
    _LifeStoryGenerator,
    build_companion_story_service,
    build_life_story_worker,
)
from app.module.companion.domain.life_story_domain import (
    REJECT_BANNED_ADDRESS,
    REJECT_TOO_SHORT,
    LifeStoryGenerationError,
    LifeStoryRejectedError,
    LifeStoryTemplateError,
    cadence_trigger_key,
    find_banned_term,
    life_story_due,
    parse_story,
    render_prompt,
    strip_citations,
)
from app.module.companion.domain.story_domain import (
    DEFAULT_RUNTIME_CONFIG,
    LifeStoryConfig,
)
from app.module.companion.protocol.life_story_protocol import (
    LifeStoryGeneration,
    LifeStoryMaterial,
    LifeStoryMaterialRequest,
)
from app.module.companion.repository.companion_life_story_repository import (
    LifeStoryJobQueue,
    LifeStoryRepository,
)
from app.module.companion.service.life_story_templates import seed_template
from app.module.companion.service.life_story_worker import LifeStoryWorker
from app.module.companion.service.story_config import (
    StaticCompanionContentProvider,
    StaticStoryConfigProvider,
)
from app.module.knowledge.exception.domain_error import (
    AiNotConfiguredError,
    AiProviderError,
    ChatUsageLimitExceededError,
)
from app.module.knowledge.protocol.text_generator_protocol import AiCompletion
from app.module.knowledge.service.metered_text_generator import MeteredTextGenerator
from app.shared.time import utcnow
from tests.conftest import UserClient, rls_connection
from tests.helpers import create_memory

VELLUM = "preset:vellum"
CONVERSATIONS = "/api/v1/agent/conversations"
STORY_BODY = (
    "The door between the map cabinets was open again tonight, and through it I saw a "
    "kitchen with one chair pulled close to the window. You were writing a list for the "
    "market in pencil, and you crossed out eggs twice. I did not step through. I only "
    "watched the steam lift from the cup beside your hand until the shelves closed."
)
STORY_OUTPUT = f"The Kitchen Door\n\n{STORY_BODY}"


def _config(**life: Any) -> StaticStoryConfigProvider:
    return StaticStoryConfigProvider(
        replace(DEFAULT_RUNTIME_CONFIG, life_story=LifeStoryConfig(**life))
    )


def _install_config(client: TestClient, **life: Any) -> StaticStoryConfigProvider:
    provider = _config(**life)
    client.app.state.companion_story_config = provider
    return provider


def _conversations(client: TestClient, count: int) -> None:
    """Finish one run in each of ``count`` new conversations."""
    client.app.state.agent_chat_generator = FakeChatGenerator(
        [text_result("ok.") for _ in range(count)]
    )
    for index in range(count):
        response = client.post(CONVERSATIONS, json={"title": f"Day {index}"})
        assert response.status_code == 201, response.text
        conversation_id = response.json()["id"]
        turn = client.post(
            f"{CONVERSATIONS}/{conversation_id}/messages",
            json={"content": f"hello {index}"},
            headers={"Accept": "application/json"},
        )
        assert turn.status_code == 200, turn.text


def _jobs(owner_engine: Engine) -> list[dict[str, Any]]:
    with owner_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, user_id, companion_ref, locale, trigger, trigger_key, status, "
                "skip_reason, error_code, attempts FROM companion_story_job ORDER BY id"
            )
        ).mappings()
        return [dict(row) for row in rows]


def _stories(owner_engine: Engine) -> list[dict[str, Any]]:
    with owner_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, user_id, companion_ref, locale, fragment_key, title, text, tier, "
                "status, source_refs, job_id, model, prompt_tokens, completion_tokens "
                "FROM companion_generated_story ORDER BY id"
            )
        ).mappings()
        return [dict(row) for row in rows]


def _queue_job(owner_engine: Engine, user_id: int, *, status: str = "queued") -> int:
    with owner_engine.begin() as connection:
        return int(
            connection.execute(
                text(
                    "INSERT INTO companion_story_job "
                    "(user_id, companion_ref, locale, trigger, trigger_key, status) "
                    "VALUES (:user_id, :ref, 'en', 'admin', :key, :status) RETURNING id"
                ),
                {
                    "user_id": user_id,
                    "ref": VELLUM,
                    "key": f"admin:test:{status}",
                    "status": status,
                },
            ).scalar_one()
        )


@dataclass
class _FakeGenerator:
    """A life-story generator that returns canned output or raises."""

    output: str = STORY_OUTPUT
    error: LifeStoryGenerationError | None = None
    on_generate: Callable[[], None] | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def generate(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, str]],
        max_output_tokens: int,
    ) -> LifeStoryGeneration:
        self.calls.append(
            {"system": system, "messages": list(messages), "max_output_tokens": max_output_tokens}
        )
        if self.on_generate is not None:
            self.on_generate()
        if self.error is not None:
            raise self.error
        return LifeStoryGeneration(
            text=self.output,
            model="fake-aux",
            provider_config_id=7,
            prompt_tokens=321,
            completion_tokens=123,
        )


@dataclass
class _FakeSelector:
    """Return fixed materials, honoring exclusions."""

    materials: list[LifeStoryMaterial]
    requests: list[LifeStoryMaterialRequest] = field(default_factory=list)

    async def select(self, request: LifeStoryMaterialRequest) -> list[LifeStoryMaterial]:
        self.requests.append(request)
        return [
            item for item in self.materials if item.source_id not in request.exclude_memory_ids
        ][: request.limit]


MATERIALS = [
    LifeStoryMaterial(kind="memory", source_id=11, title="Market list", excerpt="SECRET-EGGS"),
    LifeStoryMaterial(kind="memory", source_id=12, title="Window", excerpt="SECRET-WINDOW"),
]


def _worker(
    client: TestClient,
    *,
    generator: _FakeGenerator | None,
    selector: _FakeSelector | None = None,
    allowed: bool = True,
    config: StaticStoryConfigProvider | None = None,
    lease: timedelta = timedelta(minutes=10),
) -> LifeStoryWorker:
    state = client.app.state

    async def build_generator(
        session: AsyncSession,
        user_id: int,
        max_output_tokens: int,
    ) -> _FakeGenerator | None:
        del session, user_id, max_output_tokens
        return generator

    async def chat_allowed(user_id: int) -> bool:
        del user_id
        return allowed

    chosen = selector or _FakeSelector(list(MATERIALS))
    return LifeStoryWorker(
        database=state.db,
        config=config or _config(),
        content=StaticCompanionContentProvider(),
        story_service=lambda session, user_id: build_companion_story_service(
            session,
            user_id=user_id,
        ),
        materials=lambda session, user_id: chosen,
        generator=build_generator,
        chat_allowed=chat_allowed,
        repository=LifeStoryRepository,
        queue=LifeStoryJobQueue,
        lease=lease,
    )


# --- pure rules -----------------------------------------------------------------


def test_prompt_rendering_requires_placeholders_and_never_reinterprets_values() -> None:
    with pytest.raises(LifeStoryTemplateError) as missing:
        render_prompt("Hello {persona}", {"persona": "p"}, ("persona", "language"))
    assert missing.value.missing == ("language",)
    rendered = render_prompt(
        "{memories} / {language}",
        {"memories": "a {persona} b {not_a_field}", "language": "English", "persona": "X"},
        ("memories", "language"),
    )
    assert rendered == "a {persona} b {not_a_field} / English"
    for key in ("life_story_system", "life_story_user"):
        assert seed_template(key), key
    assert "{memories}" in seed_template("life_story_user")
    assert "Keeper" in seed_template("life_story_system")  # the rule names what not to say


def test_parse_story_splits_cleans_clips_and_judges() -> None:
    story = parse_story(
        "```\n# Title: 「The Door」\n\nA line [memory:12] that cites. " + STORY_BODY + "\n```",
        max_chars=2400,
        banned_terms=("keeper", "館主"),
    )
    assert story.title == "The Door"
    assert "[memory:12]" not in story.text
    assert story.text.startswith("A line that cites.")

    long = parse_story(
        "T\n\n" + ("A sentence that ends. " * 200),
        max_chars=300,
        banned_terms=(),
    )
    assert len(long.text) <= 300 and long.text.endswith(".")

    with pytest.raises(LifeStoryRejectedError) as short:
        parse_story("Title\n\ntoo short", max_chars=2400, banned_terms=())
    assert short.value.code == REJECT_TOO_SHORT
    with pytest.raises(LifeStoryRejectedError) as banned:
        parse_story(
            "Title\n\n" + STORY_BODY + " Good night, Keeper.",
            max_chars=2400,
            banned_terms=("keeper",),
        )
    assert banned.value.code == REJECT_BANNED_ADDRESS
    assert find_banned_term("a masterpiece of a day", ("master",)) is None
    assert find_banned_term("晚安，館主。", ("館主",)) == "館主"
    assert strip_citations("x [file:3#2] y <cite id=1>z</cite>") == "x y z"


def test_life_story_due_rules() -> None:
    base: dict[str, Any] = {
        "enabled": True,
        "conversations": 5,
        "last_life_story_conversations": 0,
        "every_conversations": 5,
        "stories_last_30d": 0,
        "max_per_30d": 4,
        "has_active_job": False,
    }
    assert life_story_due(**base)
    assert not life_story_due(**{**base, "enabled": False})
    assert not life_story_due(**{**base, "conversations": 4})
    assert not life_story_due(**{**base, "stories_last_30d": 4})
    assert not life_story_due(**{**base, "has_active_job": True})
    assert cadence_trigger_key(VELLUM, 5) == "cadence:preset:vellum:5"


# --- scheduling -----------------------------------------------------------------


def test_cadence_queues_once_at_k_conversations(client: TestClient, owner_engine: Engine) -> None:
    _install_config(client, every_conversations=2)
    _conversations(client, 1)
    assert _jobs(owner_engine) == []
    _conversations(client, 1)
    jobs = _jobs(owner_engine)
    assert len(jobs) == 1
    assert jobs[0]["trigger"] == "cadence"
    assert jobs[0]["trigger_key"] == "cadence:preset:vellum:2"
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["companion_ref"] == VELLUM
    # An active job blocks a second one, and repeating a run never recounts.
    _conversations(client, 2)
    assert len(_jobs(owner_engine)) == 1
    with owner_engine.connect() as connection:
        conversations = connection.execute(
            text("SELECT conversations FROM companion_bond WHERE companion_ref = :ref"),
            {"ref": VELLUM},
        ).scalar_one()
    assert conversations == 4


def test_duplicate_trigger_key_is_a_no_op(client: TestClient, root_account: UserClient) -> None:
    database: Database = client.app.state.db

    async def enqueue_twice() -> tuple[int | None, int | None]:
        async with database.user_session(root_account.user_id, "root") as session:
            repository = LifeStoryRepository(session, root_account.user_id)
            first = await repository.enqueue(
                companion_ref=VELLUM,
                locale="en",
                trigger="cadence",
                trigger_key="cadence:preset:vellum:5",
                now=utcnow(),
            )
            second = await repository.enqueue(
                companion_ref=VELLUM,
                locale="en",
                trigger="cadence",
                trigger_key="cadence:preset:vellum:5",
                now=utcnow(),
            )
            return first, second

    first, second = client.portal.call(enqueue_twice)
    assert first is not None and second is None


def test_thirty_day_cap_and_disabled_schedule(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
) -> None:
    _queue_job(owner_engine, root_account.user_id, status="succeeded")
    _install_config(client, every_conversations=1, max_per_30d=1)
    _conversations(client, 2)
    assert [job["status"] for job in _jobs(owner_engine)] == ["succeeded"]

    _install_config(client, enabled=False, every_conversations=1, max_per_30d=9)
    _conversations(client, 1)
    assert len(_jobs(owner_engine)) == 1


# --- the worker -----------------------------------------------------------------


def test_worker_writes_a_story_that_later_surfaces(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
) -> None:
    job_id = _queue_job(owner_engine, root_account.user_id)
    generator = _FakeGenerator()
    worker = _worker(client, generator=generator)
    assert client.portal.call(worker.run_once) == 1

    [job] = _jobs(owner_engine)
    assert job["id"] == job_id and job["status"] == "succeeded" and job["attempts"] == 1
    [story] = _stories(owner_engine)
    assert story["fragment_key"] == f"g-{story['id']}"
    assert story["status"] == "published" and story["tier"] == "familiar"
    assert story["title"] == "The Kitchen Door" and story["text"] == STORY_BODY
    assert (story["model"], story["prompt_tokens"], story["completion_tokens"]) == (
        "fake-aux",
        321,
        123,
    )
    refs = story["source_refs"]
    assert refs == {"memory_ids": [11, 12], "file_ids": [], "memory_count": 2, "file_count": 0}
    assert "SECRET" not in json.dumps(refs)

    # The prompt carries the material and canon, in the job's language.
    [call] = generator.calls
    prompt = call["messages"][0]["content"]
    assert "SECRET-EGGS" in prompt and "English" in prompt
    assert "Vellum" in call["system"]

    async def generated_keys() -> list[str]:
        database: Database = client.app.state.db
        async with database.user_session(root_account.user_id, "root") as session:
            stories = build_companion_story_service(session, user_id=root_account.user_id)
            target = await stories.resolve(VELLUM)
            items = await stories.fragments(target, "en", include_generated=True)
            editor = await stories.fragments(target, "en")
            assert all(item.origin != "generated" for item in editor)
            return [item.key for item in items if item.origin == "generated"]

    assert client.portal.call(generated_keys) == [story["fragment_key"]]


def test_used_memories_are_excluded_next_time(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
) -> None:
    _queue_job(owner_engine, root_account.user_id)
    client.portal.call(_worker(client, generator=_FakeGenerator()).run_once)
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO companion_story_job "
                "(user_id, companion_ref, locale, trigger, trigger_key) "
                "VALUES (:u, :r, 'en', 'admin', 'admin:second')"
            ),
            {"u": root_account.user_id, "r": VELLUM},
        )
    selector = _FakeSelector(list(MATERIALS))
    worker = _worker(client, generator=_FakeGenerator(), selector=selector)
    client.portal.call(worker.run_once)
    assert selector.requests[0].exclude_memory_ids == frozenset({11, 12})
    assert _jobs(owner_engine)[-1]["skip_reason"] == "no_material"


@pytest.mark.parametrize(
    ("generator", "allowed", "selector", "reason"),
    [
        (None, True, None, "model_not_assigned"),
        (_FakeGenerator(), False, None, "quota"),
        (_FakeGenerator(), True, _FakeSelector([]), "no_material"),
        (
            _FakeGenerator(error=LifeStoryGenerationError("quota", skip=True)),
            True,
            None,
            "quota",
        ),
    ],
)
def test_jobs_are_skipped_with_stable_codes(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
    generator: _FakeGenerator | None,
    allowed: bool,
    selector: _FakeSelector | None,
    reason: str,
) -> None:
    _queue_job(owner_engine, root_account.user_id)
    worker = _worker(client, generator=generator, allowed=allowed, selector=selector)
    assert client.portal.call(worker.run_once) == 0
    [job] = _jobs(owner_engine)
    assert (job["status"], job["skip_reason"]) == ("skipped", reason)
    assert _stories(owner_engine) == []


def test_real_wiring_skips_an_account_without_a_model(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
) -> None:
    create_memory(client, "We planted basil on the balcony.", "2026-05-01T09:00:00Z")
    _queue_job(owner_engine, root_account.user_id)
    worker = build_life_story_worker(client.app.state)
    assert client.portal.call(worker.drain) == 0
    [job] = _jobs(owner_engine)
    assert (job["status"], job["skip_reason"]) == ("skipped", "model_not_assigned")


def test_cancel_before_claim_and_after_generation(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
) -> None:
    _queue_job(owner_engine, root_account.user_id, status="cancel_requested")
    assert client.portal.call(_worker(client, generator=_FakeGenerator()).run_once) == 0
    assert _jobs(owner_engine)[0]["status"] == "cancelled"

    job_id = _queue_job(owner_engine, root_account.user_id)

    def cancel_now() -> None:
        with owner_engine.begin() as connection:
            connection.execute(
                text("UPDATE companion_story_job SET status = 'cancel_requested' WHERE id = :id"),
                {"id": job_id},
            )

    worker = _worker(client, generator=_FakeGenerator(on_generate=cancel_now))
    assert client.portal.call(worker.run_once) == 0
    assert _jobs(owner_engine)[-1]["status"] == "cancelled"
    assert _stories(owner_engine) == []


def test_crash_recovery_never_duplicates_a_story(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
) -> None:
    job_id = _queue_job(owner_engine, root_account.user_id)
    client.portal.call(_worker(client, generator=_FakeGenerator()).run_once)
    # Simulate a worker that wrote the story but died before closing the job.
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE companion_story_job SET status = 'running', "
                "lease_until = now() - interval '1 minute', finished_at = NULL WHERE id = :id"
            ),
            {"id": job_id},
        )
    generator = _FakeGenerator()
    assert client.portal.call(_worker(client, generator=generator).run_once) == 0
    assert generator.calls == []
    assert _jobs(owner_engine)[0]["status"] == "succeeded"
    assert len(_stories(owner_engine)) == 1


def test_rejected_output_retries_then_fails(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
) -> None:
    _queue_job(owner_engine, root_account.user_id)
    banned = _FakeGenerator(output="Title\n\n" + STORY_BODY + " Sleep well, Keeper.")
    config = _config(max_attempts=2)
    worker = _worker(client, generator=banned, config=config)
    client.portal.call(worker.run_once)
    job = _jobs(owner_engine)[0]
    assert (job["status"], job["error_code"]) == ("queued", REJECT_BANNED_ADDRESS)
    with owner_engine.begin() as connection:
        connection.execute(text("UPDATE companion_story_job SET not_before = now()"))
    client.portal.call(worker.run_once)
    job = _jobs(owner_engine)[0]
    assert (job["status"], job["error_code"], job["attempts"]) == (
        "failed",
        REJECT_BANNED_ADDRESS,
        2,
    )
    assert _stories(owner_engine) == []


def test_provider_errors_are_classified(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
) -> None:
    _queue_job(owner_engine, root_account.user_id)
    rejected = _FakeGenerator(error=LifeStoryGenerationError("provider_rejected"))
    client.portal.call(_worker(client, generator=rejected).run_once)
    assert (_jobs(owner_engine)[0]["status"], _jobs(owner_engine)[0]["error_code"]) == (
        "failed",
        "provider_rejected",
    )


def test_review_mode_keeps_stories_as_drafts(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
) -> None:
    _queue_job(owner_engine, root_account.user_id)
    worker = _worker(client, generator=_FakeGenerator(), config=_config(require_review=True))
    client.portal.call(worker.run_once)
    assert _stories(owner_engine)[0]["status"] == "draft"


# --- the generator adapter --------------------------------------------------------


@dataclass
class _FakeQuota:
    allowed: bool = True
    recorded: list[dict[str, int]] = field(default_factory=list)

    async def chat_allowed(self) -> bool:
        return self.allowed

    async def record_chat_usage(self, usage: dict[str, int]) -> None:
        self.recorded.append(dict(usage))


@dataclass
class _FakeText:
    error: Exception | None = None
    configured: bool = True
    model_name: str = "aux-model"

    async def complete_text(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        if self.error is not None:
            raise self.error
        return AiCompletion(
            text=STORY_OUTPUT,
            model="aux-model",
            usage={"prompt_tokens": 40, "completion_tokens": 20},
        )

    async def complete_json(self, system_prompt: str, user_prompt: str) -> AiCompletion:
        raise NotImplementedError


def _adapter(inner: _FakeText, quota: _FakeQuota) -> _LifeStoryGenerator:
    return _LifeStoryGenerator(MeteredTextGenerator(inner, quota), 3)


def test_adapter_records_usage_and_maps_errors() -> None:
    quota = _FakeQuota()
    generation = asyncio.run(
        _adapter(_FakeText(), quota).generate(
            system="s",
            messages=[{"role": "user", "content": "u"}],
            max_output_tokens=100,
        )
    )
    assert quota.recorded == [{"prompt_tokens": 40, "completion_tokens": 20}]
    assert (generation.prompt_tokens, generation.completion_tokens) == (40, 20)
    assert generation.provider_config_id == 3

    cases: list[tuple[Exception | None, bool, str, bool, bool]] = [
        (None, False, "quota", True, False),
        (ChatUsageLimitExceededError(), True, "quota", True, False),
        (AiNotConfiguredError(), True, "model_not_assigned", True, False),
        (AiProviderError("busy", retryable=True), True, "provider_unavailable", False, True),
        (AiProviderError("bad", status_code=400), True, "provider_rejected", False, False),
    ]
    for error, allowed, code, skip, retryable in cases:
        with pytest.raises(LifeStoryGenerationError) as raised:
            asyncio.run(
                _adapter(_FakeText(error=error), _FakeQuota(allowed=allowed)).generate(
                    system="s",
                    messages=[],
                    max_output_tokens=10,
                )
            )
        assert (raised.value.code, raised.value.skip, raised.value.retryable) == (
            code,
            skip,
            retryable,
        )


# --- isolation ------------------------------------------------------------------


def test_jobs_and_stories_are_private_per_account(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    _queue_job(owner_engine, root_account.user_id)
    client.portal.call(_worker(client, generator=_FakeGenerator()).run_once)
    other = user_client_factory()
    for table in ("companion_story_job", "companion_generated_story"):
        with rls_connection(owner_engine, user_id=other.user_id, role="user") as connection:
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        with rls_connection(
            owner_engine,
            user_id=root_account.user_id,
            role="root",
        ) as connection:
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 1

    async def other_view() -> tuple[bool, int]:
        database: Database = client.app.state.db
        async with database.user_session(other.user_id, "user") as session:
            repository = LifeStoryRepository(session, other.user_id)
            return (
                await repository.has_active_job(),
                len(await repository.list_published(VELLUM, "en")),
            )

    assert client.portal.call(other_view) == (False, 0)
