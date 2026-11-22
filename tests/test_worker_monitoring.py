"""Worker heartbeat, aggregate health, structured logs, and safe alerts."""

import io
import json
import logging
from datetime import datetime, timedelta, timezone

from src.db.models import OperationJob
from src.db.sqlite_client import Database
from src.repositories.worker_health import WorkerHeartbeatRepository
from src.services.alerts import WebhookAlertSink
from src.services.job_runner import OperationRunner
from src.services.worker_monitoring import WorkerMonitoringService
from src.utils.logger import StructuredJsonFormatter
from tests.test_api_authentication import _authenticated_app
from tests.test_api_skeleton import _request


def test_worker_health_is_degraded_without_heartbeat_and_healthy_after_idle_poll(tmp_path):
    database = Database(tmp_path / "worker-health.db")
    missing = WorkerMonitoringService(database).snapshot()
    assert missing["status"] == "degraded"
    assert missing["checks"]["heartbeat"] == "missing"

    assert OperationRunner(database, worker_name="default").run_next(limit=1) == []
    healthy = WorkerMonitoringService(database).snapshot()
    response = _request(_authenticated_app(database), "GET", "/health/worker")
    assert healthy["status"] == "healthy"
    assert healthy["worker_status"] == "idle"
    assert response.status_code == 200
    assert response.json()["checks"] == {
        "heartbeat": "ok",
        "queue": "ok",
        "running": "ok",
        "worker": "ok",
    }
    database.close()


def test_old_queue_and_stale_running_jobs_degrade_health_without_exposing_payload(tmp_path):
    database = Database(tmp_path / "worker-degraded.db")
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=1)).isoformat()
    WorkerHeartbeatRepository(database).record(
        worker_name="default",
        status="idle",
        last_seen_at=now.isoformat(),
    )
    database.insert(
        "operation_jobs",
        OperationJob(
            user_id=1,
            operation_type="resume_parse",
            idempotency_key="monitor-queue-0001",
            request_hash="hash",
            status="queued",
            created_at=old,
            updated_at=old,
        ),
    )
    database.insert(
        "operation_jobs",
        OperationJob(
            user_id=1,
            operation_type="match",
            idempotency_key="monitor-running-01",
            request_hash="hash2",
            status="running",
            created_at=old,
            started_at=old,
            updated_at=old,
        ),
    )
    response = _request(_authenticated_app(database), "GET", "/health/worker")
    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "degraded"
    assert body["checks"]["queue"] == "backlogged"
    assert body["checks"]["running"] == "stale"
    assert "user_id" not in response.text
    assert "request_hash" not in response.text
    database.close()


def test_json_formatter_only_emits_safe_operational_fields():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredJsonFormatter())
    test_logger = logging.getLogger("jobfun-test-structured")
    test_logger.handlers.clear()
    test_logger.propagate = False
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(handler)
    test_logger.error(
        "operation_failed",
        extra={
            "event": "operation_failed",
            "operation_id": 17,
            "operation_type": "match",
            "error_code": "operation_execution_failed",
            "private_payload": "resume secret",
        },
    )
    value = json.loads(stream.getvalue())
    assert value["event"] == "operation_failed"
    assert value["operation_id"] == 17
    assert "private_payload" not in value
    assert "resume secret" not in stream.getvalue()


class _Response:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_webhook_alert_filters_payload_and_uses_optional_bearer_token():
    captured = {}

    def opener(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return _Response()

    WebhookAlertSink(
        "https://alerts.example.test/jobfun",
        bearer_token="alert-token",
        timeout=2.5,
        opener=opener,
    ).send({
        "event_type": "operation_failed",
        "severity": "error",
        "operation_id": 9,
        "operation_type": "interview_answer",
        "error_code": "operation_execution_failed",
        "retry_count": 3,
        "occurred_at": "2026-11-21T12:00:00Z",
        "answer_text": "private interview answer",
        "user_id": 42,
        "maintenance_task": "audio_retention_cleanup",
        "checked_count": 4,
        "deleted_count": 3,
        "failed_count": 1,
        "consecutive_failures": 2,
    })
    assert captured["authorization"] == "Bearer alert-token"
    assert captured["timeout"] == 2.5
    assert "answer_text" not in captured["body"]
    assert "user_id" not in captured["body"]
    assert captured["body"]["maintenance_task"] == "audio_retention_cleanup"
    assert captured["body"]["failed_count"] == 1
