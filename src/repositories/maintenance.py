"""Persistence for maintenance run state, history, and policy audit."""

from __future__ import annotations

from src.db.models import (
    MaintenanceRun,
    MaintenanceRunEvent,
    RetentionPolicy,
    RetentionPolicyAuditEvent,
)


DEFAULT_MAINTENANCE_HISTORY_MAX_ROWS = 90


class MaintenanceRunRepository:
    def __init__(
        self,
        database,
        *,
        history_max_rows: int = DEFAULT_MAINTENANCE_HISTORY_MAX_ROWS,
    ) -> None:
        if not 12 <= history_max_rows <= 1000:
            raise ValueError("history_max_rows must be between 12 and 1000")
        self._database = database
        self._history_max_rows = history_max_rows

    def get(self, task_name: str) -> dict | None:
        return self._database.fetch_one(
            "SELECT * FROM maintenance_runs WHERE task_name = ?",
            (task_name,),
        )

    def start(self, task_name: str, started_at: str) -> dict:
        current = self.get(task_name)
        if current is None:
            run_id = self._database.insert(
                "maintenance_runs",
                MaintenanceRun(
                    task_name=task_name,
                    status="running",
                    last_started_at=started_at,
                ),
            )
            return self._database.get("maintenance_runs", run_id)
        self._database.update(
            "maintenance_runs",
            int(current["id"]),
            {
                "status": "running",
                "last_started_at": started_at,
                "last_error_code": "",
            },
        )
        return self.get(task_name)

    def finish(
        self,
        task_name: str,
        *,
        completed_at: str,
        checked: int,
        deleted: int,
        failed: int,
        error_code: str = "",
    ) -> dict:
        with self._database.transaction():
            current = self.get(task_name)
            if current is None:
                self.start(task_name, completed_at)
                current = self.get(task_name)
            has_failure = failed > 0 or bool(error_code)
            status = "failed" if has_failure else "succeeded"
            checked = max(0, checked)
            deleted = max(0, deleted)
            failed = max(0, failed)
            self._database.update(
                "maintenance_runs",
                int(current["id"]),
                {
                    "status": status,
                    "last_completed_at": completed_at,
                    "last_checked": checked,
                    "last_deleted": deleted,
                    "last_failed": failed,
                    "consecutive_failures": (
                        int(current.get("consecutive_failures") or 0) + 1
                        if has_failure
                        else 0
                    ),
                    "run_total": int(current.get("run_total") or 0) + 1,
                    "deleted_total": int(current.get("deleted_total") or 0) + deleted,
                    "failed_total": int(current.get("failed_total") or 0) + failed,
                    "last_error_code": error_code,
                },
            )
            self._database.insert(
                "maintenance_run_events",
                MaintenanceRunEvent(
                    task_name=task_name,
                    status=status,
                    started_at=str(current.get("last_started_at") or completed_at),
                    completed_at=completed_at,
                    checked_count=checked,
                    deleted_count=deleted,
                    failed_count=failed,
                    error_code=error_code,
                ),
            )
            self._database.execute(
                """
                DELETE FROM maintenance_run_events
                WHERE task_name = ? AND id NOT IN (
                    SELECT id FROM maintenance_run_events
                    WHERE task_name = ? ORDER BY id DESC LIMIT ?
                )
                """,
                (task_name, task_name, self._history_max_rows),
            )
        return self.get(task_name)

    def history(self, task_name: str, *, limit: int = 12) -> list[dict]:
        safe_limit = max(1, min(limit, self._history_max_rows))
        return self._database.fetch_all(
            """
            SELECT status, started_at, completed_at, checked_count,
                   deleted_count, failed_count, error_code
            FROM maintenance_run_events
            WHERE task_name = ?
            ORDER BY id DESC LIMIT ?
            """,
            (task_name, safe_limit),
        )


class RetentionPolicyRepository:
    """Record configuration changes without storing operators or secrets."""

    def __init__(self, database) -> None:
        self._database = database

    def observe(self, policy_name: str, retention_days: int, observed_at: str) -> dict:
        with self._database.transaction():
            current = self._database.fetch_one(
                "SELECT * FROM retention_policies WHERE policy_name = ?",
                (policy_name,),
            )
            if current is None:
                policy_id = self._database.insert(
                    "retention_policies",
                    RetentionPolicy(
                        policy_name=policy_name,
                        retention_days=retention_days,
                        observed_at=observed_at,
                    ),
                )
                return self._database.get("retention_policies", policy_id)
            previous_days = int(current["retention_days"])
            if previous_days == retention_days:
                self._database.update(
                    "retention_policies",
                    int(current["id"]),
                    {"observed_at": observed_at},
                )
                return self._database.get("retention_policies", int(current["id"]))
            self._database.insert(
                "retention_policy_audit_events",
                RetentionPolicyAuditEvent(
                    policy_name=policy_name,
                    previous_days=previous_days,
                    new_days=retention_days,
                    changed_at=observed_at,
                ),
            )
            self._database.update(
                "retention_policies",
                int(current["id"]),
                {"retention_days": retention_days, "observed_at": observed_at},
            )
            return self._database.get("retention_policies", int(current["id"]))

    def summary(
        self,
        policy_name: str,
        *,
        configured_days: int,
        limit: int = 5,
    ) -> dict:
        current = self._database.fetch_one(
            "SELECT retention_days, observed_at FROM retention_policies WHERE policy_name = ?",
            (policy_name,),
        )
        changes = self.changes(policy_name, limit=limit)
        return {
            "configured_days": configured_days,
            "observed_days": int(current["retention_days"]) if current else None,
            "last_observed_at": str(current["observed_at"]) if current else "",
            "changes": changes,
        }

    def changes(self, policy_name: str, *, limit: int = 20) -> list[dict]:
        return self._database.fetch_all(
            """
            SELECT previous_days, new_days, changed_at, source
            FROM retention_policy_audit_events
            WHERE policy_name = ? ORDER BY id DESC LIMIT ?
            """,
            (policy_name, max(1, min(limit, 1000))),
        )

