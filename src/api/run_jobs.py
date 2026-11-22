"""Run queued JobFun operations from a separate local worker process."""

from __future__ import annotations

import argparse
import time

from src.db.sqlite_client import Database
from src.services.job_runner import OperationRunner
from src.utils.logger import logger


def main() -> int:
    parser = argparse.ArgumentParser(description="Run queued JobFun AI operations.")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep polling the queue and updating the worker heartbeat.",
    )
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    if not 0.25 <= args.poll_interval <= 60:
        parser.error("--poll-interval must be between 0.25 and 60 seconds")
    with Database() as database:
        runner = OperationRunner(database)
        if not args.watch:
            completed = runner.run_next(limit=args.limit)
            print(f"Processed operations: {completed}")
            return 0
        logger.info(
            "worker_watch_started",
            extra={"event": "worker_watch_started", "status": "running"},
        )
        try:
            while True:
                completed = runner.run_next(limit=args.limit)
                if not completed:
                    time.sleep(args.poll_interval)
        except KeyboardInterrupt:
            logger.info(
                "worker_watch_stopped",
                extra={"event": "worker_watch_stopped", "status": "stopped"},
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
