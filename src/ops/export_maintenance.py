"""Export safe maintenance history for offline operational review."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
from src.db.postgres_client import PostgresDatabase
from src.db.sqlite_client import Database
from src.ops.maintenance_export_integrity import (
    attach_authentication,
    attach_integrity,
    parse_hmac_keyring,
)
from src.repositories.maintenance import (
    MaintenanceRunRepository,
    RetentionPolicyRepository,
)
from src.services.audio_retention import RETAINED_AUDIO_POLICY
from src.services.maintenance_monitoring import AUDIO_RETENTION_TASK


def build_maintenance_export(
    database,
    *,
    history_limit: int,
    retention_days: int,
    now=None,
    authentication_key_id: str = "",
    authentication_key: bytes | None = None,
) -> dict:
    """Build a user-data-free export from aggregate maintenance records."""
    history_limit = _validated_history_limit(history_limit)
    runs = MaintenanceRunRepository(
        database,
        history_max_rows=history_limit,
    )
    policies = RetentionPolicyRepository(database)
    current = runs.get(AUDIO_RETENTION_TASK)
    policy = policies.summary(
        RETAINED_AUDIO_POLICY,
        configured_days=retention_days,
        limit=history_limit,
    )
    payload = {
        "exported_at": (now or _utc_now)().isoformat(),
        "task_name": AUDIO_RETENTION_TASK,
        "history_limit": history_limit,
        "current_run": _public_current_run(current),
        "run_history": runs.history(AUDIO_RETENTION_TASK, limit=history_limit),
        "retention_policy": policy,
    }
    document = attach_integrity(payload)
    if authentication_key_id or authentication_key is not None:
        if not authentication_key_id or authentication_key is None:
            raise ValueError("Both authentication key ID and key are required.")
        document = attach_authentication(
            document,
            key_id=authentication_key_id,
            key=authentication_key,
        )
    return document


def write_export(payload: dict, output: str) -> None:
    """Write JSON to stdout or create a new file without overwriting one."""
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if output == "-":
        print(serialized)
        return
    target = Path(output)
    if not target.parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {target.parent}")
    with target.open("x", encoding="utf-8", newline="\n") as export_file:
        export_file.write(serialized)
        export_file.write("\n")


def _public_current_run(value: dict | None) -> dict | None:
    if value is None:
        return None
    allowed = (
        "status",
        "last_started_at",
        "last_completed_at",
        "last_checked",
        "last_deleted",
        "last_failed",
        "consecutive_failures",
        "run_total",
        "deleted_total",
        "failed_total",
        "last_error_code",
    )
    return {name: value.get(name) for name in allowed}


def _validated_history_limit(value: int) -> int:
    if not 12 <= value <= 1000:
        raise ValueError("history limit must be between 12 and 1000")
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _database():
    if config.DATABASE_BACKEND == "sqlite":
        return Database()
    if config.DATABASE_BACKEND == "postgres":
        return PostgresDatabase(config.POSTGRES_DSN)
    raise RuntimeError(f"Unsupported database backend: {config.DATABASE_BACKEND}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="-",
        help="Create this JSON file, or use - for stdout (default: -).",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=config.MAINTENANCE_HISTORY_MAX_ROWS,
        help="Export 12-1000 recent runs (default: configured retention boundary).",
    )
    parser.add_argument(
        "--authenticate",
        action="store_true",
        help="Authenticate the export with the configured active HMAC key.",
    )
    args = parser.parse_args(argv)
    try:
        history_limit = _validated_history_limit(args.history_limit)
    except ValueError as exc:
        parser.error(str(exc))
    database = _database()
    try:
        authentication_key_id = ""
        authentication_key = None
        if args.authenticate:
            keyring = parse_hmac_keyring(config.MAINTENANCE_EXPORT_HMAC_KEYS_JSON)
            authentication_key_id = config.MAINTENANCE_EXPORT_ACTIVE_KEY_ID
            authentication_key = keyring.get(authentication_key_id)
            if not authentication_key_id or authentication_key is None:
                raise ValueError("Configured active HMAC key is unavailable.")
        payload = build_maintenance_export(
            database,
            history_limit=history_limit,
            retention_days=config.RETAINED_AUDIO_MAX_DAYS,
            authentication_key_id=authentication_key_id,
            authentication_key=authentication_key,
        )
        write_export(payload, args.output)
    except (OSError, ValueError) as exc:
        print(f"Maintenance export failed: {exc}", file=sys.stderr)
        return 1
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
