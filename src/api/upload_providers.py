"""Dependency wiring for object storage and uploads."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

import config
from src.api.dependencies import get_request_context
from src.api.providers import get_database
from src.repositories.contracts import StoredObjectRepository
from src.repositories.maintenance import RetentionPolicyRepository
from src.repositories.stored_objects import StoredObjectDatabaseRepository
from src.services.audio_retention import AudioRetentionService
from src.services.context import RequestContext
from src.services.maintenance_monitoring import MaintenanceMonitoringService
from src.services.uploads import UploadApplicationService
from src.storage.contracts import ObjectStore
from src.storage.local import LocalObjectStore
from src.storage.s3 import S3ObjectStore


@lru_cache(maxsize=1)
def configured_object_store() -> ObjectStore:
    backend = config.OBJECT_STORAGE_BACKEND
    if backend == "local":
        return LocalObjectStore(config.OBJECT_STORAGE_DIR)
    if backend == "s3":
        return S3ObjectStore(
            config.S3_BUCKET,
            region=config.S3_REGION,
            endpoint_url=config.S3_ENDPOINT_URL,
            kms_key_id=config.S3_KMS_KEY_ID,
        )
    raise RuntimeError(f"Unsupported object storage backend: {backend}")


async def get_object_store() -> ObjectStore:
    return configured_object_store()


async def get_stored_object_repository(
    database=Depends(get_database),
) -> StoredObjectRepository:
    return StoredObjectDatabaseRepository(database)


async def get_upload_application_service(
    context: Annotated[RequestContext, Depends(get_request_context)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
    repository: Annotated[
        StoredObjectRepository,
        Depends(get_stored_object_repository),
    ],
) -> UploadApplicationService:
    return UploadApplicationService(context, store, repository)


async def get_audio_retention_service(
    context: Annotated[RequestContext, Depends(get_request_context)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
    repository: Annotated[
        StoredObjectRepository,
        Depends(get_stored_object_repository),
    ],
    database=Depends(get_database),
) -> AudioRetentionService:
    return AudioRetentionService(
        context,
        store,
        repository,
        maintenance=MaintenanceMonitoringService(database),
        policy_audit=RetentionPolicyRepository(database),
    )
