"""JobFun FastAPI application factory and ASGI entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from src.api.config import APISettings, get_api_settings
from src.api.errors import register_error_handlers
from src.api.middleware import register_request_id_middleware
from src.api.readiness import ReadinessProbe, default_readiness_probe
from src.api.routes.health import router as health_router
from src.api.routes.identity import router as identity_router
from src.api.routes.read_api import router as read_router
from src.api.routes.v1 import router as v1_router
from src.api.routes.write_api import router as write_router
from src.api.routes.uploads import router as upload_router
from src.api.routes.privacy import router as privacy_router
from src.api.schemas import ErrorResponse


def create_app(
    *,
    settings: APISettings | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    api_settings = settings or get_api_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.started_at = datetime.now(timezone.utc)
        yield

    application = FastAPI(
        title=api_settings.title,
        version=api_settings.version,
        lifespan=lifespan,
        responses={
            401: {"model": ErrorResponse, "description": "身份凭据无效"},
            409: {"model": ErrorResponse, "description": "幂等键冲突"},
            429: {"model": ErrorResponse, "description": "请求频率超限"},
            404: {"model": ErrorResponse, "description": "资源不存在"},
            422: {"model": ErrorResponse, "description": "请求参数无效"},
            500: {"model": ErrorResponse, "description": "内部服务错误"},
        },
    )
    application.state.api_settings = api_settings
    application.state.readiness_probe = readiness_probe or default_readiness_probe

    register_request_id_middleware(application, api_settings.request_id_header)
    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(v1_router, prefix=api_settings.api_v1_prefix)
    application.include_router(identity_router, prefix=api_settings.api_v1_prefix)
    application.include_router(read_router, prefix=api_settings.api_v1_prefix)
    application.include_router(write_router, prefix=api_settings.api_v1_prefix)
    application.include_router(upload_router, prefix=api_settings.api_v1_prefix)
    application.include_router(privacy_router, prefix=api_settings.api_v1_prefix)
    return application


app = create_app()
