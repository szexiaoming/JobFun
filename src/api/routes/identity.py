"""Authenticated identity endpoint without exposing settings or tokens."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_request_context
from src.api.schemas import MeResponse
from src.services.context import RequestContext


router = APIRouter(tags=["identity"])


@router.get("/me", response_model=MeResponse)
async def current_user(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> MeResponse:
    return MeResponse(
        id=int(context.user_id),
        username=context.username,
        roles=list(context.roles),
    )
