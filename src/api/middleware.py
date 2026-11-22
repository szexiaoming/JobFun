"""Request metadata middleware."""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response


_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def _resolve_request_id(candidate: str | None) -> str:
    if candidate and _SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return f"req_{uuid.uuid4().hex}"


def register_request_id_middleware(app: FastAPI, header_name: str) -> None:
    @app.middleware("http")
    async def add_request_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _resolve_request_id(request.headers.get(header_name))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[header_name] = request_id
        return response
