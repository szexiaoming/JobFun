"""Translate authenticated HTTP requests into service inputs."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.errors import APIError
from src.api.providers import get_authentication_service
from src.services.authentication import AuthenticationService
from src.services.context import RequestContext


bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")


async def get_request_context(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
    authentication: Annotated[
        AuthenticationService,
        Depends(get_authentication_service),
    ],
) -> RequestContext:
    """Authenticate a bearer token and build a trusted service context."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    principal = authentication.authenticate(credentials.credentials)
    if principal is None:
        raise _unauthorized()
    return RequestContext(
        request_id=str(request.state.request_id),
        user_id=principal.user_id,
        username=principal.username,
        roles=principal.roles,
        idempotency_key=None,
    )


def _unauthorized() -> APIError:
    return APIError(
        status_code=401,
        code="authentication_required",
        message="需要有效的身份凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
