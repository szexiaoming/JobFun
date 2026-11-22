"""Optional live PostgreSQL behavior check for Iteration 0.24."""

import os

import pytest

from src.db.models import User
from src.db.postgres_client import PostgresDatabase
from src.db.sqlite_client import Database
from src.repositories.stored_objects import StoredObjectDatabaseRepository


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_database_adapters_share_the_object_repository_contract(tmp_path, backend):
    if backend == "sqlite":
        database = Database(tmp_path / "contract.db")
    else:
        dsn = os.getenv("TEST_POSTGRES_DSN", "").strip()
        if not dsn:
            pytest.skip("Set TEST_POSTGRES_DSN to run the live PostgreSQL contract test")
        database = PostgresDatabase(dsn)
    marker = f"jobfun-{backend}-contract-user"
    user_id = database.insert("users", User(username=marker))
    try:
        repository = StoredObjectDatabaseRepository(database)
        stored = repository.create(
            user_id=user_id,
            object_key=f"contract/{user_id}/object.txt",
            kind="resume_source",
            original_name="object.txt",
            content_type="text/plain",
            size_bytes=4,
            sha256="0" * 64,
            idempotency_key=f"contract-{user_id}",
            created_at="2026-11-20T00:00:00+00:00",
        )
        assert repository.get(user_id, stored["id"])["object_key"] == stored["object_key"]
        assert repository.get_by_idempotency(
            user_id, "resume_source", f"contract-{user_id}"
        )["id"] == stored["id"]
    finally:
        for row in database.find_by("stored_objects", "user_id", user_id):
            database.delete("stored_objects", row["id"])
        database.delete("users", user_id)
        database.close()
