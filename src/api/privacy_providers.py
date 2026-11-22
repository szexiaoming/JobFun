"""Dependency wiring for privacy export and deletion use cases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from src.api.dependencies import get_request_context
from src.api.providers import get_database
from src.api.upload_providers import get_object_store
from src.repositories.contracts import PrivacyRepository
from src.repositories.privacy import DatabasePrivacyRepository
from src.services.context import RequestContext
from src.services.privacy import PrivacyApplicationService
from src.storage.contracts import ObjectStore


async def get_privacy_repository(
    database=Depends(get_database),
) -> PrivacyRepository:
    return DatabasePrivacyRepository(database)


async def get_privacy_application_service(
    context: Annotated[RequestContext, Depends(get_request_context)],
    repository: Annotated[PrivacyRepository, Depends(get_privacy_repository)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> PrivacyApplicationService:
    return PrivacyApplicationService(context, repository, store)
