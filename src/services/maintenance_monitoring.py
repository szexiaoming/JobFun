"""Aggregate maintenance-task health without exposing user data."""

from __future__ import annotations

from datetime import datetime, timezone

import config
from src.repositories.maintenance import MaintenanceRunRepository


AUDIO_RETENTION_TASK = "audio_retention_cleanup"


class MaintenanceMonitoringService:
    def __init__(self, database, *, now=None) -> None:
        self._runs = MaintenanceRunRepository(database)
        self._now = now or (lambda: datetime.now(timezone.utc))

    def snapshot(self, task_name: str = AUDIO_RETENTION_TASK) -> dict:
        now = self._now()
        run = self._runs.get(task_name)
        history = self._runs.history(task_name)
        completed_age = _age_seconds(
            now,
            run.get("last_completed_at") if run else None,
        )
        started_age = _age_seconds(
            now,
            run.get("last_started_at") if run else None,
        )
        consecutive = int(run.get("consecutive_failures") or 0) if run else 0
        running_stale = bool(
            run
            and str(run.get("status") or "") == "running"
            and started_age is not None
            and started_age > config.AUDIO_CLEANUP_STALE_SECONDS
        )
        checks = {
            "schedule": (
                "missing"
                if completed_age is None
                else "stale"
                if completed_age > config.AUDIO_CLEANUP_MAX_AGE_HOURS * 3600
                else "ok"
            ),
            "runtime": "stale" if running_stale else "ok",
            "failures": (
                "alerting"
                if consecutive >= config.AUDIO_CLEANUP_FAILURE_THRESHOLD
                else "warning"
                if consecutive
                else "ok"
            ),
        }
        degraded = checks["schedule"] != "ok" or checks["runtime"] != "ok" or checks["failures"] == "alerting"
        warning = not degraded and checks["failures"] == "warning"
        return {
            "status": "degraded" if degraded else "warning" if warning else "healthy",
            "task_status": str(run.get("status") or "unknown") if run else "unknown",
            "last_completed_age_seconds": completed_age,
            "last_started_age_seconds": started_age,
            "last_checked": int(run.get("last_checked") or 0) if run else 0,
            "last_deleted": int(run.get("last_deleted") or 0) if run else 0,
            "last_failed": int(run.get("last_failed") or 0) if run else 0,
            "consecutive_failures": consecutive,
            "run_total": int(run.get("run_total") or 0) if run else 0,
            "deleted_total": int(run.get("deleted_total") or 0) if run else 0,
            "failed_total": int(run.get("failed_total") or 0) if run else 0,
            "checks": checks,
            "trend": _trend(history),
            "recent_runs": [_public_run(item) for item in history],
        }


def _age_seconds(now: datetime, value) -> int | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return max(0, int((now - timestamp).total_seconds()))


def _trend(history: list[dict]) -> dict:
    total = len(history)
    succeeded = sum(str(item.get("status") or "") == "succeeded" for item in history)
    return {
        "window_runs": total,
        "success_rate_percent": round(succeeded * 100 / total, 1) if total else 0.0,
        "checked_count": sum(int(item.get("checked_count") or 0) for item in history),
        "deleted_count": sum(int(item.get("deleted_count") or 0) for item in history),
        "failed_count": sum(int(item.get("failed_count") or 0) for item in history),
    }


def _public_run(value: dict) -> dict:
    return {
        "status": str(value.get("status") or "unknown"),
        "completed_at": str(value.get("completed_at") or ""),
        "checked_count": int(value.get("checked_count") or 0),
        "deleted_count": int(value.get("deleted_count") or 0),
        "failed_count": int(value.get("failed_count") or 0),
        "error_code": str(value.get("error_code") or ""),
    }

