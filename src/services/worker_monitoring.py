"""Aggregate worker health without exposing operation payloads or users."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import config
from src.repositories.worker_health import WorkerHeartbeatRepository


class WorkerMonitoringService:
    def __init__(self, database, *, now=None) -> None:
        self._database = database
        self._heartbeats = WorkerHeartbeatRepository(database)
        self._now = now or (lambda: datetime.now(timezone.utc))

    def snapshot(self, worker_name: str | None = None) -> dict:
        now = self._now()
        selected = str(worker_name or config.WORKER_NAME)
        heartbeat = self._heartbeats.get(selected)
        queued = self._count("queued")
        running = self._count("running")
        failed_since = (now - timedelta(hours=24)).isoformat()
        failed = self._count_since("failed", failed_since)
        stale_since = (now - timedelta(seconds=config.WORKER_RUNNING_STALE_SECONDS)).isoformat()
        stale_running = self._count_updated_before("running", stale_since)
        oldest = self._database.fetch_one(
            "SELECT MIN(created_at) AS value FROM operation_jobs WHERE status = 'queued'"
        )
        oldest_age = _age_seconds(now, oldest.get("value") if oldest else None)
        heartbeat_age = _age_seconds(
            now,
            heartbeat.get("last_seen_at") if heartbeat else None,
        )
        checks = {
            "heartbeat": (
                "missing"
                if heartbeat_age is None
                else "stale"
                if heartbeat_age > config.WORKER_HEARTBEAT_MAX_AGE_SECONDS
                else "ok"
            ),
            "queue": (
                "backlogged"
                if oldest_age is not None
                and oldest_age > config.WORKER_QUEUE_MAX_AGE_SECONDS
                else "ok"
            ),
            "running": "stale" if stale_running else "ok",
            "worker": (
                "error"
                if heartbeat and str(heartbeat.get("status") or "") == "error"
                else "ok"
            ),
        }
        healthy = all(value == "ok" for value in checks.values())
        return {
            "status": "healthy" if healthy else "degraded",
            "worker_status": str(heartbeat.get("status") or "unknown") if heartbeat else "unknown",
            "heartbeat_age_seconds": heartbeat_age,
            "queued_operations": queued,
            "running_operations": running,
            "failed_operations_24h": failed,
            "stale_running_operations": stale_running,
            "oldest_queued_age_seconds": oldest_age,
            "processed_total": int(heartbeat.get("processed_total") or 0) if heartbeat else 0,
            "failed_total": int(heartbeat.get("failed_total") or 0) if heartbeat else 0,
            "checks": checks,
        }

    def _count(self, status: str) -> int:
        row = self._database.fetch_one(
            "SELECT COUNT(*) AS total FROM operation_jobs WHERE status = ?",
            (status,),
        )
        return int(row.get("total") or 0) if row else 0

    def _count_since(self, status: str, since: str) -> int:
        row = self._database.fetch_one(
            "SELECT COUNT(*) AS total FROM operation_jobs WHERE status = ? AND updated_at >= ?",
            (status, since),
        )
        return int(row.get("total") or 0) if row else 0

    def _count_updated_before(self, status: str, before: str) -> int:
        row = self._database.fetch_one(
            "SELECT COUNT(*) AS total FROM operation_jobs WHERE status = ? AND updated_at < ?",
            (status, before),
        )
        return int(row.get("total") or 0) if row else 0


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
