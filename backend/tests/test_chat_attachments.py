"""Temporary chat image upload, provider visibility, management, and isolation."""

import asyncio
from collections.abc import Callable
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine, text

from app.infrastructure.database.session import Database
from app.module.agent.domain.agent_config_domain import AgentRuntimeConfig
from app.module.agent.service.chat_attachment_cleanup import ChatAttachmentCleanup
from app.module.agent.test.fake_chat_generator import FakeChatGenerator
from tests.conftest import TEST_DATABASE_URL, UserClient


def png_bytes(size: tuple[int, int] = (8, 8)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (180, 40, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def upload_image(
    client: TestClient,
    name: str = "pasted.png",
    *,
    client_token: str | None = None,
) -> dict[str, Any]:
    data = {"client_token": client_token} if client_token is not None else None
    response = client.post(
        "/api/v1/agent/attachments",
        files={"file": (name, png_bytes(), "image/png")},
        data=data,
    )
    assert response.status_code == 201, response.text
    return response.json()


def cancel_upload(client: TestClient, client_token: str) -> Any:
    return client.post(
        "/api/v1/agent/attachments/cancel",
        json={"client_token": client_token},
    )


def create_conversation(client: TestClient) -> int:
    response = client.post(
        "/api/v1/agent/conversations",
        json={"title": "Image chat"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def send_message(
    client: TestClient,
    conversation_id: int,
    *,
    content: str,
    attachment_ids: list[int] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": content}
    if attachment_ids is not None:
        payload["attachment_ids"] = attachment_ids
    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json=payload,
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_list_content_and_delete(client: TestClient) -> None:
    uploaded = upload_image(client)
    attachment_id = int(uploaded["id"])
    assert uploaded["status"] == "staged"
    assert uploaded["mime_type"] == "image/png"
    assert int(uploaded["width"]) == 8
    assert int(uploaded["height"]) == 8
    assert uploaded["content_url"] == f"/api/v1/agent/attachments/{attachment_id}/content"

    listed = client.get("/api/v1/agent/attachments", params={"status": "staged"})
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total_results"] == 1
    assert body["resources"][0]["id"] == attachment_id

    content = client.get(f"/api/v1/agent/attachments/{attachment_id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"
    assert content.headers["x-content-type-options"] == "nosniff"
    assert content.headers["cache-control"] == "private, no-store"
    assert content.headers["cross-origin-resource-policy"] == "same-origin"
    assert content.content.startswith(b"\x89PNG")

    deleted = client.delete(f"/api/v1/agent/attachments/{attachment_id}")
    assert deleted.status_code == 204
    assert (
        client.get(f"/api/v1/agent/attachments/{attachment_id}/content").status_code
        == 404
    )
    assert client.get("/api/v1/agent/attachments").json()["total_results"] == 0


def test_upload_client_token_makes_a_retry_idempotent(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    token = "client-token-retry-0001"
    first = upload_image(client, client_token=token)
    second = upload_image(client, client_token=token)
    assert second["id"] == first["id"]
    assert client.get("/api/v1/agent/attachments").json()["total_results"] == 1

    with owner_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT client_token FROM agent_chat_attachment "
                "WHERE client_token = :token"
            ),
            {"token": token},
        ).scalars().all()
    assert rows == [token]


def test_cancel_staged_upload_is_idempotent(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    token = "client-token-cancel-0001"
    uploaded = upload_image(client, client_token=token)
    attachment_id = int(uploaded["id"])
    with owner_engine.connect() as connection:
        storage_key = connection.execute(
            text("SELECT storage_key FROM agent_chat_attachment WHERE id = :id"),
            {"id": attachment_id},
        ).scalar_one()

    first = cancel_upload(client, token)
    assert first.status_code == 204, first.text
    second = cancel_upload(client, token)
    assert second.status_code == 204, second.text

    assert client.get("/api/v1/agent/attachments").json()["total_results"] == 0
    assert (
        client.get(f"/api/v1/agent/attachments/{attachment_id}/content").status_code
        == 404
    )
    with pytest.raises(FileNotFoundError):
        asyncio.run(client.app.state.storage.read(storage_key))
    with owner_engine.connect() as connection:
        deleted = connection.execute(
            text(
                "SELECT deleted_at IS NOT NULL FROM agent_chat_attachment "
                "WHERE id = :id"
            ),
            {"id": attachment_id},
        ).scalar_one()
    assert deleted is True


def test_cancel_does_not_delete_a_sent_image(client: TestClient) -> None:
    fake = FakeChatGenerator.from_texts("The image is attached.")
    client.app.state.agent_chat_generator = fake
    token = "client-token-attached-0001"
    uploaded = upload_image(client, client_token=token)
    attachment_id = int(uploaded["id"])
    conversation_id = create_conversation(client)
    send_message(
        client,
        conversation_id,
        content="Keep this image.",
        attachment_ids=[attachment_id],
    )

    cancelled = cancel_upload(client, token)
    assert cancelled.status_code == 204, cancelled.text
    assert (
        client.get(f"/api/v1/agent/attachments/{attachment_id}/content").status_code
        == 200
    )
    listed = client.get("/api/v1/agent/attachments", params={"status": "attached"})
    assert listed.json()["total_results"] == 1


def test_cancel_is_scoped_to_the_owner(
    user_client_factory: Callable[..., UserClient],
) -> None:
    alice = user_client_factory("alice")
    bob = user_client_factory("bob")
    token = "client-token-owner-0001"
    uploaded = upload_image(alice.client, client_token=token)
    attachment_id = int(uploaded["id"])

    assert cancel_upload(bob.client, token).status_code == 204
    assert (
        alice.client.get(
            f"/api/v1/agent/attachments/{attachment_id}/content"
        ).status_code
        == 200
    )


def test_cancel_rejects_an_invalid_client_token(client: TestClient) -> None:
    response = cancel_upload(client, "too-short")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_multiple_uploads_can_be_cancelled_independently(
    client: TestClient,
) -> None:
    tokens = [f"client-token-multi-{index:04d}" for index in range(3)]
    uploaded = [
        upload_image(client, name=f"image-{index}.png", client_token=token)
        for index, token in enumerate(tokens)
    ]
    assert client.get("/api/v1/agent/attachments").json()["total_results"] == 3

    assert cancel_upload(client, tokens[1]).status_code == 204
    remaining = client.get("/api/v1/agent/attachments").json()
    assert remaining["total_results"] == 2
    assert {int(item["id"]) for item in remaining["resources"]} == {
        int(uploaded[0]["id"]),
        int(uploaded[2]["id"]),
    }


def test_image_is_visible_to_the_provider_and_linked_to_the_user_entry(
    client: TestClient,
) -> None:
    fake = FakeChatGenerator.from_texts("The screenshot shows a red square.")
    client.app.state.agent_chat_generator = fake
    attachment = upload_image(client)
    attachment_id = int(attachment["id"])
    conversation_id = create_conversation(client)

    turn = send_message(
        client,
        conversation_id,
        content="What is in this image?",
        attachment_ids=[attachment_id],
    )
    assert turn["answer"] == "The screenshot shows a red square."

    user_entry = turn["user_entry"]
    assert user_entry["data"]["attachments"][0]["id"] == attachment_id
    assert user_entry["data"]["attachments"][0]["file_name"] == "pasted.png"

    assert len(fake.requests) == 1
    user_messages = [
        message
        for message in fake.requests[0].messages
        if message.get("role") == "user"
    ]
    content = user_messages[-1]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert "What is in this image?" in content[0]["text"]
    image_part = next(part for part in content if part["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")

    listed = client.get("/api/v1/agent/attachments", params={"status": "attached"})
    assert listed.status_code == 200
    assert listed.json()["resources"][0]["entry_id"] == user_entry["id"]

    # A sent attachment is no longer staged and cannot be attached again.
    second = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={
            "content": "Use the same image again.",
            "attachment_ids": [attachment_id],
        },
        headers={"Accept": "application/json"},
    )
    assert second.status_code == 422
    assert second.json()["error"] == "agent_chat_attachment_invalid"


def test_sending_promotes_the_image_to_the_durable_prefix(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    fake = FakeChatGenerator.from_texts("Promoted.")
    client.app.state.agent_chat_generator = fake
    attachment = upload_image(client)
    attachment_id = int(attachment["id"])
    with owner_engine.connect() as connection:
        before = connection.execute(
            text(
                "SELECT user_id, storage_key FROM agent_chat_attachment WHERE id = :id"
            ),
            {"id": attachment_id},
        ).mappings().one()
    assert before["storage_key"].startswith(f"users/{before['user_id']}/chat-temp/")

    conversation_id = create_conversation(client)
    send_message(
        client,
        conversation_id,
        content="Promote this image.",
        attachment_ids=[attachment_id],
    )

    with owner_engine.connect() as connection:
        after = connection.execute(
            text("SELECT storage_key FROM agent_chat_attachment WHERE id = :id"),
            {"id": attachment_id},
        ).scalar_one()
    assert after.startswith(f"users/{before['user_id']}/chat-images/")
    assert after != before["storage_key"]
    with pytest.raises(FileNotFoundError):
        asyncio.run(client.app.state.storage.read(before["storage_key"]))
    assert (
        client.get(f"/api/v1/agent/attachments/{attachment_id}/content").status_code
        == 200
    )


def test_image_only_message_is_allowed(client: TestClient) -> None:
    fake = FakeChatGenerator.from_texts("It is a red square.")
    client.app.state.agent_chat_generator = fake
    attachment = upload_image(client)
    conversation_id = create_conversation(client)

    turn = send_message(
        client,
        conversation_id,
        content="",
        attachment_ids=[int(attachment["id"])],
    )
    assert turn["answer"] == "It is a red square."
    assert turn["user_entry"]["model"][0]["content"] == ""


def test_deleted_image_becomes_an_explicit_provider_note(client: TestClient) -> None:
    fake = FakeChatGenerator.from_texts("First answer.", "Second answer.")
    client.app.state.agent_chat_generator = fake
    attachment = upload_image(client)
    attachment_id = int(attachment["id"])
    conversation_id = create_conversation(client)
    send_message(
        client,
        conversation_id,
        content="Look at this.",
        attachment_ids=[attachment_id],
    )

    assert client.delete(f"/api/v1/agent/attachments/{attachment_id}").status_code == 204
    send_message(client, conversation_id, content="What did the image show?")

    user_messages = [
        message
        for message in fake.requests[1].messages
        if message.get("role") == "user"
    ]
    content = user_messages[0]["content"]
    assert isinstance(content, list)
    assert any(
        part.get("type") == "text"
        and "could not be loaded from temporary storage" in part.get("text", "")
        for part in content
    )


def test_forked_transcript_keeps_provider_image_parts(client: TestClient) -> None:
    fake = FakeChatGenerator.from_texts("First answer.", "Fork answer.")
    client.app.state.agent_chat_generator = fake
    attachment = upload_image(client)
    conversation_id = create_conversation(client)
    send_message(
        client,
        conversation_id,
        content="Look at this.",
        attachment_ids=[int(attachment["id"])],
    )

    forked = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/fork",
        json={},
    )
    assert forked.status_code == 201, forked.text
    fork_id = int(forked.json()["id"])
    send_message(client, fork_id, content="Does the copy still see it?")

    user_messages = [
        message
        for message in fake.requests[1].messages
        if message.get("role") == "user"
    ]
    assert any(
        isinstance(message.get("content"), list)
        and any(part.get("type") == "image_url" for part in message["content"])
        for message in user_messages
    )


def test_empty_message_and_too_many_images_are_rejected(client: TestClient) -> None:
    client.app.state.agent_chat_generator = FakeChatGenerator([])
    conversation_id = create_conversation(client)
    empty = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "   "},
        headers={"Accept": "application/json"},
    )
    assert empty.status_code == 422
    assert empty.json()["error"] == "agent_invalid_entry"

    attachment_ids = [int(upload_image(client)["id"]) for _ in range(5)]
    too_many = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Too many", "attachment_ids": attachment_ids},
        headers={"Accept": "application/json"},
    )
    assert too_many.status_code == 422
    assert too_many.json()["error"] == "agent_chat_attachment_limit"


def test_non_image_payload_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agent/attachments",
        files={"file": ("not-an-image.png", b"not an image", "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "agent_chat_attachment_unsupported"


def test_temporary_images_are_isolated_between_accounts(
    user_client_factory: Callable[..., UserClient],
    owner_engine: Engine,
) -> None:
    alice = user_client_factory("alice")
    bob = user_client_factory("bob")
    attachment = upload_image(alice.client)
    attachment_id = int(attachment["id"])

    with owner_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT user_id, storage_key FROM agent_chat_attachment "
                "WHERE id = :attachment_id"
            ),
            {"attachment_id": attachment_id},
        ).mappings().one()
    assert int(row["user_id"]) == alice.user_id
    assert row["storage_key"].startswith(f"users/{alice.user_id}/chat-temp/")

    assert bob.client.get("/api/v1/agent/attachments").json()["total_results"] == 0
    assert (
        bob.client.get(f"/api/v1/agent/attachments/{attachment_id}/content").status_code
        == 404
    )
    assert (
        bob.client.delete(f"/api/v1/agent/attachments/{attachment_id}").status_code
        == 404
    )
    assert alice.client.get(
        f"/api/v1/agent/attachments/{attachment_id}/content"
    ).status_code == 200


def test_cleanup_removes_only_expired_staged_images(
    client: TestClient,
    owner_engine: Engine,
) -> None:
    fake = FakeChatGenerator.from_texts("The attached image is durable.")
    client.app.state.agent_chat_generator = fake
    staged = upload_image(client)
    attached = upload_image(client)
    conversation_id = create_conversation(client)
    send_message(
        client,
        conversation_id,
        content="Keep this one forever.",
        attachment_ids=[int(attached["id"])],
    )
    fresh = upload_image(client)

    staged_id = int(staged["id"])
    attached_id = int(attached["id"])
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE agent_chat_attachment "
                "SET created_at = now() - interval '2 days' "
                "WHERE id IN (:staged_id, :attached_id)"
            ),
            {"staged_id": staged_id, "attached_id": attached_id},
        )
        staged_key = connection.execute(
            text("SELECT storage_key FROM agent_chat_attachment WHERE id = :id"),
            {"id": staged_id},
        ).scalar_one()

    config = AgentRuntimeConfig(
        chat_attachment_staged_ttl_hours=1,
        chat_attachment_cleanup_interval_seconds=900,
    )

    async def run_cleanup() -> int:
        database = Database(TEST_DATABASE_URL)
        try:
            cleanup = ChatAttachmentCleanup(
                database=database,
                storage=client.app.state.storage,
                config_provider=lambda: asyncio.sleep(0, result=config),
            )
            return await cleanup.run_once(config)
        finally:
            await database.dispose()

    assert asyncio.run(run_cleanup()) == 1
    assert client.get("/api/v1/agent/attachments").json()["total_results"] == 2
    assert (
        client.get(f"/api/v1/agent/attachments/{staged_id}/content").status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/agent/attachments/{attached_id}/content").status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/agent/attachments/{fresh['id']}/content").status_code
        == 200
    )
    with pytest.raises(FileNotFoundError):
        asyncio.run(client.app.state.storage.read(staged_key))

    with owner_engine.connect() as connection:
        staged_deleted = connection.execute(
            text(
                "SELECT deleted_at IS NOT NULL FROM agent_chat_attachment WHERE id = :id"
            ),
            {"id": staged_id},
        ).scalar_one()
        attached_deleted = connection.execute(
            text(
                "SELECT deleted_at IS NOT NULL FROM agent_chat_attachment WHERE id = :id"
            ),
            {"id": attached_id},
        ).scalar_one()
    assert staged_deleted is True
    assert attached_deleted is False
