"""Root companion administration: every operation, the scope, and the access log."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.module.companion.service.companion_admin_service import (
    KNOBS,
    coerce_knob,
    knob_default,
    placeholders,
    render_sample,
)
from tests.conftest import UserClient, rls_connection
from tests.helpers import create_memory

ADMIN = "/api/v1/admin/companions"


def _story(engine: Engine, user_id: int, *, ref: str = "preset:vellum", text_body: str) -> int:
    with engine.begin() as connection:
        story_id = int(
            connection.execute(
                text(
                    "INSERT INTO companion_generated_story (user_id, companion_ref, locale, "
                    "fragment_key, title, text, weight, themes, status, source_refs) VALUES "
                    "(:user_id, :ref, 'en', 'g-pending', 'Through the door', :body, 'past', "
                    "'[]'::jsonb, 'published', '{\"memory\": [1, 2]}'::jsonb) RETURNING id"
                ),
                {"user_id": user_id, "ref": ref, "body": text_body},
            ).scalar_one()
        )
        connection.execute(
            text("UPDATE companion_generated_story SET fragment_key = :key WHERE id = :id"),
            {"key": f"g-{story_id}", "id": story_id},
        )
    return story_id


def _access_actions(engine: Engine, target: int) -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT action FROM companion_admin_access_log WHERE target_user_id = :id "
                "ORDER BY id"
            ),
            {"id": target},
        )
        return [str(row[0]) for row in rows]


def _ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def test_non_root_is_forbidden(
    client: TestClient, user_client_factory: Callable[..., UserClient]
) -> None:
    member = user_client_factory("plain.member")
    for path in ("/presets", "/users", f"/users/{member.user_id}", "/config", "/seed"):
        response = member.client.get(f"{ADMIN}{path}")
        assert response.status_code == 403, path
    assert client.get(f"{ADMIN}/presets").status_code == 200


def test_global_content_endpoints(client: TestClient) -> None:
    presets = _ok(client.get(f"{ADMIN}/presets"))
    ids = [preset["id"] for preset in presets]
    assert "vellum" in ids and len(ids) == 6
    # The test database is seeded like every process start.
    assert all(preset["seeded"] for preset in presets)

    updated = _ok(client.patch(f"{ADMIN}/presets/atlas", json={"position": 0}))
    assert updated["seeded"] and updated["admin_modified"]

    text_body = _ok(client.get(f"{ADMIN}/presets/vellum/text", params={"locale": "zh-TW"}))
    assert text_body["name"] == "Vellum"
    changed = _ok(
        client.put(
            f"{ADMIN}/presets/vellum/text",
            params={"locale": "en"},
            json={"persona": "You are Vellum. Speak softly, as an equal."},
        )
    )
    assert changed["admin_modified"]
    reset = _ok(client.post(f"{ADMIN}/presets/vellum/text/reset", params={"locale": "en"}))
    assert not reset["admin_modified"] and reset["persona"] != changed["persona"]

    lore = _ok(client.get(f"{ADMIN}/lore", params={"preset": "vellum", "weight": "heart"}))
    assert lore and all(item["weight"] == "heart" for item in lore)
    key = lore[0]["fragment_key"]
    edited = _ok(
        client.patch(
            f"{ADMIN}/lore/vellum/{key}", json={"text": "A new rare memory.", "locale": "en"}
        )
    )
    assert edited["admin_modified"] and edited["text"] == "A new rare memory." and edited["id"] > 0
    assert _ok(client.post(f"{ADMIN}/lore/vellum/{key}/retire"))["retired"]
    restored = _ok(client.post(f"{ADMIN}/lore/vellum/{key}/reset"))
    assert not restored["retired"] and restored["text"] != "A new rare memory."
    created = _ok(
        client.post(
            f"{ADMIN}/lore",
            json={
                "preset_id": "quill",
                "fragment_key": "quill-admin-1",
                "weight": "everyday",
                "themes": ["ink"],
                "refs": [],
                "text": "An admin-written memory.",
            },
        ),
        201,
    )
    assert created["fragment_key"] == "quill-admin-1"
    searched = _ok(client.get(f"{ADMIN}/lore", params={"q": "admin-written"}))
    assert [item["fragment_key"] for item in searched] == ["quill-admin-1"]

    docs = _ok(client.get(f"{ADMIN}/world-docs"))
    assert any(doc["doc_key"] == "bible" for doc in docs)
    bible = _ok(client.get(f"{ADMIN}/world-docs/bible"))
    saved = _ok(
        client.put(
            f"{ADMIN}/world-docs/bible",
            json={"body_md": bible["body_md"] + "\n\nAn added line.", "version": bible["version"]},
        )
    )
    assert saved["version"] == bible["version"] + 1
    stale = client.put(f"{ADMIN}/world-docs/bible", json={"body_md": "x", "version": 1})
    assert stale.status_code == 422
    assert len(_ok(client.get(f"{ADMIN}/world-docs/bible/revisions"))) == 1
    assert "An added line." not in _ok(client.post(f"{ADMIN}/world-docs/bible/reset"))["body_md"]

    canon = _ok(client.get(f"{ADMIN}/canon"))
    assert canon
    upserted = _ok(
        client.put(
            f"{ADMIN}/canon",
            json={"entity_id": canon[0]["entity_id"], "name": "Renamed", "summary": "Edited."},
        )
    )
    assert upserted["admin_modified"]

    config = _ok(client.get(f"{ADMIN}/config"))
    assert {knob["key"] for knob in config["knobs"]} == {knob.key for knob in KNOBS}
    bumped = _ok(client.patch(f"{ADMIN}/config", json={"values": {"story_moment_every_runs": 4}}))
    assert next(k for k in bumped["knobs"] if k["key"] == "story_moment_every_runs")["value"] == 4
    assert client.patch(f"{ADMIN}/config", json={"values": {"untold_bonus": 3}}).status_code == 422
    assert client.patch(f"{ADMIN}/config", json={"values": {"nope": 1}}).status_code == 422
    reset_config = _ok(client.post(f"{ADMIN}/config/reset"))
    assert (
        next(k for k in reset_config["knobs"] if k["key"] == "story_moment_every_runs")["value"]
        == 3
    )

    templates = _ok(client.get(f"{ADMIN}/templates"))
    assert any(t["template_key"] == "lore_guidance" for t in templates)
    bad = client.put(f"{ADMIN}/templates/life_story_user", json={"body": "No placeholders here."})
    assert bad.status_code == 422
    good = _ok(
        client.put(
            f"{ADMIN}/templates/life_story_user",
            json={
                "body": "{companion_name} {persona} {canon} {memories} {language} {max_chars}",
            },
        )
    )
    assert good["missing_placeholders"] == []
    preview = _ok(
        client.post(
            f"{ADMIN}/templates/preview",
            json={"template_key": "life_story_user", "body": "Hello {companion_name}, {oops}"},
        )
    )
    assert preview["rendered"].startswith("Hello Vellum") and preview["unknown_placeholders"] == [
        "oops"
    ]
    assert (
        _ok(client.post(f"{ADMIN}/templates/lore_guidance/reset"))["template_key"]
        == "lore_guidance"
    )
    assert not _ok(client.post(f"{ADMIN}/templates/life_story_user/reset"))["admin_modified"]

    status = _ok(client.get(f"{ADMIN}/seed"))
    assert status["shipped_presets"] == 6 and status["admin_modified_rows"] >= 1
    # The process installed its seeder, so root can re-apply the shipped seed;
    # rows root edited stay edited.
    applied = _ok(client.post(f"{ADMIN}/seed/apply", json={"force_keys": []}))
    assert applied["admin_modified_rows"] >= 1


def test_per_user_policy_progress_and_overrides(
    client: TestClient,
    owner_engine: Engine,
    user_client_factory: Callable[..., UserClient],
) -> None:
    member = user_client_factory("story.member")
    uid = member.user_id
    summaries = _ok(client.get(f"{ADMIN}/users"))
    assert any(row["user_id"] == uid for row in summaries)

    user = _ok(client.get(f"{ADMIN}/users/{uid}"))
    assert user["policy"]["active_ref"] == "preset:vellum"
    assert user["bonds"][0]["companion_ref"] == "preset:vellum"

    policy = _ok(
        client.put(
            f"{ADMIN}/users/{uid}/policy",
            json={
                "default_ref": "preset:atlas",
                "allowed_refs": ["preset:atlas", "preset:quill"],
                "allow_custom": True,
                "pinned_ref": None,
                "pin_enabled": False,
            },
        )
    )
    assert policy["active_ref"] == "preset:atlas" and policy["active_source"] == "admin_default"
    catalog = _ok(member.client.get("/api/v1/companions/presets"))
    assert {p["id"] for p in catalog["presets"]} == {"atlas", "quill"}
    assert catalog["active_ref"] == "preset:atlas" and not catalog["pinned"]
    pinned = _ok(
        client.put(
            f"{ADMIN}/users/{uid}/policy",
            json={"pinned_ref": "preset:quill", "pin_enabled": True},
        )
    )
    assert pinned["active_ref"] == "preset:quill" and pinned["active_source"] == "pinned"
    assert _ok(member.client.get("/api/v1/companions/presets"))["pinned"]
    bad_ref = client.put(f"{ADMIN}/users/{uid}/policy", json={"default_ref": "preset:nobody"})
    assert bad_ref.status_code == 422
    # The account itself can never write root's policy rows.
    with rls_connection(owner_engine, user_id=uid, role="user") as connection:
        rows = connection.execute(
            text("UPDATE companion_account_policy SET pin_enabled = false WHERE user_id = :id"),
            {"id": uid},
        )
        assert rows.rowcount == 0

    config = _ok(
        client.patch(f"{ADMIN}/users/{uid}/config", json={"values": {"story_moment_every_runs": 2}})
    )
    assert config["overrides"]["story_moment_every_runs"] == 2
    assert (
        client.patch(
            f"{ADMIN}/users/{uid}/config", json={"values": {"life_story_poll_seconds": 5}}
        ).status_code
        == 422
    )
    assert (
        _ok(client.post(f"{ADMIN}/users/{uid}/config/reset"))["overrides"][
            "story_moment_every_runs"
        ]
        is None
    )

    ref = "preset:vellum"
    fragments = _ok(client.get(f"{ADMIN}/users/{uid}/companions/{ref}/fragments"))
    # Nothing is locked: every memory is either told or not yet, whatever its weight.
    assert "unlocked_tiers" not in fragments
    states = {f["state"] for f in fragments["fragments"]}
    assert states == {"untold"}
    assert {f["weight"] for f in fragments["fragments"]} == {"everyday", "past", "heart"}
    first_key = next(f["key"] for f in fragments["fragments"] if f["weight"] == "everyday")
    told = _ok(
        client.put(
            f"{ADMIN}/users/{uid}/companions/{ref}/progress",
            json={"fragment_key": first_key, "told": True},
        )
    )
    assert next(f for f in told["fragments"] if f["key"] == first_key)["state"] == "told"
    bond = _ok(
        client.patch(f"{ADMIN}/users/{uid}/companions/{ref}/bond", json={"completed_runs": 25})
    )
    vellum = next(b for b in bond["bonds"] if b["companion_ref"] == ref)
    assert vellum["completed_runs"] == 25 and vellum["first_met_at"] is not None
    reset = _ok(
        client.post(f"{ADMIN}/users/{uid}/companions/{ref}/progress/reset", json={"scope": "all"})
    )
    assert next(b for b in reset["bonds"] if b["companion_ref"] == ref)["completed_runs"] == 0

    persona = _ok(
        client.put(
            f"{ADMIN}/users/{uid}/companions/{ref}/persona",
            json={"persona": "You are Vellum, for this account only."},
        )
    )
    assert persona["persona"].endswith("only.") and persona["inherited_persona"]
    assert (
        _ok(client.post(f"{ADMIN}/users/{uid}/companions/{ref}/persona/reset"))["persona"] is None
    )

    _ok(
        client.put(
            f"{ADMIN}/users/{uid}/companions/{ref}/lore-overrides",
            json={"fragment_key": first_key, "action": "hide"},
        )
    )
    _ok(
        client.put(
            f"{ADMIN}/users/{uid}/companions/{ref}/lore-overrides",
            json={
                "fragment_key": "admin-extra",
                "action": "add",
                "weight": "everyday",
                "text": "Only for this account.",
            },
        )
    )
    overrides = _ok(client.get(f"{ADMIN}/users/{uid}/companions/{ref}/lore-overrides"))
    assert {o["fragment_key"] for o in overrides} == {first_key, "admin-extra"}
    effective = _ok(client.get(f"{ADMIN}/users/{uid}/companions/{ref}/fragments"))
    hidden = next(f for f in effective["fragments"] if f["key"] == first_key)
    assert hidden["hidden_by_admin"]
    assert any(f["key"] == "admin-extra" and f["origin"] == "admin" for f in effective["fragments"])
    deleted = client.delete(f"{ADMIN}/users/{uid}/companions/{ref}/lore-overrides/admin-extra")
    assert deleted.status_code == 204

    actions = _access_actions(owner_engine, uid)
    assert {"override", "adjust_progress", "reset_progress"} <= set(actions)


def test_generated_stories_are_logged_and_jobs_queue(
    client: TestClient,
    owner_engine: Engine,
    user_client_factory: Callable[..., UserClient],
) -> None:
    member = user_client_factory("story.reader")
    uid = member.user_id
    secret = "The baker saved the last rye loaf for you."
    story_id = _story(owner_engine, uid, text_body=secret)

    listed = _ok(client.get(f"{ADMIN}/users/{uid}/stories"))
    assert listed[0]["id"] == story_id and "text" not in listed[0]
    assert listed[0]["source_counts"] == {"memory": 2}
    assert secret not in str(listed)
    assert _access_actions(owner_engine, uid) == []

    full = _ok(client.get(f"{ADMIN}/users/{uid}/stories/{story_id}"))
    assert full["text"] == secret
    assert _access_actions(owner_engine, uid) == ["view_full_text"]

    edited = _ok(client.patch(f"{ADMIN}/users/{uid}/stories/{story_id}", json={"status": "draft"}))
    assert edited["status"] == "draft" and edited["admin_edited_at"]

    job = _ok(client.post(f"{ADMIN}/users/{uid}/stories/{story_id}/regenerate"), 202)
    assert job["trigger"] == "regenerate" and job["status"] == "queued"
    busy = client.post(f"{ADMIN}/users/{uid}/stories", json={"companion_ref": "preset:vellum"})
    assert busy.status_code == 422
    cancelled = _ok(client.post(f"{ADMIN}/users/{uid}/jobs/{job['id']}/cancel"))
    assert cancelled["status"] == "cancelled"
    queued = _ok(
        client.post(f"{ADMIN}/users/{uid}/stories", json={"companion_ref": "preset:vellum"}), 202
    )
    assert queued["trigger"] == "admin"
    assert len(_ok(client.get(f"{ADMIN}/users/{uid}/jobs"))) == 2

    assert client.delete(f"{ADMIN}/users/{uid}/stories/{story_id}").status_code == 204
    assert client.get(f"{ADMIN}/users/{uid}/stories/{story_id}").status_code == 404
    log = _ok(client.get(f"{ADMIN}/users/{uid}/access-log"))
    assert [row["action"] for row in reversed(log)] == [
        "view_full_text",
        "edit",
        "regenerate",
        "edit",
        "generate",
        "delete",
    ]
    # The audit log is append-only: the application role cannot rewrite it.
    with rls_connection(owner_engine, user_id=1, role="root") as connection:
        connection.execute(text("SELECT set_config('app.admin_scope', 'companion', true)"))
        assert (
            connection.execute(text("SELECT count(*) FROM companion_admin_access_log")).scalar_one()
            == 6
        )
        try:
            connection.execute(text("DELETE FROM companion_admin_access_log"))
        except Exception as error:
            assert "permission denied" in str(error)
        else:
            raise AssertionError("the access log must not be deletable")


def test_admin_scope_never_reaches_the_archive(
    client: TestClient,
    owner_engine: Engine,
    root_account: UserClient,
    user_client_factory: Callable[..., UserClient],
) -> None:
    member = user_client_factory("archive.owner")
    create_memory(member.client, "A private memory about the garden.", "2026-01-01T00:00:00Z")
    _story(owner_engine, member.user_id, text_body="A story.")
    with rls_connection(owner_engine, user_id=root_account.user_id, role="root") as connection:
        connection.execute(text("SELECT set_config('app.admin_scope', 'companion', true)"))
        assert connection.execute(text("SELECT count(*) FROM memory")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM file")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM chunk")).scalar_one() == 0
        assert (
            connection.execute(text("SELECT count(*) FROM companion_generated_story")).scalar_one()
            == 1
        )
    with rls_connection(owner_engine, user_id=root_account.user_id, role="root") as connection:
        # Without the scope root sees none of another account's companion rows.
        assert (
            connection.execute(text("SELECT count(*) FROM companion_generated_story")).scalar_one()
            == 0
        )


def test_impersonated_session_has_no_admin_scope(
    client: TestClient, user_client_factory: Callable[..., UserClient]
) -> None:
    member = user_client_factory("impersonated.member")
    started = client.post(f"/api/v1/accounts/{member.user_id}/impersonate")
    assert started.status_code == 200, started.text
    assert client.get(f"{ADMIN}/presets").status_code == 403
    assert client.get(f"{ADMIN}/users/{member.user_id}/stories").status_code == 403


def test_pure_helpers() -> None:
    assert placeholders("{a} and {b} and {a}") == ["a", "b"]
    assert render_sample("Hi {companion_name} {unknown}") == "Hi Vellum {unknown}"
    assert coerce_knob("life_story_weight", "heart") == "heart"
    assert coerce_knob("self_query_phrases", [" a ", ""]) == ["a"]
    assert knob_default("story_moment_every_runs") == 3
    for bad in (
        {"key": "story_moment_every_runs", "value": 1.5},
        {"key": "life_story_enabled", "value": 1},
    ):
        try:
            coerce_knob(bad["key"], bad["value"])  # type: ignore[arg-type]
        except Exception:
            continue
        raise AssertionError(bad)
