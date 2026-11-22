"""Authentication acceptance tests for Iteration 0.21."""

import json
from datetime import timedelta

from src.api.app import create_app
from src.api.providers import get_database
from src.db.sqlite_client import Database
from src.repositories.sqlite_auth import SQLiteAuthRepository
from src.services.authentication import AuthenticationService, hash_token
from tests.test_api_skeleton import _request


def _authenticated_app(database: Database):
    application = create_app()

    async def override_database():
        yield database

    application.dependency_overrides[get_database] = override_database
    return application


def _issue(database: Database, *, user_id: int = 1, label: str = "test"):
    service = AuthenticationService(SQLiteAuthRepository(database))
    issued = service.issue_token(user_id=user_id, label=label)
    assert issued is not None
    return issued


def test_token_is_stored_as_hash_and_authenticated_context_cannot_be_overridden(tmp_path):
    database = Database(tmp_path / "auth.db")
    database.update(
        "users",
        1,
        {"username": "alice", "settings_json": json.dumps({"roles": ["member"]})},
    )
    issued = _issue(database)

    stored = database.find_by("api_tokens", "user_id", 1)[0]
    assert stored["token_hash"] == hash_token(issued.token)
    assert issued.token not in json.dumps(stored)

    response = _request(
        _authenticated_app(database),
        "GET",
        "/api/v1/me?user_id=999",
        headers={"Authorization": f"Bearer {issued.token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"id": 1, "username": "alice", "roles": ["member"]}
    assert database.find_by("api_tokens", "user_id", 1)[0]["last_used_at"]
    database.close()


def test_missing_and_invalid_credentials_return_the_same_safe_401(tmp_path):
    database = Database(tmp_path / "unauthorized.db")
    application = _authenticated_app(database)

    missing = _request(application, "GET", "/api/v1/me")
    invalid = _request(
        application,
        "GET",
        "/api/v1/me",
        headers={"Authorization": "Bearer invalid-short-token"},
    )

    for response in (missing, invalid):
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == "authentication_required"
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert "token" not in response.text.lower()
    database.close()


def test_expired_revoked_and_inactive_tokens_are_rejected(tmp_path):
    database = Database(tmp_path / "token_state.db")
    application = _authenticated_app(database)

    expired = _issue(database, label="expired")
    revoked = _issue(database, label="revoked")
    inactive = _issue(database, label="inactive")
    rows = {row["label"]: row for row in database.find_by("api_tokens", "user_id", 1)}
    database.update("api_tokens", rows["expired"]["id"], {"expires_at": "2000-01-01T00:00:00+00:00"})
    service = AuthenticationService(SQLiteAuthRepository(database))
    assert service.revoke_token(user_id=1, token_id=rows["revoked"]["id"])
    assert not service.revoke_token(user_id=999, token_id=rows["inactive"]["id"])

    expired_response = _request(
        application,
        "GET",
        "/api/v1/me",
        headers={"Authorization": f"Bearer {expired.token}"},
    )
    revoked_response = _request(
        application,
        "GET",
        "/api/v1/me",
        headers={"Authorization": f"Bearer {revoked.token}"},
    )
    database.update("users", 1, {"is_active": 0})
    inactive_response = _request(
        application,
        "GET",
        "/api/v1/me",
        headers={"Authorization": f"Bearer {inactive.token}"},
    )

    assert [response.status_code for response in (
        expired_response,
        revoked_response,
        inactive_response,
    )] == [401, 401, 401]
    database.close()


def test_token_issuer_rejects_unknown_or_non_positive_lifetime(tmp_path):
    database = Database(tmp_path / "issuer.db")
    service = AuthenticationService(SQLiteAuthRepository(database))

    assert service.issue_token(user_id=999) is None
    try:
        service.issue_token(user_id=1, lifetime=timedelta(0))
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("Expected a non-positive lifetime to be rejected")
    database.close()


def test_openapi_declares_bearer_auth_only_for_protected_identity_route():
    response = _request(create_app(), "GET", "/openapi.json")
    document = response.json()

    assert document["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert document["paths"]["/api/v1/me"]["get"]["security"] == [
        {"BearerAuth": []}
    ]
    assert "security" not in document["paths"]["/health/live"]["get"]
