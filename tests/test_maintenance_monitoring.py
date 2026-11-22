"""Maintenance run status, health thresholds, and safe alert tests."""

import io
from datetime import datetime, timedelta, timezone

import config
from src.db.sqlite_client import Database
from src.repositories.maintenance import MaintenanceRunRepository
from src.repositories.stored_objects import StoredObjectDatabaseRepository
from src.services.audio_retention import AudioRetentionRunner
from src.services.maintenance_monitoring import (
    AUDIO_RETENTION_TASK,
    MaintenanceMonitoringService,
)
from src.storage.contracts import ObjectStorageError
from src.storage.local import LocalObjectStore
from tests.test_api_authentication import _authenticated_app
from tests.test_api_skeleton import _request


class _AlertSink:
    def __init__(self) -> None:
        self.events = []

    def send(self, event: dict) -> None:
        self.events.append(dict(event))


class _FailingDeleteStore(LocalObjectStore):
    def delete(self, key: str) -> None:
        raise ObjectStorageError("private object details")


def test_maintenance_health_is_missing_then_healthy_after_successful_run(tmp_path):
    database = Database(tmp_path / "maintenance-health.db")
    now = datetime.now(timezone.utc)
    missing = _request(_authenticated_app(database), "GET", "/health/maintenance")
    assert missing.status_code == 503
    assert missing.json()["checks"]["schedule"] == "missing"

    result = AudioRetentionRunner(
        LocalObjectStore(tmp_path / "objects"),
        StoredObjectDatabaseRepository(database),
        run_repository=MaintenanceRunRepository(database),
        now=lambda: now,
    ).run()
    healthy = MaintenanceMonitoringService(database, now=lambda: now).snapshot()

    assert result["failed"] == 0
    assert healthy["status"] == "healthy"
    assert healthy["task_status"] == "succeeded"
    assert healthy["run_total"] == 1
    assert healthy["last_checked"] == 0
    assert "user_id" not in str(healthy)
    database.close()


def test_stale_running_cleanup_is_degraded(tmp_path, monkeypatch):
    database = Database(tmp_path / "maintenance-stale.db")
    now = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(config, "AUDIO_CLEANUP_STALE_SECONDS", 300)
    runs = MaintenanceRunRepository(database)
    runs.start(AUDIO_RETENTION_TASK, (now - timedelta(minutes=10)).isoformat())

    snapshot = MaintenanceMonitoringService(database, now=lambda: now).snapshot()

    assert snapshot["status"] == "degraded"
    assert snapshot["checks"]["runtime"] == "stale"
    database.close()


def test_consecutive_failure_threshold_alerts_once_and_exposes_safe_counts(tmp_path, monkeypatch):
    database = Database(tmp_path / "maintenance-failures.db")
    now = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(config, "AUDIO_CLEANUP_FAILURE_THRESHOLD", 2)
    repository = StoredObjectDatabaseRepository(database)
    store = _FailingDeleteStore(tmp_path / "objects")
    blob = store.put(
        "users/1/interview_audio/expired/answer.webm",
        io.BytesIO(b"synthetic audio"),
        content_type="audio/webm",
        max_bytes=100,
    )
    repository.create(
        user_id=1,
        object_key=blob.key,
        kind="interview_audio",
        original_name="answer.webm",
        content_type="audio/webm",
        size_bytes=blob.size_bytes,
        sha256=blob.sha256,
        idempotency_key="maintenance-failure-audio",
        created_at=(now - timedelta(days=31)).isoformat(),
    )
    alerts = _AlertSink()
    runner = AudioRetentionRunner(
        store,
        repository,
        run_repository=MaintenanceRunRepository(database),
        alert_sink=alerts,
        retention_days=30,
        now=lambda: now,
    )

    first = runner.run()
    warning = MaintenanceMonitoringService(database, now=lambda: now).snapshot()
    second = runner.run()
    degraded = MaintenanceMonitoringService(database, now=lambda: now).snapshot()
    third = runner.run()

    assert first["failed"] == second["failed"] == third["failed"] == 1
    assert warning["status"] == "warning"
    assert warning["checks"]["failures"] == "warning"
    assert degraded["status"] == "degraded"
    assert degraded["checks"]["failures"] == "alerting"
    assert degraded["last_checked"] == 1
    assert degraded["last_deleted"] == 0
    assert degraded["last_failed"] == 1
    assert degraded["consecutive_failures"] == 2
    assert len(alerts.events) == 1
    assert alerts.events[0]["maintenance_task"] == AUDIO_RETENTION_TASK
    assert alerts.events[0]["failed_count"] == 1
    assert "user_id" not in alerts.events[0]
    assert "object_key" not in alerts.events[0]
    database.close()


def test_completed_runs_create_bounded_safe_history_and_trend(tmp_path):
    database = Database(tmp_path / "maintenance-history.db")
    now = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)
    runs = MaintenanceRunRepository(database)

    runs.start(AUDIO_RETENTION_TASK, (now - timedelta(minutes=2)).isoformat())
    runs.finish(
        AUDIO_RETENTION_TASK,
        completed_at=(now - timedelta(minutes=1)).isoformat(),
        checked=3,
        deleted=2,
        failed=1,
        error_code="object_cleanup_failed",
    )
    runs.start(AUDIO_RETENTION_TASK, now.isoformat())
    runs.finish(
        AUDIO_RETENTION_TASK,
        completed_at=now.isoformat(),
        checked=4,
        deleted=4,
        failed=0,
    )

    snapshot = MaintenanceMonitoringService(database, now=lambda: now).snapshot()

    assert snapshot["trend"] == {
        "window_runs": 2,
        "success_rate_percent": 50.0,
        "checked_count": 7,
        "deleted_count": 6,
        "failed_count": 1,
    }
    assert [item["status"] for item in snapshot["recent_runs"]] == [
        "succeeded",
        "failed",
    ]
    assert snapshot["recent_runs"][1]["error_code"] == "object_cleanup_failed"
    assert "user_id" not in str(snapshot["recent_runs"])
    assert "object_key" not in str(snapshot["recent_runs"])
    database.close()


def test_maintenance_history_keeps_only_the_latest_ninety_runs(tmp_path):
    database = Database(tmp_path / "maintenance-history-bound.db")
    runs = MaintenanceRunRepository(database)
    now = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)

    for index in range(95):
        completed_at = (now + timedelta(minutes=index)).isoformat()
        runs.start(AUDIO_RETENTION_TASK, completed_at)
        runs.finish(
            AUDIO_RETENTION_TASK,
            completed_at=completed_at,
            checked=index,
            deleted=0,
            failed=0,
        )

    rows = database.fetch_all(
        "SELECT checked_count FROM maintenance_run_events ORDER BY id",
    )
    assert len(rows) == 90
    assert rows[0]["checked_count"] == 5
    assert rows[-1]["checked_count"] == 94
    database.close()

