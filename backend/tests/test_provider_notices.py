"""Persistent provider-error notices: dedupe, sanitization, and root API."""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.module.knowledge.protocol.provider_notice_protocol import (
    ProviderAttempt,
    ProviderFailureEvent,
)
from app.module.knowledge.service.provider_error_notice_service import (
    ProviderErrorNoticeService,
)
from tests.conftest import UserClient


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _event(
    *,
    detail: str = "The provider failed: HTTP 503",
    error_code: str = "http_503",
    attempts: tuple[ProviderAttempt, ...] | None = None,
) -> ProviderFailureEvent:
    return ProviderFailureEvent(
        capability="chat",
        operation="chat",
        error_code=error_code,
        status_code=503,
        detail=detail,
        attempts=attempts
        or (
            ProviderAttempt(
                provider="deepseek",
                status_code=503,
                error_code="http_503",
                detail="upstream unavailable",
            ),
            ProviderAttempt(
                provider="openai-compatible",
                status_code=429,
                error_code="rate_limit",
                detail="slow down",
            ),
        ),
    )


def _service(
    client: TestClient,
    *,
    clock: _Clock | None = None,
) -> ProviderErrorNoticeService:
    return ProviderErrorNoticeService(
        client.app.state.db.session_factory,
        dedupe_window=timedelta(minutes=15),
        now=clock or _Clock(),
    )


def _run[T](client: TestClient, factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Run one coroutine on the TestClient's event-loop portal."""

    async def run() -> T:
        return await factory()

    assert client.portal is not None
    return client.portal.call(run)


def _notices(
    client: TestClient,
    service: ProviderErrorNoticeService,
) -> list[Any]:
    listing = _run(client, service.list_notices)
    return list(listing.notices)


def test_report_inserts_and_deduplicates_inside_the_window(client: TestClient) -> None:
    clock = _Clock()
    service = _service(client, clock=clock)
    client.portal.call(service.report, _event())
    client.portal.call(service.report, _event())

    notices = _notices(client, service)
    assert len(notices) == 1
    notice = notices[0]
    assert notice.count == 2
    assert notice.last_seen_at == clock.now
    assert [attempt.provider for attempt in notice.attempts] == [
        "deepseek",
        "openai-compatible",
    ]
    assert notice.attempts[1].status_code == 429
    assert notice.attempts[1].error_code == "rate_limit"

    # Outside the 15-minute dedupe window the same fingerprint starts a new
    # unresolved notice; the older row is not silently overwritten.
    clock.now += timedelta(minutes=16)
    client.portal.call(service.report, _event())
    notices = _notices(client, service)
    assert len(notices) == 2
    assert sorted(notice.count for notice in notices) == [1, 2]


def test_report_sanitizes_credentials_and_control_characters(
    client: TestClient,
) -> None:
    service = _service(client)
    long_detail = "provider detail " * 300
    event = _event(
        detail=(
            "Authorization: Bearer sk-live-supersecret123456\u0000\n"
            "https://user:password@example.com/private "
            "api_key=tvly-also-secret123456 " + long_detail
        ),
        attempts=(
            ProviderAttempt(
                provider="deepseek",
                status_code=401,
                error_code="authorization_error",
                detail="Bearer sk-attempt-secret123456 " + long_detail,
            ),
        ),
    )
    client.portal.call(service.report, event)
    notice = _notices(client, service)[0]

    assert "sk-live-supersecret" not in notice.detail
    assert "tvly-also-secret" not in notice.detail
    assert "user:password" not in notice.detail
    assert "\u0000" not in notice.detail
    assert "[redacted]" in notice.detail
    assert len(notice.detail) <= 2_000
    assert len(notice.attempts[0].detail) <= 400
    assert "sk-attempt-secret" not in notice.attempts[0].detail


def test_root_list_resolve_and_resolve_all(
    client: TestClient,
    root_account: UserClient,
    user_client_factory: Any,
) -> None:
    service = _service(client)
    client.portal.call(service.report, _event(error_code="http_503"))
    client.portal.call(service.report, _event(error_code="network_error"))

    listing = client.get("/api/v1/system/provider-notices")
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["open_count"] == 2
    assert len(body["notices"]) == 2
    notice_id = body["notices"][0]["id"]
    assert body["notices"][0]["attempts"]
    assert body["notices"][0]["capability"] == "chat"

    normal_user = user_client_factory("notice-reader")
    forbidden = normal_user.client.get("/api/v1/system/provider-notices")
    assert forbidden.status_code == 403, forbidden.text
    forbidden_resolve = normal_user.client.post(
        f"/api/v1/system/provider-notices/{notice_id}/resolve"
    )
    assert forbidden_resolve.status_code == 403, forbidden_resolve.text
    forbidden_all = normal_user.client.post(
        "/api/v1/system/provider-notices/resolve-all"
    )
    assert forbidden_all.status_code == 403, forbidden_all.text

    resolved = client.post(
        f"/api/v1/system/provider-notices/{notice_id}/resolve"
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolved_at"] is not None
    assert resolved.json()["resolved_by_user_id"] == root_account.user_id

    open_listing = client.get("/api/v1/system/provider-notices")
    assert open_listing.json()["open_count"] == 1

    resolved_all = client.post("/api/v1/system/provider-notices/resolve-all")
    assert resolved_all.status_code == 200, resolved_all.text
    assert resolved_all.json()["open_count"] == 0
    assert resolved_all.json()["notices"] == []

    all_listing = client.get(
        "/api/v1/system/provider-notices",
        params={"status": "all"},
    )
    assert all_listing.status_code == 200, all_listing.text
    assert len(all_listing.json()["notices"]) == 2
    assert all(
        notice["resolved_at"] is not None
        for notice in all_listing.json()["notices"]
    )

    missing = client.post("/api/v1/system/provider-notices/999/resolve")
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"] == "provider_notice_not_found"
