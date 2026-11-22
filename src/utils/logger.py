"""
Simple structured logger for JobFun.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone


_SAFE_EXTRA_FIELDS = {
    "event",
    "request_id",
    "operation_id",
    "operation_type",
    "error_type",
    "error_code",
    "retry_count",
    "status",
    "maintenance_task",
    "checked_count",
    "deleted_count",
    "failed_count",
    "consecutive_failures",
}


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _SAFE_EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def setup_logger(
    name: str = "jobfun",
    level: int = logging.INFO,
    *,
    json_format: bool | None = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)

    use_json = (
        os.getenv("JOBFUN_LOG_FORMAT", "text").strip().lower() == "json"
        if json_format is None
        else json_format
    )
    fmt = StructuredJsonFormatter() if use_json else logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    return logger


logger = setup_logger()
