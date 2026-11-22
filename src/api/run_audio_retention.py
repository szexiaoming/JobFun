"""Delete retained interview audio that has reached its configured expiry."""

from __future__ import annotations

import argparse
import json

import config
from src.api.upload_providers import configured_object_store
from src.db.postgres_client import PostgresDatabase
from src.db.sqlite_client import Database
from src.repositories.maintenance import (
    MaintenanceRunRepository,
    RetentionPolicyRepository,
)
from src.repositories.stored_objects import StoredObjectDatabaseRepository
from src.services.alerts import configured_alert_sink
from src.services.audio_retention import AudioRetentionRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    if config.DATABASE_BACKEND == "sqlite":
        database = Database()
    elif config.DATABASE_BACKEND == "postgres":
        database = PostgresDatabase(config.POSTGRES_DSN)
    else:
        raise RuntimeError(f"Unsupported database backend: {config.DATABASE_BACKEND}")
    try:
        result = AudioRetentionRunner(
            configured_object_store(),
            StoredObjectDatabaseRepository(database),
            run_repository=MaintenanceRunRepository(
                database,
                history_max_rows=config.MAINTENANCE_HISTORY_MAX_ROWS,
            ),
            policy_repository=RetentionPolicyRepository(database),
            alert_sink=configured_alert_sink(),
        ).run(args.limit)
        print(json.dumps(result))
        return 0 if result["failed"] == 0 else 1
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())

