"""Versioned API root. User-data routes are intentionally absent in 0.20."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from src.api.config import APISettings
from src.api.schemas import VersionResponse


router = APIRouter(tags=["api"])


async def _settings(request: Request) -> APISettings:
    return request.app.state.api_settings


@router.get("", response_model=VersionResponse)
async def api_version(
    settings: Annotated[APISettings, Depends(_settings)],
) -> VersionResponse:
    return VersionResponse(service=settings.title, version=settings.version)
