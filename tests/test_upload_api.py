"""Multipart upload HTTP acceptance tests for Iteration 0.24."""

from src.api.upload_providers import get_object_store
from src.db.models import InterviewAttempt, User
from src.db.sqlite_client import Database
from src.repositories.stored_objects import StoredObjectDatabaseRepository
from src.storage.local import LocalObjectStore
from tests.test_api_authentication import _authenticated_app, _issue
from tests.test_api_skeleton import _request


def _upload_app(database, root):
    application = _authenticated_app(database)
    store = LocalObjectStore(root)
    application.dependency_overrides[get_object_store] = lambda: store
    return application


def _headers(token, key):
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def test_multipart_upload_replays_and_exposes_metadata_only(tmp_path):
    database = Database(tmp_path / "upload-api.db")
    token = _issue(database).token
    application = _upload_app(database, tmp_path / "objects")
    files = {"file": ("resume.pdf", b"private pdf", "application/pdf")}

    first = _request(
        application,
        "POST",
        "/api/v1/uploads/resume_source",
        headers=_headers(token, "upload-api-0001"),
        files=files,
    )
    replay = _request(
        application,
        "POST",
        "/api/v1/uploads/resume_source",
        headers=_headers(token, "upload-api-0001"),
        files=files,
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    assert replay.json()["replayed"] is True
    assert "object_key" not in first.json()
    assert "path" not in first.text.lower()
    assert "private pdf" not in first.text
    detail = _request(
        application,
        "GET",
        f"/api/v1/uploads/{first.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    assert detail.json()["sha256"] == first.json()["sha256"]
    audio = _request(
        application,
        "POST",
        "/api/v1/uploads/interview_audio",
        headers=_headers(token, "upload-audio-0001"),
        files={"file": ("answer.webm", b"mock audio", "audio/webm")},
    )
    deleted = _request(
        application,
        "DELETE",
        f"/api/v1/uploads/{audio.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    missing = _request(
        application,
        "GET",
        f"/api/v1/uploads/{audio.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.json() == {"id": audio.json()["id"], "status": "deleted"}
    assert missing.status_code == 404
    database.close()


def test_upload_api_rejects_conflict_invalid_extension_and_foreign_owner(tmp_path):
    database = Database(tmp_path / "upload-isolation.db")
    user_two = database.insert("users", User(username="bob"))
    alice = _issue(database, user_id=1, label="alice").token
    bob = _issue(database, user_id=user_two, label="bob").token
    application = _upload_app(database, tmp_path / "objects")
    headers = _headers(alice, "upload-api-0002")
    created = _request(
        application,
        "POST",
        "/api/v1/uploads/job_source",
        headers=headers,
        files={"file": ("job.png", b"image", "image/png")},
    )
    conflict = _request(
        application,
        "POST",
        "/api/v1/uploads/job_source",
        headers=headers,
        files={"file": ("job.png", b"changed", "image/png")},
    )
    invalid = _request(
        application,
        "POST",
        "/api/v1/uploads/job_source",
        headers=_headers(alice, "upload-api-0003"),
        files={"file": ("job.exe", b"binary", "application/octet-stream")},
    )
    foreign = _request(
        application,
        "GET",
        f"/api/v1/uploads/{created.json()['id']}",
        headers={"Authorization": f"Bearer {bob}"},
    )

    assert created.status_code == 201
    assert conflict.status_code == 409
    assert invalid.status_code == 422
    assert foreign.status_code == 404
    database.close()


def test_upload_openapi_declares_multipart_and_bearer_security(tmp_path):
    database = Database(tmp_path / "upload-openapi.db")
    schema = _upload_app(database, tmp_path / "objects").openapi()
    operation = schema["paths"]["/api/v1/uploads/{kind}"]["post"]
    assert "multipart/form-data" in operation["requestBody"]["content"]
    assert operation["security"] == [{"BearerAuth": []}]
    assert set(schema["paths"]["/api/v1/retained-audio"]) == {"get", "delete"}
    database.close()


def test_retained_audio_api_is_owner_scoped_and_batch_deletes_without_keys(tmp_path):
    database = Database(tmp_path / "retained-audio-api.db")
    user_two = database.insert("users", User(username="bob"))
    alice = _issue(database, user_id=1, label="alice-retained").token
    bob = _issue(database, user_id=user_two, label="bob-retained").token
    application = _upload_app(database, tmp_path / "objects")
    alice_audio = _request(
        application,
        "POST",
        "/api/v1/uploads/interview_audio",
        headers=_headers(alice, "retained-alice-01"),
        files={"file": ("alice.webm", b"alice-audio", "audio/webm")},
    ).json()
    bob_audio = _request(
        application,
        "POST",
        "/api/v1/uploads/interview_audio",
        headers=_headers(bob, "retained-bob-0001"),
        files={"file": ("bob.webm", b"bob-audio", "audio/webm")},
    ).json()
    repository = StoredObjectDatabaseRepository(database)
    alice_stored = repository.get(1, alice_audio["id"])
    bob_stored = repository.get(user_two, bob_audio["id"])
    database.insert(
        "interview_attempts",
        InterviewAttempt(audio_path=alice_stored["object_key"], answer_text="alice"),
    )
    database.insert(
        "interview_attempts",
        InterviewAttempt(audio_path=bob_stored["object_key"], answer_text="bob"),
    )

    listed = _request(
        application,
        "GET",
        "/api/v1/retained-audio",
        headers={"Authorization": f"Bearer {alice}"},
    )
    deleted = _request(
        application,
        "DELETE",
        "/api/v1/retained-audio",
        headers={"Authorization": f"Bearer {alice}"},
        json={"object_ids": [alice_audio["id"], bob_audio["id"]]},
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [alice_audio["id"]]
    assert "object_key" not in listed.text
    assert "sha256" not in listed.text
    assert deleted.json() == {"requested": 2, "deleted": 1, "already_absent": 1}
    assert repository.get(1, alice_audio["id"]) is None
    assert repository.get(user_two, bob_audio["id"]) is not None
    database.close()
