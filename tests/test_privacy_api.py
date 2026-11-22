"""Data export and controlled deletion acceptance tests for Iteration 0.25."""

import hashlib
import io
import json
import zipfile

from src.api.upload_providers import get_object_store
from src.db.models import (
    ApplicationEvent,
    EvidenceMatch,
    EvidenceReview,
    EvidenceSupplement,
    EvidenceSupplementEvent,
    InterviewFollowUp,
    JobRequirement,
    LatexChange,
    OperationJob,
    Suggestion,
    User,
)
from src.db.sqlite_client import Database
from src.repositories.stored_objects import StoredObjectDatabaseRepository
from src.services.context import RequestContext
from src.services.uploads import UploadApplicationService
from src.services.privacy import ObjectCleanupRunner
from src.repositories.privacy import DatabasePrivacyRepository
from src.storage.contracts import ObjectStorageError
from src.storage.local import LocalObjectStore
from tests.test_api_authentication import _authenticated_app, _issue
from tests.test_api_skeleton import _request
from tests.test_read_api import _seed_chain


def _privacy_app(database, store):
    application = _authenticated_app(database)
    application.dependency_overrides[get_object_store] = lambda: store
    return application


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _upload(database, store, user_id, suffix):
    service = UploadApplicationService(
        RequestContext(
            request_id=f"req_{suffix}",
            user_id=user_id,
            username=suffix,
        ),
        store,
        StoredObjectDatabaseRepository(database),
    )
    return service.upload(
        kind="resume_source",
        filename=f"resume-{suffix}.pdf",
        content_type="application/pdf",
        stream=io.BytesIO(f"private binary {suffix}".encode()),
        idempotency_key=f"privacy-upload-{suffix}",
    )


def _seed_full_graph(database, user_id, suffix):
    chain = _seed_chain(database, user_id, suffix)
    requirement = database.insert(
        "job_requirements",
        JobRequirement(
            jd_id=chain["job"],
            text="Python",
            normalized_key=f"python-{suffix}",
        ),
    )
    evidence = database.insert(
        "evidence_matches",
        EvidenceMatch(
            match_id=chain["match"],
            requirement_id=requirement,
            evidence_json=[{"quote": suffix}],
        ),
    )
    database.insert(
        "evidence_reviews",
        EvidenceReview(
            evidence_match_id=evidence,
            match_id=chain["match"],
            requirement_id=requirement,
            action="confirmed",
        ),
    )
    supplement = database.insert(
        "evidence_supplements",
        EvidenceSupplement(
            match_id=chain["match"],
            requirement_id=requirement,
            evidence_match_id=evidence,
            title="Extra evidence",
            description=suffix,
        ),
    )
    database.insert(
        "evidence_supplement_events",
        EvidenceSupplementEvent(
            supplement_id=supplement,
            event_type="created",
            snapshot_json={"suffix": suffix},
        ),
    )
    suggestion = database.insert(
        "suggestions",
        Suggestion(match_id=chain["match"], suggested_text=suffix),
    )
    database.insert(
        "application_events",
        ApplicationEvent(
            application_id=chain["application"],
            event_type="test",
            title="Test event",
            occurred_at="2026-11-20T00:00:00+00:00",
        ),
    )
    attempt = database.fetch_one(
        "SELECT id FROM interview_attempts WHERE application_id = ?",
        (chain["application"],),
    )["id"]
    database.insert(
        "interview_follow_ups",
        InterviewFollowUp(
            parent_attempt_id=attempt,
            question_id=chain["question"],
            target_dimension="technical",
            rationale=suffix,
        ),
    )
    database.insert(
        "latex_changes",
        LatexChange(
            resume_id=chain["resume"],
            suggestion_id=suggestion,
            file_path=f"C:/private/{suffix}/resume.tex",
            commit_hash=f"commit-{suffix}",
        ),
    )
    operation = database.insert(
        "operation_jobs",
        OperationJob(
            user_id=user_id,
            operation_type="privacy_test",
            idempotency_key=f"operation-{suffix}",
            request_hash=f"hash-{suffix}",
            status="succeeded",
            created_at="2026-11-20T00:00:00+00:00",
            updated_at="2026-11-20T00:00:00+00:00",
        ),
    )
    database.execute(
        """
        INSERT INTO operation_payloads (operation_id, user_id, payload_json, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (operation, user_id, json.dumps({"private": suffix}), "2026-11-20"),
    )
    return chain


def _clear_legacy_paths(database, chain):
    database.update(
        "resumes",
        chain["resume"],
        {"latex_path": "", "pdf_path": ""},
    )
    database.update("job_descriptions", chain["job"], {"source_file": ""})


def test_export_zip_contains_owned_data_and_binary_without_server_secrets(tmp_path):
    database = Database(tmp_path / "export.db")
    database.update("users", 1, {"username": "alice"})
    _seed_full_graph(database, 1, "alice")
    store = LocalObjectStore(tmp_path / "objects")
    uploaded = _upload(database, store, 1, "alice")
    token = _issue(database).token

    response = _request(
        _privacy_app(database, store),
        "GET",
        "/api/v1/me/export",
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        data = json.loads(archive.read("data.json"))
        manifest = json.loads(archive.read("manifest.json"))
        object_name = next(name for name in names if name.startswith("objects/"))
        assert archive.read(object_name) == b"private binary alice"
    encoded = json.dumps(data)
    assert data["user"]["username"] == "alice"
    assert data["operation_payloads"][0]["payload"] == {"private": "alice"}
    assert {warning["code"] for warning in manifest["warnings"]} == {
        "legacy_local_file_not_exported"
    }
    assert manifest["counts"]["stored_objects"] == 1
    assert str(uploaded["id"]) in object_name
    assert "C:/private" not in encoded
    assert "idempotency_key" not in encoded
    assert "request_hash" not in encoded
    assert "token_hash" not in encoded
    assert database.count("privacy_audit_events") == 1
    database.close()


def test_export_is_user_scoped(tmp_path):
    database = Database(tmp_path / "export-isolation.db")
    database.update("users", 1, {"username": "alice"})
    bob_id = database.insert("users", User(username="bob"))
    _seed_chain(database, 1, "alice")
    _seed_chain(database, bob_id, "bob-secret")
    store = LocalObjectStore(tmp_path / "objects")
    token = _issue(database, user_id=1).token
    response = _request(
        _privacy_app(database, store),
        "GET",
        "/api/v1/me/export",
        headers=_auth(token),
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        data = archive.read("data.json").decode()
    assert "alice" in data
    assert "bob-secret" not in data
    database.close()


def test_deletion_requires_one_time_token_username_and_exact_phrase(tmp_path):
    database = Database(tmp_path / "delete-confirmation.db")
    database.update("users", 1, {"username": "alice"})
    _seed_chain(database, 1, "alice")
    store = LocalObjectStore(tmp_path / "objects")
    token = _issue(database).token
    app = _privacy_app(database, store)
    challenge = _request(
        app,
        "POST",
        "/api/v1/me/deletion-challenge",
        headers=_auth(token),
    )
    challenge_row = database.list("privacy_deletion_challenges", limit=1)[0]
    assert challenge.status_code == 200
    assert challenge.headers["cache-control"] == "no-store"
    assert challenge_row["token_hash"] == hashlib.sha256(
        challenge.json()["deletion_token"].encode()
    ).hexdigest()
    assert challenge.json()["deletion_token"] not in json.dumps(challenge_row)

    wrong = _request(
        app,
        "DELETE",
        "/api/v1/me",
        headers={**_auth(token), "Deletion-Token": challenge.json()["deletion_token"]},
        json={"username": "alice", "confirmation": "delete"},
    )
    assert wrong.status_code == 422
    assert database.get("users", 1) is not None
    assert database.count("resumes") == 1
    database.close()


def test_account_deletion_cascades_owned_graph_keeps_audit_and_other_user(tmp_path):
    database = Database(tmp_path / "delete.db")
    database.update("users", 1, {"username": "alice"})
    bob_id = database.insert("users", User(username="bob"))
    alice = _seed_full_graph(database, 1, "alice")
    bob = _seed_full_graph(database, bob_id, "bob")
    _clear_legacy_paths(database, alice)
    store = LocalObjectStore(tmp_path / "objects")
    uploaded = _upload(database, store, 1, "alice")
    token = _issue(database).token
    app = _privacy_app(database, store)
    challenge = _request(
        app,
        "POST",
        "/api/v1/me/deletion-challenge",
        headers=_auth(token),
    ).json()

    deleted = _request(
        app,
        "DELETE",
        "/api/v1/me",
        headers={**_auth(token), "Deletion-Token": challenge["deletion_token"]},
        json={"username": "alice", "confirmation": "DELETE MY DATA"},
    )

    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert deleted.json()["object_cleanup_pending"] == 0
    assert database.get("users", 1) is None
    assert database.get("users", bob_id)["username"] == "bob"
    assert database.get("applications", bob["application"]) is not None
    assert database.fetch_one("SELECT * FROM api_tokens WHERE user_id = 1") is None
    assert database.fetch_one("SELECT * FROM operation_jobs WHERE user_id = 1") is None
    assert database.fetch_one("SELECT * FROM stored_objects WHERE user_id = 1") is None
    assert not store.exists(uploaded["object_key"])
    assert database.count("object_cleanup_jobs") == 0
    audit = database.list("privacy_audit_events", limit=1)[0]
    assert audit["event_type"] == "account_deleted"
    assert audit["status"] == "completed"
    assert "alice" not in json.dumps(audit)
    assert "user_id" not in json.dumps(audit)
    after = _request(app, "GET", "/api/v1/me", headers=_auth(token))
    assert after.status_code == 401
    database.close()


def test_existing_legacy_local_file_blocks_deletion_until_migrated(tmp_path):
    database = Database(tmp_path / "legacy-block.db")
    database.update("users", 1, {"username": "alice"})
    chain = _seed_chain(database, 1, "alice")
    legacy = tmp_path / "legacy-resume.pdf"
    legacy.write_bytes(b"legacy private data")
    database.update("resumes", chain["resume"], {"pdf_path": str(legacy)})
    store = LocalObjectStore(tmp_path / "objects")
    token = _issue(database).token
    app = _privacy_app(database, store)
    challenge = _request(
        app,
        "POST",
        "/api/v1/me/deletion-challenge",
        headers=_auth(token),
    ).json()
    response = _request(
        app,
        "DELETE",
        "/api/v1/me",
        headers={**_auth(token), "Deletion-Token": challenge["deletion_token"]},
        json={"username": "alice", "confirmation": "DELETE MY DATA"},
    )
    assert response.status_code == 422
    assert database.get("users", 1) is not None
    assert legacy.exists()
    assert database.count("privacy_audit_events") == 0
    database.close()


class _FailingDeleteStore(LocalObjectStore):
    def delete(self, key):
        raise ObjectStorageError("private backend error")


def test_failed_object_cleanup_is_safely_queued_after_database_deletion(tmp_path):
    database = Database(tmp_path / "delete-compensation.db")
    database.update("users", 1, {"username": "alice"})
    store = _FailingDeleteStore(tmp_path / "objects")
    _upload(database, store, 1, "alice")
    token = _issue(database).token
    app = _privacy_app(database, store)
    challenge = _request(
        app,
        "POST",
        "/api/v1/me/deletion-challenge",
        headers=_auth(token),
    ).json()
    deleted = _request(
        app,
        "DELETE",
        "/api/v1/me",
        headers={**_auth(token), "Deletion-Token": challenge["deletion_token"]},
        json={"username": "alice", "confirmation": "DELETE MY DATA"},
    )

    assert deleted.status_code == 200
    assert deleted.json()["object_cleanup_pending"] == 1
    queued = database.list("object_cleanup_jobs", limit=1)[0]
    assert queued["status"] == "retry"
    assert queued["attempts"] == 1
    assert queued["error_code"] == "object_delete_failed"
    assert "private backend error" not in json.dumps(queued)
    assert database.get("users", 1) is None
    assert database.list("privacy_audit_events", limit=1)[0]["status"] == "cleanup_pending"
    retried = ObjectCleanupRunner(
        DatabasePrivacyRepository(database),
        LocalObjectStore(tmp_path / "objects"),
    ).run()
    assert retried == {"processed": 1, "pending": 0}
    assert database.count("object_cleanup_jobs") == 0
    database.close()


def test_privacy_openapi_declares_export_challenge_and_delete(tmp_path):
    database = Database(tmp_path / "privacy-openapi.db")
    schema = _privacy_app(database, LocalObjectStore(tmp_path / "objects")).openapi()
    assert "get" in schema["paths"]["/api/v1/me/export"]
    assert "post" in schema["paths"]["/api/v1/me/deletion-challenge"]
    assert "delete" in schema["paths"]["/api/v1/me"]
    database.close()
