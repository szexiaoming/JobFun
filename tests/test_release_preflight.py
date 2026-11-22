"""Private release preflight and read-only health verification tests."""

import base64
import json

from src.ops.preflight import evaluate_preflight
from src.ops.verify_health import verify_health


def _ready_environment() -> dict[str, str]:
    return {
        "JOBFUN_API_ENV": "staging",
        "DATABASE_BACKEND": "postgres",
        "POSTGRES_DSN": "postgresql://jobfun:super-secret@db.internal:5432/jobfun",
        "OBJECT_STORAGE_BACKEND": "s3",
        "S3_BUCKET": "jobfun-private-staging",
        "S3_REGION": "eu-west-2",
        "JOBFUN_COOKIE_SECURE": "true",
        "JOBFUN_LOG_FORMAT": "json",
        "JOBFUN_WORKER_NAME": "staging-worker-01",
        "JOBFUN_WORKER_HEARTBEAT_MAX_AGE_SECONDS": "120",
        "JOBFUN_WORKER_QUEUE_MAX_AGE_SECONDS": "300",
        "JOBFUN_WORKER_RUNNING_STALE_SECONDS": "900",
        "JOBFUN_RETAINED_AUDIO_MAX_DAYS": "30",
        "JOBFUN_AUDIO_CLEANUP_MAX_AGE_HOURS": "36",
        "JOBFUN_AUDIO_CLEANUP_STALE_SECONDS": "1800",
        "JOBFUN_AUDIO_CLEANUP_FAILURE_THRESHOLD": "2",
        "JOBFUN_MAINTENANCE_HISTORY_MAX_ROWS": "90",
        "AI_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "deepseek-super-secret",
        "OPENAI_API_KEY": "openai-super-secret",
        "JOBFUN_API_BASE_URL": "https://staging-api.example.test/api/v1",
        "JOBFUN_ALERT_WEBHOOK_URL": "https://alerts.example.test/jobfun",
        "JOBFUN_ALERT_WEBHOOK_BEARER_TOKEN": "alert-super-secret",
    }


def test_ready_staging_configuration_passes_without_disclosing_values():
    environment = _ready_environment()
    report = evaluate_preflight(environment)
    serialized = json.dumps(report.as_dict())

    assert report.ready is True
    assert report.as_dict()["summary"]["failures"] == 0
    for secret in ("super-secret", environment["POSTGRES_DSN"], environment["S3_BUCKET"]):
        assert secret not in serialized


def test_local_or_insecure_configuration_fails_release_gate():
    environment = _ready_environment()
    environment.update({
        "JOBFUN_API_ENV": "development",
        "DATABASE_BACKEND": "sqlite",
        "POSTGRES_DSN": "",
        "OBJECT_STORAGE_BACKEND": "local",
        "JOBFUN_COOKIE_SECURE": "false",
        "JOBFUN_LOG_FORMAT": "text",
        "JOBFUN_WORKER_NAME": "default",
    })

    report = evaluate_preflight(environment)

    assert report.ready is False
    failed = {check.name for check in report.checks if check.level == "failure"}
    assert {
        "api_environment",
        "database_backend",
        "postgres_dsn",
        "object_storage_backend",
        "secure_cookie",
        "structured_logs",
        "worker_identity",
    } <= failed


def test_optional_capabilities_warn_and_strict_mode_blocks_them():
    environment = _ready_environment()
    environment["OPENAI_API_KEY"] = ""
    environment["JOBFUN_ALERT_WEBHOOK_URL"] = ""

    normal = evaluate_preflight(environment)
    strict = evaluate_preflight(environment, strict=True)

    assert normal.ready is True
    assert normal.as_dict()["summary"]["warnings"] == 2
    assert strict.ready is False


def test_maintenance_history_boundary_must_be_supported():
    environment = _ready_environment()
    environment["JOBFUN_MAINTENANCE_HISTORY_MAX_ROWS"] = "1001"

    report = evaluate_preflight(environment)

    assert report.ready is False
    failed = {check.name for check in report.checks if check.level == "failure"}
    assert "maintenance_history" in failed


def test_optional_maintenance_export_authentication_validates_keyring():
    environment = _ready_environment()
    encoded_key = base64.b64encode(b"a" * 32).decode()
    environment.update({
        "JOBFUN_MAINTENANCE_EXPORT_ACTIVE_KEY_ID": "2026-q4",
        "JOBFUN_MAINTENANCE_EXPORT_HMAC_KEYS_JSON": json.dumps({"2026-q4": encoded_key}),
    })

    valid = evaluate_preflight(environment)
    environment["JOBFUN_MAINTENANCE_EXPORT_ACTIVE_KEY_ID"] = "missing"
    missing = evaluate_preflight(environment)

    assert valid.ready is True
    assert missing.ready is False
    assert "super-secret" not in json.dumps(valid.as_dict())
    assert "2026-q4" not in json.dumps(valid.as_dict())


class _HealthResponse:
    status = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_health_verifier_checks_all_three_read_only_contracts():
    requested = []
    payloads = {
        "/health/live": {"status": "ok"},
        "/health/ready": {"status": "ready"},
        "/health/worker": {"status": "healthy"},
        "/health/maintenance": {"status": "healthy"},
    }

    def opener(request, timeout):
        requested.append((request.full_url, timeout, request.get_method()))
        path = "/" + request.full_url.split("/", 3)[-1]
        return _HealthResponse(payloads[path])

    checks = verify_health("https://staging-api.example.test", opener=opener, timeout=2)

    assert all(check.ok for check in checks)
    assert [item.endpoint for item in checks] == [
        "/health/live",
        "/health/ready",
        "/health/worker",
        "/health/maintenance",
    ]
    assert all(method == "GET" for _, _, method in requested)
    assert all(timeout == 2 for _, timeout, _ in requested)


def test_health_verifier_rejects_degraded_worker():
    payloads = iter((
        {"status": "ok"},
        {"status": "ready"},
        {"status": "degraded", "checks": {"heartbeat": "stale"}},
        {"status": "healthy"},
    ))

    def opener(_request, timeout):
        assert timeout == 5
        return _HealthResponse(next(payloads))

    checks = verify_health("http://127.0.0.1:8000/", opener=opener)

    assert [check.ok for check in checks] == [True, True, False, True]
    assert "heartbeat" not in checks[2].message

