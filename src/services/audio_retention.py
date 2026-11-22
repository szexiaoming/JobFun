"""Owner-scoped retained-audio management and operational expiry cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import config
from src.repositories.contracts import StoredObjectRepository
from src.repositories.maintenance import (
    MaintenanceRunRepository,
    RetentionPolicyRepository,
)
from src.services.alerts import AlertSink, NullAlertSink
from src.services.context import RequestContext
from src.services.maintenance_monitoring import AUDIO_RETENTION_TASK
from src.services.maintenance_monitoring import MaintenanceMonitoringService
from src.storage.contracts import ObjectStore
from src.utils.logger import logger


RETAINED_AUDIO_POLICY = "retained_interview_audio"


class AudioRetentionError(Exception):
    code = "audio_retention_error"


class AudioRetentionValidationError(AudioRetentionError):
    code = "audio_retention_validation_error"


class AudioRetentionService:
    def __init__(
        self,
        context: RequestContext,
        store: ObjectStore,
        repository: StoredObjectRepository,
        *,
        retention_days: int | None = None,
        maintenance: MaintenanceMonitoringService | None = None,
        policy_audit: RetentionPolicyRepository | None = None,
    ) -> None:
        if context.user_id is None or context.user_id <= 0:
            raise ValueError("An authenticated user context is required")
        self.context = context
        self._store = store
        self._repository = repository
        self._retention_days = _retention_days(retention_days)
        self._maintenance = maintenance
        self._policy_audit = policy_audit

    @property
    def user_id(self) -> int:
        return int(self.context.user_id)

    def list_retained(self) -> dict:
        items = [
            _public_retained_audio(row, self._retention_days)
            for row in self._repository.list_retained_audio(self.user_id)
        ]
        maintenance = (
            self._maintenance.snapshot()
            if self._maintenance is not None
            else _missing_maintenance_status()
        )
        return {
            "items": items,
            "retention_days": self._retention_days,
            "maintenance": maintenance,
            "retention_policy": (
                self._policy_audit.summary(
                    RETAINED_AUDIO_POLICY,
                    configured_days=self._retention_days,
                )
                if self._policy_audit is not None
                else _missing_policy_audit(self._retention_days)
            ),
        }

    def delete_batch(self, object_ids: list[int]) -> dict:
        ids = _validated_ids(object_ids)
        deleted = 0
        already_absent = 0
        for object_id in ids:
            stored = self._repository.get(self.user_id, object_id)
            if stored is None or str(stored.get("kind") or "") != "interview_audio":
                already_absent += 1
                continue
            self._delete(stored)
            deleted += 1
        return {
            "requested": len(ids),
            "deleted": deleted,
            "already_absent": already_absent,
        }

    def _delete(self, stored: dict) -> None:
        object_key = str(stored["object_key"])
        self._store.delete(object_key)
        self._repository.clear_audio_reference(object_key)
        self._repository.mark_deleted(
            self.user_id,
            int(stored["id"]),
            _utc_now().isoformat(),
        )


class AudioRetentionRunner:
    """Delete expired audio in bounded batches; safe to run repeatedly."""

    def __init__(
        self,
        store: ObjectStore,
        repository: StoredObjectRepository,
        *,
        retention_days: int | None = None,
        now=None,
        run_repository: MaintenanceRunRepository | None = None,
        policy_repository: RetentionPolicyRepository | None = None,
        alert_sink: AlertSink | None = None,
    ) -> None:
        self._store = store
        self._repository = repository
        self._retention_days = _retention_days(retention_days)
        self._now = now or _utc_now
        self._runs = run_repository
        self._policies = policy_repository
        self._alerts = alert_sink or NullAlertSink()

    def run(self, limit: int = 100) -> dict:
        if not 1 <= limit <= 1000:
            raise AudioRetentionValidationError("limit must be between 1 and 1000")
        started_at = self._now()
        if self._policies is not None:
            self._policies.observe(
                RETAINED_AUDIO_POLICY,
                self._retention_days,
                started_at.isoformat(),
            )
        if self._runs is not None:
            self._runs.start(AUDIO_RETENTION_TASK, started_at.isoformat())
        cutoff = self._now() - timedelta(days=self._retention_days)
        try:
            rows = self._repository.list_expired_audio(cutoff.isoformat(), limit)
        except Exception:
            result = {
                "checked": 0,
                "deleted": 0,
                "failed": 1,
                "retention_days": self._retention_days,
            }
            self._finish_run(result, error_code="cleanup_scan_failed")
            logger.error(
                "retained_audio_cleanup_scan_failed",
                extra={
                    "event": "retained_audio_cleanup_failed",
                    "maintenance_task": AUDIO_RETENTION_TASK,
                    "error_code": "cleanup_scan_failed",
                },
            )
            return result
        deleted = 0
        failed = 0
        for stored in rows:
            try:
                object_key = str(stored["object_key"])
                self._store.delete(object_key)
                self._repository.clear_audio_reference(object_key)
                self._repository.mark_deleted(
                    int(stored["user_id"]),
                    int(stored["id"]),
                    self._now().isoformat(),
                )
                deleted += 1
            except Exception:
                failed += 1
                logger.error(
                    "retained_audio_cleanup_failed",
                    extra={
                        "event": "retained_audio_cleanup_failed",
                        "error_code": "object_cleanup_failed",
                        "maintenance_task": AUDIO_RETENTION_TASK,
                    },
                )
        result = {
            "checked": len(rows),
            "deleted": deleted,
            "failed": failed,
            "retention_days": self._retention_days,
        }
        self._finish_run(
            result,
            error_code="object_cleanup_failed" if failed else "",
        )
        return result

    def _finish_run(self, result: dict, *, error_code: str) -> None:
        run = None
        if self._runs is not None:
            run = self._runs.finish(
                AUDIO_RETENTION_TASK,
                completed_at=self._now().isoformat(),
                checked=int(result["checked"]),
                deleted=int(result["deleted"]),
                failed=int(result["failed"]),
                error_code=error_code,
            )
        consecutive = int(run.get("consecutive_failures") or 0) if run else 0
        if not result["failed"] or consecutive != config.AUDIO_CLEANUP_FAILURE_THRESHOLD:
            return
        event = {
            "event_type": "maintenance_failed",
            "severity": "error",
            "maintenance_task": AUDIO_RETENTION_TASK,
            "error_code": error_code or "object_cleanup_failed",
            "checked_count": int(result["checked"]),
            "deleted_count": int(result["deleted"]),
            "failed_count": int(result["failed"]),
            "consecutive_failures": consecutive,
            "occurred_at": self._now().isoformat(),
        }
        try:
            self._alerts.send(event)
        except Exception:
            logger.error(
                "maintenance_alert_delivery_failed",
                extra={
                    "event": "alert_delivery_failed",
                    "maintenance_task": AUDIO_RETENTION_TASK,
                    "error_code": "alert_delivery_failed",
                    "consecutive_failures": consecutive,
                },
            )


def _public_retained_audio(value: dict, retention_days: int) -> dict:
    created_at = _parse_time(value.get("created_at"))
    expires_at = created_at + timedelta(days=retention_days)
    return {
        "id": int(value["id"]),
        "original_name": str(value.get("original_name") or "audio"),
        "content_type": str(value.get("content_type") or "application/octet-stream"),
        "size_bytes": int(value.get("size_bytes") or 0),
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


def _validated_ids(values: list[int]) -> list[int]:
    if not values:
        raise AudioRetentionValidationError("Select at least one audio object")
    unique = list(dict.fromkeys(values))
    if len(unique) > 100 or any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in unique):
        raise AudioRetentionValidationError("Select 1 to 100 valid audio objects")
    return unique


def _retention_days(value: int | None) -> int:
    days = config.RETAINED_AUDIO_MAX_DAYS if value is None else value
    if not 1 <= days <= 365:
        raise AudioRetentionValidationError("retention days must be between 1 and 365")
    return days


def _parse_time(value) -> datetime:
    try:
        result = datetime.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise AudioRetentionError("Stored audio has an invalid timestamp") from exc
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _missing_maintenance_status() -> dict:
    return {
        "status": "degraded",
        "task_status": "unknown",
        "last_completed_age_seconds": None,
        "last_started_age_seconds": None,
        "last_checked": 0,
        "last_deleted": 0,
        "last_failed": 0,
        "consecutive_failures": 0,
        "run_total": 0,
        "deleted_total": 0,
        "failed_total": 0,
        "checks": {"schedule": "missing", "runtime": "ok", "failures": "ok"},
        "trend": {
            "window_runs": 0,
            "success_rate_percent": 0.0,
            "checked_count": 0,
            "deleted_count": 0,
            "failed_count": 0,
        },
        "recent_runs": [],
    }


def _missing_policy_audit(configured_days: int) -> dict:
    return {
        "configured_days": configured_days,
        "observed_days": None,
        "last_observed_at": "",
        "changes": [],
    }

