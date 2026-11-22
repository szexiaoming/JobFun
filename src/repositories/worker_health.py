"""Persistence for non-user worker heartbeat state."""

from __future__ import annotations

from src.db.models import WorkerHeartbeat


class WorkerHeartbeatRepository:
    def __init__(self, database) -> None:
        self._database = database

    def get(self, worker_name: str) -> dict | None:
        return self._database.fetch_one(
            "SELECT * FROM worker_heartbeats WHERE worker_name = ?",
            (worker_name,),
        )

    def record(
        self,
        *,
        worker_name: str,
        status: str,
        last_seen_at: str,
        last_started_at: str | None = None,
        last_completed_at: str | None = None,
        last_operation_id: int | None = None,
        last_error_code: str | None = None,
        processed_delta: int = 0,
        failed_delta: int = 0,
    ) -> dict:
        current = self.get(worker_name)
        if current is None:
            heartbeat_id = self._database.insert(
                "worker_heartbeats",
                WorkerHeartbeat(
                    worker_name=worker_name,
                    status=status,
                    last_seen_at=last_seen_at,
                    last_started_at=last_started_at or "",
                    last_completed_at=last_completed_at or "",
                    last_operation_id=last_operation_id or 0,
                    last_error_code=last_error_code or "",
                    processed_total=max(0, processed_delta),
                    failed_total=max(0, failed_delta),
                ),
            )
            return self._database.get("worker_heartbeats", heartbeat_id)
        updates = {
            "status": status,
            "last_seen_at": last_seen_at,
            "processed_total": int(current.get("processed_total") or 0)
            + max(0, processed_delta),
            "failed_total": int(current.get("failed_total") or 0)
            + max(0, failed_delta),
        }
        if last_started_at is not None:
            updates["last_started_at"] = last_started_at
        if last_completed_at is not None:
            updates["last_completed_at"] = last_completed_at
        if last_operation_id is not None:
            updates["last_operation_id"] = last_operation_id
        if last_error_code is not None:
            updates["last_error_code"] = last_error_code
        self._database.update("worker_heartbeats", int(current["id"]), updates)
        return self.get(worker_name)
