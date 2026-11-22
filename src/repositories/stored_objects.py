"""Ownership-scoped object metadata persistence."""

from __future__ import annotations

from typing import Any

from src.db.models import StoredObject


class StoredObjectDatabaseRepository:
    """Works with any database adapter implementing JobFun's CRUD contract."""

    def __init__(self, database) -> None:
        self._database = database

    def get(self, user_id: int, object_id: int) -> dict[str, Any] | None:
        return self._database.fetch_one(
            "SELECT * FROM stored_objects WHERE id = ? AND user_id = ? AND deleted_at = ''",
            (object_id, user_id),
        )

    def get_by_idempotency(
        self,
        user_id: int,
        kind: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        return self._database.fetch_one(
            """
            SELECT * FROM stored_objects
            WHERE user_id = ? AND kind = ? AND idempotency_key = ?
            """,
            (user_id, kind, idempotency_key),
        )

    def create(self, **values) -> dict[str, Any]:
        object_id = self._database.insert("stored_objects", StoredObject(**values))
        return self._database.get("stored_objects", object_id)

    def mark_deleted(self, user_id: int, object_id: int, deleted_at: str) -> None:
        self._database.execute(
            """
            UPDATE stored_objects
            SET status = 'deleted', deleted_at = ?
            WHERE id = ? AND user_id = ? AND deleted_at = ''
            """,
            (deleted_at, object_id, user_id),
        )

    def list_retained_audio(self, user_id: int) -> list[dict[str, Any]]:
        return self._database.fetch_all(
            """
            SELECT DISTINCT stored.*
            FROM stored_objects AS stored
            INNER JOIN interview_attempts AS attempt
                ON attempt.audio_path = stored.object_key
            WHERE stored.user_id = ?
              AND stored.kind = 'interview_audio'
              AND stored.deleted_at = ''
              AND stored.status = 'available'
            ORDER BY stored.created_at DESC, stored.id DESC
            """,
            (user_id,),
        )

    def list_expired_audio(self, cutoff: str, limit: int) -> list[dict[str, Any]]:
        return self._database.fetch_all(
            """
            SELECT * FROM stored_objects
            WHERE kind = 'interview_audio'
              AND deleted_at = ''
              AND status = 'available'
              AND created_at <= ?
            ORDER BY created_at, id
            LIMIT ?
            """,
            (cutoff, limit),
        )

    def clear_audio_reference(self, object_key: str) -> None:
        self._database.execute(
            "UPDATE interview_attempts SET audio_path = '' WHERE audio_path = ?",
            (object_key,),
        )
