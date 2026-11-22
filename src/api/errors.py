"""Stable, non-sensitive HTTP error mapping."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.schemas import ErrorBody, ErrorResponse
from src.utils.logger import logger


class APIError(Exception):
    """Expected API failure with a public error code and safe message."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "request_unavailable"))


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    payload = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            request_id=request_id,
            details=details or {},
        )
    )
    response = JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )
    header_name = request.app.state.api_settings.request_id_header
    response.headers[header_name] = request_id
    for name, value in (headers or {}).items():
        response.headers[name] = value
    return response


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        safe_errors = [
            {
                "location": [str(part) for part in error.get("loc", ())],
                "type": str(error.get("type", "validation_error")),
                "message": str(error.get("msg", "输入无效")),
            }
            for error in exc.errors()
        ]
        return _error_response(
            request,
            status_code=422,
            code="validation_error",
            message="请求参数无效",
            details={"fields": safe_errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        if exc.status_code == 404:
            code = "resource_not_found"
            message = "请求的资源不存在"
        else:
            code = "http_error"
            message = "请求无法完成"
        return _error_response(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_api_error",
            extra={
                "event": "unhandled_api_error",
                "request_id": _request_id(request),
                "error_type": type(exc).__name__,
                "status": 500,
            },
        )
        return _error_response(
            request,
            status_code=500,
            code="internal_error",
            message="服务器暂时无法处理请求",
        )
