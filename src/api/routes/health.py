"""Process health endpoints. These routes never read user data."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from src.api.config import APISettings
from src.api.providers import get_database
from src.api.readiness import ReadinessProbe
from src.api.schemas import (
    LiveResponse,
    MaintenanceHealthResponse,
    ReadyResponse,
    WorkerHealthResponse,
)
from src.services.maintenance_monitoring import MaintenanceMonitoringService
from src.services.worker_monitoring import WorkerMonitoringService


router = APIRouter(prefix="/health", tags=["health"])


async def _settings(request: Request) -> APISettings:
    return request.app.state.api_settings


async def _readiness_probe(request: Request) -> ReadinessProbe:
    return request.app.state.readiness_probe


@router.get("/live", response_model=LiveResponse)
async def live(
    settings: Annotated[APISettings, Depends(_settings)],
) -> LiveResponse:
    return LiveResponse(service=settings.title, version=settings.version)


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
async def ready(
    response: Response,
    probe: Annotated[ReadinessProbe, Depends(_readiness_probe)],
) -> ReadyResponse:
    results = dict(probe())
    checks = {name: "ok" if passed else "failed" for name, passed in results.items()}
    is_ready = bool(checks) and all(value == "ok" for value in checks.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="ready" if is_ready else "not_ready", checks=checks)


@router.get(
    "/worker",
    response_model=WorkerHealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": WorkerHealthResponse}},
)
async def worker_health(
    response: Response,
    database=Depends(get_database),
) -> dict:
    snapshot = WorkerMonitoringService(database).snapshot()
    if snapshot["status"] != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return snapshot


@router.get(
    "/maintenance",
    response_model=MaintenanceHealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": MaintenanceHealthResponse}},
)
async def maintenance_health(
    response: Response,
    database=Depends(get_database),
) -> dict:
    snapshot = MaintenanceMonitoringService(database).snapshot()
    if snapshot["status"] == "degraded":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return snapshot
