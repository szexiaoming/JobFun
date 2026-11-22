"""Durable SQLite operation and private payload persistence."""

from __future__ import annotations

import json
from typing import Any

from src.db.models import OperationJob
from src.db.sqlite_client import Database


_JSON_FIELDS = {"input_refs_json", "result_refs_json"}


class SQLiteOperationRepository:
    def __init__(self, database: Database):
        self._database = database

    def get(self, user_id: int, operation_id: int) -> dict[str, Any] | None:
        row = self._database.fetch_one(
            "SELECT * FROM operation_jobs WHERE id = ? AND user_id = ?",
            (operation_id, user_id),
        )
        return _decode(row)

    def get_any(self, operation_id: int) -> dict[str, Any] | None:
        return _decode(self._database.get("operation_jobs", operation_id))

    def get_by_key(
        self,
        user_id: int,
        operation_type: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        row = self._database.fetch_one(
            """
            SELECT * FROM operation_jobs
            WHERE user_id = ? AND operation_type = ? AND idempotency_key = ?
            """,
            (user_id, operation_type, idempotency_key),
        )
        return _decode(row)

    def create(self, **values) -> dict[str, Any]:
        operation_id = self._database.insert("operation_jobs", OperationJob(**values))
        return self.get_any(operation_id)

    def update(self, operation_id: int, updates: dict[str, Any]) -> None:
        encoded = {
            key: json.dumps(value, ensure_ascii=False) if key in _JSON_FIELDS else value
            for key, value in updates.items()
        }
        self._database.update("operation_jobs", operation_id, encoded)

    def count_active(self, user_id: int) -> int:
        row = self._database.fetch_one(
            """
            SELECT COUNT(*) AS total FROM operation_jobs
            WHERE user_id = ? AND status IN ('queued', 'running')
            """,
            (user_id,),
        )
        return int(row["total"] if row else 0)

    def count_recent(self, user_id: int, since: str) -> int:
        row = self._database.fetch_one(
            """
            SELECT COUNT(*) AS total FROM operation_jobs
            WHERE user_id = ? AND created_at >= ?
            """,
            (user_id, since),
        )
        return int(row["total"] if row else 0)

    def store_payload(self, operation_id: int, user_id: int, payload: dict) -> None:
        self._database.execute(
            """
            INSERT INTO operation_payloads (operation_id, user_id, payload_json, created_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (operation_id, user_id, json.dumps(payload, ensure_ascii=False)),
        )

    def get_payload(self, operation_id: int, user_id: int) -> dict | None:
        row = self._database.fetch_one(
            """
            SELECT payload_json FROM operation_payloads
            WHERE operation_id = ? AND user_id = ?
            """,
            (operation_id, user_id),
        )
        if not row:
            return None
        try:
            value = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def delete_payload(self, operation_id: int, user_id: int) -> None:
        self._database.execute(
            "DELETE FROM operation_payloads WHERE operation_id = ? AND user_id = ?",
            (operation_id, user_id),
        )

    def list_queued(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._database.fetch_all(
            """
            SELECT * FROM operation_jobs
            WHERE status = 'queued'
            ORDER BY id ASC LIMIT ?
            """,
            (limit,),
        )
        return [_decode(row) for row in rows]

    def claim(self, operation_id: int, started_at: str) -> bool:
        changed = self._database.execute(
            """
            UPDATE operation_jobs
            SET status = 'running', progress = 5, started_at = ?, updated_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (started_at, started_at, operation_id),
        )
        return changed == 1


def _decode(row: dict | None) -> dict | None:
    if row is None:
        return None
    decoded = dict(row)
    for field in _JSON_FIELDS:
        value = decoded.get(field)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                parsed = {}
            decoded[field] = parsed if isinstance(parsed, dict) else {}
    return decoded
