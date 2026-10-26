"""Multi-user account lifecycle, archive isolation, and row-level security."""

import asyncio
from collections.abc import Callable
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database, commit_and_reapply
from app.module.agent.test.fake_chat_generator import FakeChatGenerator, text_result
from app.module.auth.exception.domain_error import CannotImpersonateRootError
from app.module.auth.model.auth_model import AppUserModel
from app.module.auth.service.auth_service import AuthService
from tests.conftest import TEST_DATABASE_URL, UserClient, rls_connection
from tests.helpers import create_memory, create_text

ACCOUNTS_URL = "/api/v1/accounts"
PROMPTS_URL = "/api/v1/settings/frequent-prompts"
AGENT_USAGE = {
    "prompt_tokens": 31,
    "completion_tokens": 7,
    "total_tokens": 38,
    "prompt_cache_hit_tokens": 20,
    "prompt_cache_miss_tokens": 11,
}
MALFORMED_COMPLETION_USAGE = {
    "prompt_tokens": 10**18,
    "completion_tokens": -5,
    "total_tokens": 0,
    "prompt_cache_hit_tokens": 10**20,
}
ROOT_ONLY_PATHS = (
    ("/api/v1/accounts", "get"),
    ("/api/v1/settings/providers", "get"),
    ("/api/v1/settings/ingest", "get"),
    ("/api/v1/agent/settings", "get"),
    ("/api/v1/agent/settings/system-prompt", "get"),
)


async def _state(session: AsyncSession) -> tuple[str, str | None, str | None]:
    """Read the transaction-local role and RLS settings from one session."""
    row = (
        await session.execute(
            text(
                "SELECT current_user, "
                "current_setting('app.user_id', true), "
                "current_setting('app.user_role', true)"
            )
        )
    ).one()
    return (str(row[0]), row[1], row[2])


def test_account_lifecycle_forced_change_disable_and_reset(
    client: TestClient,
    client_factory: Callable[[], TestClient],
) -> None:
    """Root-created users must change the temporary password before access."""
    created = client.post(
        ACCOUNTS_URL,
        json={"username": "lifecycle.user", "display_name": "Lifecycle User"},
    )
    assert created.status_code == 201, created.text
    account = created.json()["user"]
    temporary_password = created.json()["temporary_password"]
    assert account["role"] == "user"
    assert account["is_active"] is True
    assert account["must_change_password"] is True
    assert len(temporary_password) == 20
    user_id = int(account["user_id"])

    user_client = client_factory()
    login = user_client.post(
        "/api/v1/auth/login",
        json={"username": "lifecycle.user", "password": temporary_password},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["must_change_password"] is True

    blocked = user_client.get("/api/v1/auth/me")
    assert blocked.status_code == 403
    assert blocked.json()["error"] == "password_change_required"

    new_password = "correct-horse-battery-lifecycle"
    changed = user_client.post(
        "/api/v1/auth/password",
        json={
            "current_password": temporary_password,
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    assert changed.status_code == 204, changed.text
    me = user_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["must_change_password"] is False

    disabled = client.post(f"{ACCOUNTS_URL}/{user_id}/disable")
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["is_active"] is False
    revoked = user_client.get("/api/v1/auth/me")
    assert revoked.status_code == 401
    assert revoked.json()["error"] == "authentication_required"
    disabled_login = user_client.post(
        "/api/v1/auth/login",
        json={"username": "lifecycle.user", "password": new_password},
    )
    assert disabled_login.status_code == 403
    assert disabled_login.json()["error"] == "account_disabled"

    enabled = client.post(f"{ACCOUNTS_URL}/{user_id}/enable")
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["is_active"] is True
    relogin = user_client.post(
        "/api/v1/auth/login",
        json={"username": "lifecycle.user", "password": new_password},
    )
    assert relogin.status_code == 200, relogin.text
    assert user_client.get("/api/v1/auth/me").status_code == 200

    reset = client.post(f"{ACCOUNTS_URL}/{user_id}/reset-password")
    assert reset.status_code == 200, reset.text
    reset_body = reset.json()
    reset_password = reset_body["temporary_password"]
    assert len(reset_password) == 20
    assert reset_body["user"]["must_change_password"] is True
    assert user_client.get("/api/v1/auth/me").status_code == 401

    stale_login = user_client.post(
        "/api/v1/auth/login",
        json={"username": "lifecycle.user", "password": new_password},
    )
    assert stale_login.status_code == 401
    assert stale_login.json()["error"] == "invalid_credentials"
    reset_login = user_client.post(
        "/api/v1/auth/login",
        json={"username": "lifecycle.user", "password": reset_password},
    )
    assert reset_login.status_code == 200, reset_login.text
    assert reset_login.json()["user"]["must_change_password"] is True
    assert user_client.get("/api/v1/auth/me").json()["error"] == "password_change_required"

    final_change = user_client.post(
        "/api/v1/auth/password",
        json={
            "current_password": reset_password,
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    assert final_change.status_code == 204, final_change.text
    assert user_client.get("/api/v1/auth/me").status_code == 200


def test_root_only_accounts_and_global_settings(
    client: TestClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    """Normal accounts are rejected before any root-only handler runs."""
    member = user_client_factory("guard.member")

    for path, method in ROOT_ONLY_PATHS:
        response = getattr(member.client, method)(path)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["error"] == "forbidden"

    forbidden_create = member.client.post(
        ACCOUNTS_URL,
        json={"username": "forbidden.user", "display_name": "Forbidden User"},
    )
    assert forbidden_create.status_code == 403
    assert forbidden_create.json()["error"] == "forbidden"

    # Personal settings stay available to a normal account.
    assert member.client.get(PROMPTS_URL).status_code == 200

    for path, method in ROOT_ONLY_PATHS:
        response = getattr(client, method)(path)
        assert response.status_code == 200, (path, response.text)

    accounts = client.get(ACCOUNTS_URL)
    assert accounts.status_code == 200
    usernames = [item["username"] for item in accounts.json()["items"]]
    assert usernames[0] == "owner"
    assert "guard.member" in usernames


def test_account_usage_starts_at_zero(
    client: TestClient,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    """Every account exposes the nested usage contract, starting at zero."""
    member = user_client_factory("usage.zero")
    accounts = client.get(ACCOUNTS_URL)
    assert accounts.status_code == 200, accounts.text
    by_user = {int(item["user_id"]): item for item in accounts.json()["items"]}
    expected = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "api_calls": 0,
        "turns": 0,
        "last_activity_at": None,
    }
    assert by_user[root_account.user_id]["usage"] == expected
    assert by_user[member.user_id]["usage"] == expected


def test_agent_turn_records_usage_and_account_rollup(
    client: TestClient,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
    owner_engine: Engine,
) -> None:
    """One provider completion updates the run and the account rollup."""
    member = user_client_factory("usage.member", display_name="Usage Member")
    member.client.app.state.agent_chat_generator = FakeChatGenerator.from_texts(
        "The usage counters are recorded.",
        usage=AGENT_USAGE,
    )

    created = member.client.post(
        "/api/v1/agent/conversations",
        json={"title": "Usage accounting"},
    )
    assert created.status_code == 201, created.text
    conversation_id = int(created.json()["id"])
    turn_response = member.client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "How much usage did that use?"},
        headers={"Accept": "application/json"},
    )
    assert turn_response.status_code == 200, turn_response.text
    run = turn_response.json()["run"]
    assert run["prompt_tokens"] == AGENT_USAGE["prompt_tokens"]
    assert run["completion_tokens"] == AGENT_USAGE["completion_tokens"]
    assert run["total_tokens"] == AGENT_USAGE["total_tokens"]
    assert run["cached_tokens"] == AGENT_USAGE["prompt_cache_hit_tokens"]
    assert run["api_calls"] == 1

    with owner_engine.connect() as connection:
        stored = connection.execute(
            text(
                "SELECT prompt_tokens, completion_tokens, total_tokens, "
                "cached_tokens, api_calls FROM agent_run WHERE id = :run_id"
            ),
            {"run_id": run["id"]},
        ).one()
    assert tuple(stored) == (
        AGENT_USAGE["prompt_tokens"],
        AGENT_USAGE["completion_tokens"],
        AGENT_USAGE["total_tokens"],
        AGENT_USAGE["prompt_cache_hit_tokens"],
        1,
    )

    accounts = client.get(ACCOUNTS_URL)
    assert accounts.status_code == 200, accounts.text
    by_user = {int(item["user_id"]): item for item in accounts.json()["items"]}
    member_usage = by_user[member.user_id]["usage"]
    assert member_usage["prompt_tokens"] == AGENT_USAGE["prompt_tokens"]
    assert member_usage["completion_tokens"] == AGENT_USAGE["completion_tokens"]
    assert member_usage["total_tokens"] == AGENT_USAGE["total_tokens"]
    assert member_usage["cached_tokens"] == AGENT_USAGE["prompt_cache_hit_tokens"]
    assert member_usage["api_calls"] == 1
    assert member_usage["turns"] == 1
    assert member_usage["last_activity_at"] is not None

    root_usage = by_user[root_account.user_id]["usage"]
    assert root_usage["turns"] == 0
    assert root_usage["api_calls"] == 0
    assert root_usage["total_tokens"] == 0


def test_malformed_completion_records_bounded_usage(
    client: TestClient,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    """A malformed provider result still counts one capped API call."""
    member = user_client_factory("usage.malformed")
    member.client.app.state.agent_chat_generator = FakeChatGenerator(
        [text_result("", usage=MALFORMED_COMPLETION_USAGE)]
    )

    created = member.client.post(
        "/api/v1/agent/conversations",
        json={"title": "Malformed completion"},
    )
    assert created.status_code == 201, created.text
    conversation_id = int(created.json()["id"])
    response = member.client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Return a malformed completion."},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    run = body["run"]
    assert run["status"] == "failed"
    assert run["error_code"] == "provider_error"
    assert run["prompt_tokens"] == 10**15
    assert run["completion_tokens"] == 0
    assert run["total_tokens"] == 10**15
    assert run["cached_tokens"] == 10**15
    assert run["api_calls"] == 1

    assistant_entries = [
        entry for entry in body["entries"] if entry["kind"] == "pi.assistant"
    ]
    assert len(assistant_entries) == 1
    assert assistant_entries[0]["data"]["usage"] == MALFORMED_COMPLETION_USAGE

    accounts = client.get(ACCOUNTS_URL)
    assert accounts.status_code == 200, accounts.text
    by_user = {int(item["user_id"]): item for item in accounts.json()["items"]}
    member_usage = by_user[member.user_id]["usage"]
    assert member_usage["prompt_tokens"] == 10**15
    assert member_usage["completion_tokens"] == 0
    assert member_usage["total_tokens"] == 10**15
    assert member_usage["cached_tokens"] == 10**15
    assert member_usage["api_calls"] == 1
    assert member_usage["turns"] == 1


def test_root_impersonation_round_trip(
    client: TestClient,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    """Root can act as a normal account and return without touching logins."""
    member = user_client_factory("impersonation.target", display_name="Target Account")
    root_login_before = client.get("/api/v1/auth/me").json()["last_login_at"]
    member_login_before = member.client.get("/api/v1/auth/me").json()["last_login_at"]

    started = client.post(f"{ACCOUNTS_URL}/{member.user_id}/impersonate")
    assert started.status_code == 200, started.text
    started_body = started.json()
    assert started_body["user"]["user_id"] == member.user_id
    assert started_body["user"]["role"] == "user"
    assert started_body["impersonation"]["actor_user_id"] == root_account.user_id
    assert started_body["impersonation"]["username"] == root_account.username

    status = client.get("/api/v1/auth/status")
    assert status.status_code == 200, status.text
    status_body = status.json()
    assert status_body["authenticated"] is True
    assert status_body["user"]["user_id"] == member.user_id
    assert status_body["impersonation"]["actor_user_id"] == root_account.user_id

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user_id"] == member.user_id
    assert me.json()["last_login_at"] == member_login_before

    # Root-only routes disappear while the session carries the target's role.
    denied = client.get(ACCOUNTS_URL)
    assert denied.status_code == 403
    assert denied.json()["error"] == "forbidden"

    # The target's own session is independent and remains valid.
    assert member.client.get("/api/v1/auth/me").status_code == 200

    stopped = client.post(
        "/api/v1/auth/impersonation/stop",
        json={"password": root_account.password},
    )
    assert stopped.status_code == 200, stopped.text
    stopped_body = stopped.json()
    assert stopped_body["user"]["user_id"] == root_account.user_id
    assert stopped_body["impersonation"] is None

    after = client.get("/api/v1/auth/status").json()
    assert after["user"]["user_id"] == root_account.user_id
    assert after["impersonation"] is None
    assert client.get("/api/v1/auth/me").json()["last_login_at"] == root_login_before
    assert client.get(ACCOUNTS_URL).status_code == 200


def test_stop_impersonation_requires_the_root_password(
    client: TestClient,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    """A wrong root password leaves the impersonation session untouched."""
    member = user_client_factory("impersonation.stop-password")
    started = client.post(f"{ACCOUNTS_URL}/{member.user_id}/impersonate")
    assert started.status_code == 200, started.text

    wrong = client.post(
        "/api/v1/auth/impersonation/stop",
        json={"password": "definitely-the-wrong-password"},
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"] == "impersonation_password_invalid"

    status = client.get("/api/v1/auth/status").json()
    assert status["authenticated"] is True
    assert status["user"]["user_id"] == member.user_id
    assert status["impersonation"]["actor_user_id"] == root_account.user_id
    assert client.get("/api/v1/auth/me").json()["user_id"] == member.user_id

    stopped = client.post(
        "/api/v1/auth/impersonation/stop",
        json={"password": root_account.password},
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["user"]["user_id"] == root_account.user_id


def test_root_password_change_revokes_impersonation_sessions(
    client: TestClient,
    root_account: UserClient,
    client_factory: Callable[[], TestClient],
    user_client_factory: Callable[..., UserClient],
) -> None:
    """Rotating the root password invalidates sessions it started as a target."""
    member = user_client_factory("impersonation.rotated")
    started = client.post(f"{ACCOUNTS_URL}/{member.user_id}/impersonate")
    assert started.status_code == 200, started.text

    second_root = client_factory()
    login = second_root.post(
        "/api/v1/auth/login",
        json={"username": root_account.username, "password": root_account.password},
    )
    assert login.status_code == 200, login.text
    new_password = "correct-horse-battery-rotated-root"
    changed = second_root.post(
        "/api/v1/auth/password",
        json={
            "current_password": root_account.password,
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    assert changed.status_code == 204, changed.text

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401
    assert me.json()["error"] == "authentication_required"
    assert client.get("/api/v1/auth/status").json()["authenticated"] is False
    stop = client.post(
        "/api/v1/auth/impersonation/stop",
        json={"password": new_password},
    )
    assert stop.status_code == 401
    assert stop.json()["error"] == "authentication_required"


def test_impersonation_requires_root_and_stop_requires_impersonation(
    user_client_factory: Callable[..., UserClient],
) -> None:
    """A normal account cannot start impersonation or stop a normal session."""
    actor = user_client_factory("impersonation.actor")
    target = user_client_factory("impersonation.victim")

    denied = actor.client.post(f"{ACCOUNTS_URL}/{target.user_id}/impersonate")
    assert denied.status_code == 403
    assert denied.json()["error"] == "forbidden"

    stopped = actor.client.post(
        "/api/v1/auth/impersonation/stop",
        json={"password": actor.password},
    )
    assert stopped.status_code == 400
    assert stopped.json()["error"] == "not_impersonating"
    assert actor.client.get("/api/v1/auth/status").json()["impersonation"] is None


def test_impersonation_rejects_self_disabled_and_forced_accounts(
    client: TestClient,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    """Root cannot impersonate itself or an account that cannot sign in."""
    self_attempt = client.post(f"{ACCOUNTS_URL}/{root_account.user_id}/impersonate")
    assert self_attempt.status_code == 409
    assert self_attempt.json()["error"] == "cannot_impersonate_self"

    disabled = user_client_factory("impersonation.disabled")
    disabled_response = client.post(f"{ACCOUNTS_URL}/{disabled.user_id}/disable")
    assert disabled_response.status_code == 200, disabled_response.text
    disabled_attempt = client.post(f"{ACCOUNTS_URL}/{disabled.user_id}/impersonate")
    assert disabled_attempt.status_code == 409
    assert disabled_attempt.json()["error"] == "account_not_impersonatable"

    forced = user_client_factory(
        "impersonation.forced",
        must_change_password=True,
        complete_password_change=False,
    )
    forced_attempt = client.post(f"{ACCOUNTS_URL}/{forced.user_id}/impersonate")
    assert forced_attempt.status_code == 409
    assert forced_attempt.json()["error"] == "account_not_impersonatable"


class _UserById:
    """Minimal account reader for a root-target guard unreachable through HTTP."""

    def __init__(self, users: dict[int, AppUserModel]) -> None:
        self._users = users

    async def get_by_id(self, user_id: int) -> AppUserModel | None:
        return self._users.get(user_id)


def test_impersonation_rejects_a_root_target() -> None:
    """The service guard rejects any root target, even outside the single-root DB."""
    actor = AppUserModel(
        id=9002,
        username="root.actor",
        role="root",
        is_active=True,
        must_change_password=False,
    )
    target = AppUserModel(
        id=9001,
        username="root.target",
        role="root",
        is_active=True,
        must_change_password=False,
    )
    service = AuthService(
        user_repository=cast(Any, _UserById({actor.id: actor, target.id: target})),
        session_repository=cast(Any, object()),
        password_hasher=cast(Any, object()),
        token_generator=cast(Any, object()),
        session_ttl_hours=1,
        login_attempt_limit=1,
        login_window_minutes=1,
    )

    with pytest.raises(CannotImpersonateRootError):
        asyncio.run(
            service.impersonate(
                actor_user_id=actor.id,
                target_user_id=target.id,
            )
        )


def test_password_change_is_forbidden_while_impersonating(
    client: TestClient,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    """An impersonation session cannot change the target's password."""
    member = user_client_factory("impersonation.password")
    started = client.post(f"{ACCOUNTS_URL}/{member.user_id}/impersonate")
    assert started.status_code == 200, started.text
    new_password = "correct-horse-battery-impersonated"

    changed = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": member.password,
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    assert changed.status_code == 403
    assert changed.json()["error"] == "impersonation_password_change_forbidden"

    assert member.client.get("/api/v1/auth/me").status_code == 200
    stopped = client.post(
        "/api/v1/auth/impersonation/stop",
        json={"password": root_account.password},
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["user"]["role"] == "root"


def test_private_archive_isolation_between_accounts(
    user_client_factory: Callable[..., UserClient],
) -> None:
    """Every archive layer filters by the authenticated owner."""
    alice = user_client_factory("alice")
    bob = user_client_factory("bob")
    marker = "quarantine-zeta-marker"

    file = create_text(
        alice.client,
        "/alice/secret.md",
        f"{marker} belongs to Alice's file.",
        "2026-09-01T09:00:00Z",
    )
    file_id = int(file["id"])
    alice_paths = alice.client.get(
        "/api/v1/paths",
        params={"path": "/", "path_depth": 2},
    )
    assert alice_paths.status_code == 200
    assert any(item["path"] == "/alice" for item in alice_paths.json()["directories"])

    first_memory = create_memory(
        alice.client,
        f"{marker} first memory.",
        "2026-09-02T09:00:00Z",
    )
    second_memory = create_memory(
        alice.client,
        f"{marker} second memory.",
        "2026-09-03T09:00:00Z",
    )
    first_memory_id = int(first_memory["memory"]["memory_id"])
    second_memory_id = int(second_memory["memory"]["memory_id"])

    summary = alice.client.post(
        "/api/v1/summaries",
        json={"memory_ids": [first_memory_id, second_memory_id]},
    )
    assert summary.status_code == 201, summary.text
    summary_id = int(summary.json()["memory_summary_id"])

    conversation = alice.client.post(
        "/api/v1/agent/conversations",
        json={"title": "Alice only"},
    )
    assert conversation.status_code == 201, conversation.text
    conversation_id = int(conversation.json()["id"])

    question = alice.client.post(
        "/api/v1/agent/questions",
        json={"question": f"{marker} question?"},
    )
    assert question.status_code == 201, question.text
    question_id = int(question.json()["id"])

    prompt = alice.client.post(
        PROMPTS_URL,
        json={
            "title": "Alice prompt",
            "prompt_text": f"{marker} prompt",
            "sort_order": 10,
        },
    )
    assert prompt.status_code == 201, prompt.text

    assert bob.client.get(f"/api/v1/files/{file_id}").status_code == 404
    bob_paths = bob.client.get(
        "/api/v1/paths",
        params={"path": "/", "path_depth": 2},
    )
    assert bob_paths.status_code == 200
    assert all(item["file_id"] != file_id for item in bob_paths.json()["files"])
    assert all(item["path"] != "/alice" for item in bob_paths.json()["directories"])

    assert bob.client.get(f"/api/v1/memories/{first_memory_id}").status_code == 404
    assert bob.client.get("/api/v1/memories").json()["total_results"] == 0
    assert bob.client.get(f"/api/v1/summaries/{summary_id}").status_code == 404
    assert bob.client.get("/api/v1/summaries").json()["total_results"] == 0
    assert bob.client.get(f"/api/v1/agent/conversations/{conversation_id}").status_code == 404
    assert bob.client.get("/api/v1/agent/conversations").json()["total_results"] == 0
    stolen_question = bob.client.patch(
        f"/api/v1/agent/questions/{question_id}",
        json={"question": "Stolen question?"},
    )
    assert stolen_question.status_code == 404
    assert bob.client.get("/api/v1/agent/questions").json()["total"] == 0
    assert bob.client.get(PROMPTS_URL).json()["resources"] == []

    search = bob.client.get(
        "/api/v1/search",
        params={"query": marker, "result_number": 10},
    )
    assert search.status_code == 200
    assert search.json()["file_results"] == []
    assert search.json()["memory_results"] == []
    assert search.json()["summary_results"] == []

    # Logical paths are unique per owner: the same path is a new file for Bob.
    bob_same_path = create_text(
        bob.client,
        "/alice/secret.md",
        "Bob's own note at the same logical path.",
        "2026-09-04T09:00:00Z",
    )
    assert int(bob_same_path["id"]) > file_id
    assert bob.client.get(f"/api/v1/files/{bob_same_path['id']}").status_code == 200
    assert alice.client.get(f"/api/v1/files/{file_id}").status_code == 200
    assert alice.client.get("/api/v1/agent/conversations").json()["total_results"] == 1
    assert alice.client.get(PROMPTS_URL).json()["total_results"] == 1


def test_frequent_prompt_cap_and_reorder_are_per_account(
    user_client_factory: Callable[..., UserClient],
) -> None:
    """One owner's cap, order, and cached list never leak into another's."""
    alice = user_client_factory("prompts.alice")
    bob = user_client_factory("prompts.bob")

    alice_first = alice.client.post(
        PROMPTS_URL,
        json={"title": "Alice prompt", "prompt_text": "Alice text.", "sort_order": 10},
    )
    assert alice_first.status_code == 201, alice_first.text
    assert alice.client.get(PROMPTS_URL).json()["total_results"] == 1

    bob_first = bob.client.post(
        PROMPTS_URL,
        json={"title": "Bob prompt", "prompt_text": "Bob text.", "sort_order": 10},
    )
    assert bob_first.status_code == 201, bob_first.text
    assert alice.client.get(PROMPTS_URL).json()["resources"][0]["title"] == "Alice prompt"
    assert bob.client.get(PROMPTS_URL).json()["resources"][0]["title"] == "Bob prompt"

    for index in range(19):
        created = alice.client.post(
            PROMPTS_URL,
            json={
                "title": f"Alice bulk {index:02d}",
                "prompt_text": f"Alice bulk text {index:02d}.",
                "sort_order": 100 + index,
            },
        )
        assert created.status_code == 201, created.text

    alice_list = alice.client.get(PROMPTS_URL).json()
    assert alice_list["total_results"] == 20
    rejected = alice.client.post(
        PROMPTS_URL,
        json={"title": "Over cap", "prompt_text": "Never stored.", "sort_order": 999},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"] == "too_many_frequent_prompts"

    bob_second = bob.client.post(
        PROMPTS_URL,
        json={"title": "Bob second", "prompt_text": "Still allowed.", "sort_order": 20},
    )
    assert bob_second.status_code == 201, bob_second.text
    bob_ids = [item["id"] for item in bob.client.get(PROMPTS_URL).json()["resources"]]
    assert bob_ids == [bob_first.json()["id"], bob_second.json()["id"]]

    alice_ids = [item["id"] for item in alice_list["resources"]]
    reordered = alice.client.post(
        f"{PROMPTS_URL}/reorder",
        json={"prompt_ids": list(reversed(alice_ids))},
    )
    assert reordered.status_code == 200, reordered.text
    assert [item["id"] for item in reordered.json()["resources"]] == list(reversed(alice_ids))
    assert [item["id"] for item in bob.client.get(PROMPTS_URL).json()["resources"]] == bob_ids

    foreign_update = alice.client.put(
        f"{PROMPTS_URL}/{bob_first.json()['id']}",
        json={"title": "Stolen", "prompt_text": "Stolen text.", "sort_order": 1},
    )
    assert foreign_update.status_code == 404
    foreign_delete = alice.client.delete(f"{PROMPTS_URL}/{bob_first.json()['id']}")
    assert foreign_delete.status_code == 404
    assert bob.client.get(PROMPTS_URL).json()["total_results"] == 2


def test_rls_blocks_cross_user_direct_sql_and_requires_context(
    owner_engine: Engine,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    """Forced RLS is the database-level backstop behind service filters."""
    member = user_client_factory("rls.member")
    with owner_engine.begin() as connection:
        root_prompt_id = connection.execute(
            text(
                "INSERT INTO frequently_used_prompt "
                "(user_id, title, prompt_text, sort_order) "
                "VALUES (:user_id, 'Root prompt', 'Root text.', 0) "
                "RETURNING id"
            ),
            {"user_id": root_account.user_id},
        ).scalar_one()

    with rls_connection(owner_engine, user_id=member.user_id, role="user") as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM frequently_used_prompt")).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM frequently_used_prompt WHERE id = :id"),
                {"id": root_prompt_id},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("UPDATE frequently_used_prompt SET title = 'stolen' WHERE id = :id"),
                {"id": root_prompt_id},
            ).rowcount
            == 0
        )
        assert (
            connection.execute(
                text("DELETE FROM frequently_used_prompt WHERE id = :id"),
                {"id": root_prompt_id},
            ).rowcount
            == 0
        )

    with pytest.raises(DBAPIError, match="row-level security"):
        with rls_connection(owner_engine, user_id=member.user_id, role="user") as connection:
            connection.execute(
                text(
                    "INSERT INTO frequently_used_prompt "
                    "(user_id, title, prompt_text, sort_order) "
                    "VALUES (:user_id, 'Stolen', 'Stolen text.', 0)"
                ),
                {"user_id": root_account.user_id},
            )

    # A session with no user context can read global config but no private row.
    with rls_connection(owner_engine) as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM frequently_used_prompt")).scalar_one()
            == 0
        )
        assert (
            connection.execute(text("SELECT count(*) FROM system_prompt_section")).scalar_one() == 4
        )

    with pytest.raises(DBAPIError, match="row-level security"):
        with rls_connection(owner_engine, user_id=member.user_id, role="user") as connection:
            connection.execute(
                text(
                    "INSERT INTO system_prompt_section (title, body, sort_order) "
                    "VALUES ('Not allowed', 'Normal users cannot edit this.', 999)"
                )
            )

    with rls_connection(owner_engine, user_id=root_account.user_id, role="root") as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM frequently_used_prompt")).scalar_one()
            == 1
        )
        connection.execute(
            text(
                "INSERT INTO system_prompt_section (title, body, sort_order) "
                "VALUES ('Root only', 'Root-authored config.', 999)"
            )
        )
        assert (
            connection.execute(text("SELECT count(*) FROM system_prompt_section")).scalar_one() == 5
        )


def test_commit_and_reapply_restores_rls_context(
    owner_engine: Engine,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    """A workflow checkpoint must not fall back to the owner login."""
    member = user_client_factory("worker.member")
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO frequently_used_prompt "
                "(user_id, title, prompt_text, sort_order) "
                "VALUES (:user_id, 'Root prompt', 'Root text.', 0)"
            ),
            {"user_id": root_account.user_id},
        )

    async def probe() -> None:
        database = Database(TEST_DATABASE_URL)
        try:
            async with database.user_session(member.user_id, "user") as session:
                expected = ("apsor_app", str(member.user_id), "user")
                assert await _state(session) == expected
                before_count = (
                    await session.execute(text("SELECT count(*) FROM frequently_used_prompt"))
                ).scalar_one()
                assert before_count == 0
                await session.execute(
                    text(
                        "INSERT INTO frequently_used_prompt "
                        "(user_id, title, prompt_text, sort_order) "
                        "VALUES (:user_id, 'Worker prompt', 'Worker text.', 0)"
                    ),
                    {"user_id": member.user_id},
                )
                await commit_and_reapply(session, member.user_id, "user")
                assert await _state(session) == expected
                after_count = (
                    await session.execute(text("SELECT count(*) FROM frequently_used_prompt"))
                ).scalar_one()
                assert after_count == 1
        finally:
            await database.dispose()

    asyncio.run(probe())
