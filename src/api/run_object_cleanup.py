"""Retry object deletions left pending after account erasure."""

from __future__ import annotations

import argparse
import json

import config
from src.api.upload_providers import configured_object_store
from src.db.postgres_client import PostgresDatabase
from src.db.sqlite_client import Database
from src.repositories.privacy import DatabasePrivacyRepository
from src.services.privacy import ObjectCleanupRunner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if config.DATABASE_BACKEND == "sqlite":
        database = Database()
    elif config.DATABASE_BACKEND == "postgres":
        database = PostgresDatabase(config.POSTGRES_DSN)
    else:
        raise RuntimeError(f"Unsupported database backend: {config.DATABASE_BACKEND}")
    try:
        result = ObjectCleanupRunner(
            DatabasePrivacyRepository(database),
            configured_object_store(),
        ).run(args.limit)
        print(json.dumps(result))
        return 0 if result["pending"] == 0 else 1
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
