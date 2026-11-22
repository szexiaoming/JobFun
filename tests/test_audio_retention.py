"""Retained interview audio expiry, ownership, and batch deletion tests."""

import io
from datetime import datetime, timedelta, timezone

from src.db.models import InterviewAttempt, User
from src.db.sqlite_client import Database
from src.repositories.stored_objects import StoredObjectDatabaseRepository
from src.repositories.maintenance import RetentionPolicyRepository
from src.services.audio_retention import AudioRetentionRunner, AudioRetentionService
from src.services.context import RequestContext
from src.services.uploads import UploadApplicationService
from src.storage.local import LocalObjectStore


def _upload(database, store, *, user_id=1, suffix="one"):
    return UploadApplicationService(
        RequestContext(request_id="req_audio", user_id=user_id, username="owner"),
        store,
        StoredObjectDatabaseRepository(database),
    ).upload(
        kind="interview_audio",
        filename=f"answer-{suffix}.webm",
        content_type="audio/webm",
        stream=io.BytesIO(f"audio-{suffix}".encode()),
        idempotency_key=f"audio-retention-{suffix}",
    )


def test_owner_lists_retained_audio_and_batch_delete_clears_attempt_reference(tmp_path):
    database = Database(tmp_path / "retained.db")
    store = LocalObjectStore(tmp_path / "objects")
    other_user = database.insert("users", User(username="other"))
    owned = _upload(database, store, suffix="owned")
    foreign = _upload(database, store, user_id=other_user, suffix="foreign")
    database.insert(
        "interview_attempts",
        InterviewAttempt(audio_path=owned["object_key"], answer_text="synthetic"),
    )
    database.insert(
        "interview_attempts",
        InterviewAttempt(audio_path=foreign["object_key"], answer_text="synthetic"),
    )
    service = AudioRetentionService(
        RequestContext(request_id="req_audio_list", user_id=1, username="owner"),
        store,
        StoredObjectDatabaseRepository(database),
        retention_days=30,
    )

    result = service.list_retained()
    deleted = service.delete_batch([owned["id"], owned["id"], foreign["id"]])

    assert result["retention_days"] == 30
    assert [item["id"] for item in result["items"]] == [owned["id"]]
    assert result["items"][0]["expires_at"] > result["items"][0]["created_at"]
    assert "object_key" not in result["items"][0]
    assert deleted == {"requested": 2, "deleted": 1, "already_absent": 1}
    assert not store.exists(owned["object_key"])
    assert store.exists(foreign["object_key"])
    attempt = database.fetch_one(
        "SELECT audio_path FROM interview_attempts WHERE answer_text = ? ORDER BY id LIMIT 1",
        ("synthetic",),
    )
    assert attempt["audio_path"] == ""
    database.close()


def test_expiry_runner_deletes_only_audio_older_than_policy_in_bounded_batch(tmp_path):
    database = Database(tmp_path / "expiry.db")
    store = LocalObjectStore(tmp_path / "objects")
    repository = StoredObjectDatabaseRepository(database)
    now = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)

    old = _stored_audio(repository, store, "old", now - timedelta(days=31))
    recent = _stored_audio(repository, store, "recent", now - timedelta(days=29))
    database.insert(
        "interview_attempts",
        InterviewAttempt(audio_path=old["object_key"], answer_text="old-attempt"),
    )

    result = AudioRetentionRunner(
        store,
        repository,
        retention_days=30,
        now=lambda: now,
    ).run(limit=10)

    assert result == {"checked": 1, "deleted": 1, "failed": 0, "retention_days": 30}
    assert not store.exists(old["object_key"])
    assert store.exists(recent["object_key"])
    assert repository.get(1, old["id"]) is None
    assert repository.get(1, recent["id"]) is not None
    assert database.get("interview_attempts", 1)["audio_path"] == ""
    database.close()


def test_retention_policy_records_only_real_configuration_changes(tmp_path):
    database = Database(tmp_path / "retention-policy.db")
    store = LocalObjectStore(tmp_path / "objects")
    objects = StoredObjectDatabaseRepository(database)
    policies = RetentionPolicyRepository(database)
    now = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)

    for days in (30, 45, 45):
        AudioRetentionRunner(
            store,
            objects,
            retention_days=days,
            policy_repository=policies,
            now=lambda: now,
        ).run()

    service = AudioRetentionService(
        RequestContext(request_id="req_policy", user_id=1, username="owner"),
        store,
        objects,
        retention_days=45,
        policy_audit=policies,
    )
    policy = service.list_retained()["retention_policy"]

    assert policy["configured_days"] == 45
    assert policy["observed_days"] == 45
    assert policy["last_observed_at"] == now.isoformat()
    assert policy["changes"] == [
        {
            "previous_days": 30,
            "new_days": 45,
            "changed_at": now.isoformat(),
            "source": "configuration",
        }
    ]
    assert "user_id" not in str(policy)
    database.close()


def _stored_audio(repository, store, marker: str, created_at: datetime) -> dict:
    key = f"users/1/interview_audio/{marker}/answer.webm"
    blob = store.put(
        key,
        io.BytesIO(marker.encode()),
        content_type="audio/webm",
        max_bytes=100,
    )
    return repository.create(
        user_id=1,
        object_key=key,
        kind="interview_audio",
        original_name=f"{marker}.webm",
        content_type="audio/webm",
        size_bytes=blob.size_bytes,
        sha256=blob.sha256,
        idempotency_key=f"retention-{marker}",
        status="available",
        created_at=created_at.isoformat(),
    )

