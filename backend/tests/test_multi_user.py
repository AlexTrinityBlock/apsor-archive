"""Multi-user account lifecycle, archive isolation, and row-level security."""

import asyncio
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import Database, commit_and_reapply
from tests.conftest import TEST_DATABASE_URL, UserClient, rls_connection
from tests.helpers import create_memory, create_text

ACCOUNTS_URL = "/api/v1/accounts"
PROMPTS_URL = "/api/v1/settings/frequent-prompts"
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
