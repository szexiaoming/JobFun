"""Dependency wiring for idempotent write services."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from src.api.dependencies import get_request_context
from src.api.providers import get_database
from src.api.read_providers import get_ownership_repository
from src.api.upload_providers import get_stored_object_repository
from src.db.sqlite_client import Database
from src.repositories.contracts import (
    OperationRepository,
    OwnershipRepository,
    StoredObjectRepository,
)
from src.repositories.operations import SQLiteOperationRepository
from src.services.context import RequestContext
from src.services.write_models import WriteApplicationService


async def get_operation_repository(
    database: Annotated[Database, Depends(get_database)],
) -> OperationRepository:
    return SQLiteOperationRepository(database)


async def get_write_application_service(
    context: Annotated[RequestContext, Depends(get_request_context)],
    database: Annotated[Database, Depends(get_database)],
    ownership: Annotated[OwnershipRepository, Depends(get_ownership_repository)],
    operations: Annotated[OperationRepository, Depends(get_operation_repository)],
    stored_objects: Annotated[
        StoredObjectRepository,
        Depends(get_stored_object_repository),
    ],
) -> WriteApplicationService:
    return WriteApplicationService(
        context, database, ownership, operations, stored_objects
    )
