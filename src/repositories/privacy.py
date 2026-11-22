"""User export, deletion, audit, and object-cleanup persistence."""

from __future__ import annotations

from typing import Any

from src.db.models import PrivacyAuditEvent, PrivacyDeletionChallenge


class DatabasePrivacyRepository:
    def __init__(self, database) -> None:
        self._database = database

    def create_deletion_challenge(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: str,
        created_at: str,
    ) -> None:
        with self._database.transaction():
            self._database.execute(
                "DELETE FROM privacy_deletion_challenges WHERE user_id = ?",
                (user_id,),
            )
            self._database.insert(
                "privacy_deletion_challenges",
                PrivacyDeletionChallenge(
                    user_id=user_id,
                    token_hash=token_hash,
                    expires_at=expires_at,
                    created_at=created_at,
                ),
            )

    def export_snapshot(self, user_id: int) -> dict[str, Any] | None:
        user = self._database.fetch_one(
            "SELECT id, username, settings_json, created_at FROM users WHERE id = ? AND is_active = 1",
            (user_id,),
        )
        if user is None:
            return None
        snapshot: dict[str, Any] = {"user": user}
        snapshot["resumes"] = self._rows("resumes", "user_id", [user_id])
        snapshot["job_descriptions"] = self._rows(
            "job_descriptions", "user_id", [user_id]
        )
        snapshot["applications"] = self._rows("applications", "user_id", [user_id])
        snapshot["operation_jobs"] = self._rows(
            "operation_jobs", "user_id", [user_id]
        )
        snapshot["operation_payloads"] = self._rows(
            "operation_payloads", "user_id", [user_id]
        )
        snapshot["stored_objects"] = self._rows(
            "stored_objects", "user_id", [user_id]
        )

        resume_ids = _ids(snapshot["resumes"])
        job_ids = _ids(snapshot["job_descriptions"])
        application_ids = _ids(snapshot["applications"])
        snapshot["match_results"] = self._database.fetch_all(
            """
            SELECT match.* FROM match_results AS match
            JOIN resumes AS resume ON resume.id = match.resume_id
            JOIN job_descriptions AS job ON job.id = match.jd_id
            WHERE resume.user_id = ? AND job.user_id = ?
            ORDER BY match.id ASC
            """,
            (user_id, user_id),
        )
        match_ids = _ids(snapshot["match_results"])
        snapshot["job_requirements"] = self._rows(
            "job_requirements", "jd_id", job_ids
        )
        requirement_ids = _ids(snapshot["job_requirements"])
        snapshot["evidence_matches"] = self._rows(
            "evidence_matches", "match_id", match_ids
        )
        evidence_ids = _ids(snapshot["evidence_matches"])
        snapshot["evidence_reviews"] = self._rows(
            "evidence_reviews", "match_id", match_ids
        )
        snapshot["evidence_supplements"] = self._rows(
            "evidence_supplements", "match_id", match_ids
        )
        supplement_ids = _ids(snapshot["evidence_supplements"])
        snapshot["evidence_supplement_events"] = self._rows(
            "evidence_supplement_events", "supplement_id", supplement_ids
        )
        snapshot["suggestions"] = self._rows("suggestions", "match_id", match_ids)
        suggestion_ids = _ids(snapshot["suggestions"])
        snapshot["application_events"] = self._rows(
            "application_events", "application_id", application_ids
        )
        snapshot["interview_questions"] = self._rows(
            "interview_questions", "match_id", match_ids
        )
        question_ids = _ids(snapshot["interview_questions"])
        snapshot["interview_attempts"] = self._rows(
            "interview_attempts", "application_id", application_ids
        )
        attempt_ids = _ids(snapshot["interview_attempts"])
        snapshot["interview_follow_ups"] = self._rows(
            "interview_follow_ups", "parent_attempt_id", attempt_ids
        )
        snapshot["latex_changes"] = self._rows(
            "latex_changes", "resume_id", resume_ids
        )
        # Keep variables visible here as documentation of the complete graph.
        _ = requirement_ids, evidence_ids, suggestion_ids, question_ids
        return snapshot

    def record_audit(self, **values) -> int:
        return self._database.insert(
            "privacy_audit_events",
            PrivacyAuditEvent(**values),
        )

    def delete_user_data(
        self,
        *,
        user_id: int,
        token_hash: str,
        now: str,
        correlation_id: str,
        subject_hash: str,
        request_id: str,
    ) -> dict[str, Any] | None:
        with self._database.transaction():
            challenge = self._database.fetch_one(
                """
                SELECT id FROM privacy_deletion_challenges
                WHERE user_id = ? AND token_hash = ? AND expires_at > ?
                """,
                (user_id, token_hash, now),
            )
            if challenge is None:
                return None
            if self._database.execute(
                "DELETE FROM privacy_deletion_challenges WHERE id = ?",
                (challenge["id"],),
            ) != 1:
                return None
            snapshot = self.export_snapshot(user_id)
            if snapshot is None:
                return None
            counts = {
                name: (1 if name == "user" else len(rows))
                for name, rows in snapshot.items()
            }
            audit_id = self.record_audit(
                correlation_id=correlation_id,
                subject_hash=subject_hash,
                event_type="account_deleted",
                status="completed",
                request_id=request_id,
                details_json={"deleted_counts": counts},
                created_at=now,
            )
            cleanup_jobs = []
            for stored in snapshot["stored_objects"]:
                self._database.execute(
                    """
                    INSERT INTO object_cleanup_jobs
                        (object_key, status, attempts, error_code, created_at, updated_at)
                    VALUES (?, 'pending', 0, '', ?, ?)
                    ON CONFLICT(object_key) DO NOTHING
                    """,
                    (stored["object_key"], now, now),
                )
                job = self._database.fetch_one(
                    "SELECT * FROM object_cleanup_jobs WHERE object_key = ?",
                    (stored["object_key"],),
                )
                if job:
                    cleanup_jobs.append(job)
            self._delete_snapshot(snapshot)
            self._database.execute("DELETE FROM api_tokens WHERE user_id = ?", (user_id,))
            self._database.execute(
                "DELETE FROM privacy_deletion_challenges WHERE user_id = ?",
                (user_id,),
            )
            self._database.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return {
            "audit_id": audit_id,
            "correlation_id": correlation_id,
            "counts": counts,
            "cleanup_jobs": cleanup_jobs,
        }

    def list_cleanup_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._database.fetch_all(
            """
            SELECT * FROM object_cleanup_jobs
            WHERE status IN ('pending', 'retry')
            ORDER BY id ASC LIMIT ?
            """,
            (limit,),
        )

    def complete_cleanup(self, job_id: int) -> None:
        # Successful cleanup jobs contain object keys derived from deleted users,
        # so remove the queue record instead of retaining it as long-term audit.
        self._database.execute("DELETE FROM object_cleanup_jobs WHERE id = ?", (job_id,))

    def fail_cleanup(self, job_id: int, updated_at: str) -> None:
        self._database.execute(
            """
            UPDATE object_cleanup_jobs
            SET status = 'retry', attempts = attempts + 1,
                error_code = 'object_delete_failed', updated_at = ?
            WHERE id = ?
            """,
            (updated_at, job_id),
        )

    def update_deletion_audit(self, audit_id: int, cleanup_pending: int) -> None:
        self._database.update(
            "privacy_audit_events",
            audit_id,
            {"status": "cleanup_pending" if cleanup_pending else "completed"},
        )

    def _delete_snapshot(self, snapshot: dict[str, Any]) -> None:
        order = (
            "interview_follow_ups",
            "interview_attempts",
            "interview_questions",
            "application_events",
            "evidence_supplement_events",
            "evidence_reviews",
            "evidence_supplements",
            "evidence_matches",
            "latex_changes",
            "suggestions",
            "job_requirements",
            "applications",
            "match_results",
            "operation_payloads",
            "operation_jobs",
            "stored_objects",
            "resumes",
            "job_descriptions",
        )
        for table in order:
            if table == "operation_payloads":
                operation_ids = [
                    int(row["operation_id"]) for row in snapshot[table]
                ]
                self._delete_ids(table, "operation_id", operation_ids)
            else:
                self._delete_ids(table, "id", _ids(snapshot[table]))

    def _rows(self, table: str, column: str, values: list[int]) -> list[dict]:
        if not values:
            return []
        placeholders = ", ".join("?" for _ in values)
        order_column = "operation_id" if table == "operation_payloads" else "id"
        return self._database.fetch_all(
            f"SELECT * FROM {table} WHERE {column} IN ({placeholders}) ORDER BY {order_column} ASC",
            tuple(values),
        )

    def _delete_ids(self, table: str, column: str, values: list[int]) -> None:
        if not values:
            return
        placeholders = ", ".join("?" for _ in values)
        self._database.execute(
            f"DELETE FROM {table} WHERE {column} IN ({placeholders})",
            tuple(values),
        )


def _ids(rows: list[dict]) -> list[int]:
    return [int(row["id"]) for row in rows]
