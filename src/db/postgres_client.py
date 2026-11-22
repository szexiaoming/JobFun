"""Psycopg implementation of JobFun's database adapter contract."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from typing import Any

from src.db.models import TABLE_MAP, User


_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


class PostgresDatabase:
    """Small PostgreSQL adapter matching the existing SQLite database surface."""

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("POSTGRES_DSN is required")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Install psycopg[binary] to use PostgreSQL") from exc
        self._conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        self._init_schema()

    def _init_schema(self) -> None:
        # The canonical schema intentionally stays beside the SQLite adapter.
        # Its SQL is portable after replacing the two SQLite-only constructs.
        from src.db.sqlite_client import SCHEMA

        schema = (
            SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
            .replace(
                "DEFAULT (datetime('now','localtime'))",
                "DEFAULT (CURRENT_TIMESTAMP::text)",
            )
        )
        with self._conn.transaction():
            with self._conn.cursor() as cursor:
                for statement in schema.split(";"):
                    if statement.strip():
                        cursor.execute(statement)
                cursor.execute("SELECT COUNT(*) AS total FROM users")
                if int(cursor.fetchone()["total"]) == 0:
                    cursor.execute("INSERT INTO users (username) VALUES ('default')")

    def insert(self, table: str, obj: Any) -> int:
        table = _table(table)
        data = _to_db(obj)
        data.pop("id", None)
        columns = [_column(table, name) for name in data]
        placeholders = ", ".join("%s" for _ in data)
        query = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) RETURNING id"
        )
        with self._conn.cursor() as cursor:
            cursor.execute(query, tuple(data.values()))
            return int(cursor.fetchone()["id"])

    def get(self, table: str, obj_id: int) -> dict | None:
        table = _table(table)
        return self.fetch_one(f"SELECT * FROM {table} WHERE id = ?", (obj_id,))

    def list(self, table: str, limit: int = 50, offset: int = 0) -> list[dict]:
        table = _table(table)
        return self.fetch_all(
            f"SELECT * FROM {table} ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def update(self, table: str, obj_id: int, updates: dict) -> None:
        table = _table(table)
        if not updates:
            return
        names = [_column(table, name) for name in updates]
        assignments = ", ".join(f"{name} = %s" for name in names)
        query = f"UPDATE {table} SET {assignments} WHERE id = %s"
        with self._conn.cursor() as cursor:
            cursor.execute(query, (*updates.values(), obj_id))

    def delete(self, table: str, obj_id: int) -> None:
        table = _table(table)
        self.execute(f"DELETE FROM {table} WHERE id = ?", (obj_id,))

    def find_by(self, table: str, column: str, value: Any) -> list[dict]:
        table = _table(table)
        column = _column(table, column)
        return self.fetch_all(f"SELECT * FROM {table} WHERE {column} = ?", (value,))

    def count(self, table: str) -> int:
        table = _table(table)
        row = self.fetch_one(f"SELECT COUNT(*) AS total FROM {table}")
        return int(row["total"] if row else 0)

    def fetch_one(self, query: str, parameters: tuple = ()) -> dict | None:
        with self._conn.cursor() as cursor:
            cursor.execute(_query(query), parameters)
            row = cursor.fetchone()
            return dict(row) if row else None

    def fetch_all(self, query: str, parameters: tuple = ()) -> list[dict]:
        with self._conn.cursor() as cursor:
            cursor.execute(_query(query), parameters)
            return [dict(row) for row in cursor.fetchall()]

    def execute(self, query: str, parameters: tuple = ()) -> int:
        with self._conn.cursor() as cursor:
            cursor.execute(_query(query), parameters)
            return int(cursor.rowcount)

    @contextmanager
    def transaction(self):
        with self._conn.transaction():
            yield self

    def get_latest_match(self, resume_id: int = None, jd_id: int = None) -> dict | None:
        if resume_id and jd_id:
            return self.fetch_one(
                """
                SELECT * FROM match_results WHERE resume_id = ? AND jd_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (resume_id, jd_id),
            )
        return self.fetch_one("SELECT * FROM match_results ORDER BY id DESC LIMIT 1")

    def get_suggestions_for_match(self, match_id: int) -> list[dict]:
        return self.find_by("suggestions", "match_id", match_id)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _table(value: str) -> str:
    if value not in TABLE_MAP:
        raise ValueError(f"Unsupported table: {value}")
    return value


def _column(table: str, value: str) -> str:
    allowed = set(TABLE_MAP[table].__dataclass_fields__)
    if table == "users":
        allowed.add("settings_json")
        allowed.discard("settings")
    if value not in allowed or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsupported column: {table}.{value}")
    return value


def _query(value: str) -> str:
    # Repository SQL is fixed application code; this only converts its bind style
    # and one SQLite time helper. Values remain separately parameterized.
    return value.replace("datetime('now')", "CURRENT_TIMESTAMP").replace("?", "%s")


def _to_db(obj: Any) -> dict:
    data = {}
    for name in obj.__dataclass_fields__:
        value = getattr(obj, name)
        if isinstance(value, (list, dict)):
            data[name] = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            data[name] = int(value)
        else:
            data[name] = value
    if isinstance(obj, User):
        data["settings_json"] = data.pop("settings")
    return data
