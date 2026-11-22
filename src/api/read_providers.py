"""Dependency wiring for ownership-scoped read application services."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from src.api.dependencies import get_request_context
from src.api.providers import get_database
from src.db.sqlite_client import Database
from src.repositories.contracts import OwnershipRepository
from src.repositories.sqlite_ownership import SQLiteOwnershipRepository
from src.services.context import RequestContext
from src.services.read_models import ReadApplicationService


async def get_ownership_repository(
    database: Annotated[Database, Depends(get_database)],
) -> OwnershipRepository:
    return SQLiteOwnershipRepository(database)


async def get_read_application_service(
    context: Annotated[RequestContext, Depends(get_request_context)],
    repository: Annotated[OwnershipRepository, Depends(get_ownership_repository)],
) -> ReadApplicationService:
    return ReadApplicationService(context, repository)
