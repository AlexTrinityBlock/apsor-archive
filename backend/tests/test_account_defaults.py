"""New accounts inherit the deployment's primary chat endpoint."""

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text


def _insert_chat_endpoint(engine: Engine, *, model: str) -> int:
    """Insert an active primary chat row as root (the table is forced-RLS)."""
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.user_role', 'root', true)")
        )
        row = connection.execute(
            text(
                "INSERT INTO chat_provider_config ("
                "provider, label, model, base_url, is_active, priority"
                ") VALUES ("
                "'deepseek', 'Deployment default', :model, "
                "'https://api.deepseek.com', true, 0"
                ") RETURNING id"
            ),
            {"model": model},
        ).one()
    return int(row.id)


def _assignment(
    engine: Engine, user_id: int
) -> tuple[int | None, str | None, int | None, str | None, str]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT chat_provider_config_id, chat_model, "
                "aux_provider_config_id, aux_model, aux_reasoning_effort "
                "FROM app_user WHERE id = :user_id"
            ),
            {"user_id": user_id},
        ).one()
    return (
        row.chat_provider_config_id,
        row.chat_model,
        row.aux_provider_config_id,
        row.aux_model,
        row.aux_reasoning_effort,
    )


def test_new_account_inherits_the_primary_endpoint(
    client: TestClient, owner_engine: Engine
) -> None:
    endpoint_id = _insert_chat_endpoint(owner_engine, model="deepseek-v4-pro")

    response = client.post(
        "/api/v1/accounts",
        json={"username": "newmate", "display_name": "New Mate"},
    )
    assert response.status_code == 201, response.text
    user_id = int(response.json()["user"]["user_id"])

    (
        endpoint,
        model,
        aux_endpoint,
        aux_model,
        aux_effort,
    ) = _assignment(owner_engine, user_id)
    assert endpoint == endpoint_id
    assert model == "deepseek-v4-pro"
    # The auxiliary slot stays NULL so it keeps inheriting the primary row with
    # the cheap default effort; the assignment API makes it explicit later.
    assert aux_endpoint is None
    assert aux_model is None
    assert aux_effort == "low"


def test_new_account_stays_unassigned_without_an_endpoint(
    client: TestClient, owner_engine: Engine
) -> None:
    response = client.post(
        "/api/v1/accounts",
        json={"username": "lonely", "display_name": "Lonely"},
    )
    assert response.status_code == 201, response.text
    user_id = int(response.json()["user"]["user_id"])

    (
        endpoint,
        model,
        aux_endpoint,
        aux_model,
        aux_effort,
    ) = _assignment(owner_engine, user_id)
    assert endpoint is None
    assert model is None
    assert aux_endpoint is None
    assert aux_model is None
    assert aux_effort == "low"
