"""Configuration owned by the HTTP adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class APISettings:
    title: str = "JobFun API"
    version: str = "0.31.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    request_id_header: str = "X-Request-ID"


def get_api_settings() -> APISettings:
    """Load non-secret HTTP settings from the environment."""
    return APISettings(
        title=os.getenv("JOBFUN_API_TITLE", "JobFun API").strip() or "JobFun API",
        version=os.getenv("JOBFUN_API_VERSION", "0.31.0").strip() or "0.31.0",
        environment=(
            os.getenv("JOBFUN_API_ENV", "development").strip().lower()
            or "development"
        ),
    )
