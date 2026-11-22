"""Authenticated multipart object upload endpoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Header, Path, UploadFile, status

from src.api.errors import APIError
from src.api.schemas import (
    RetainedAudioDeletionRequest,
    RetainedAudioDeletionResponse,
    RetainedAudioListResponse,
    StoredObjectDeletionResponse,
    StoredObjectResponse,
)
from src.api.upload_providers import (
    get_audio_retention_service,
    get_upload_application_service,
)
from src.services.audio_retention import (
    AudioRetentionError,
    AudioRetentionService,
    AudioRetentionValidationError,
)
from src.services.uploads import (
    UploadApplicationService,
    UploadIdempotencyConflict,
    UploadNotFoundError,
    UploadServiceError,
    UploadValidationError,
)


router = APIRouter(tags=["uploads"])
UploadService = Annotated[
    UploadApplicationService,
    Depends(get_upload_application_service),
]
RetentionService = Annotated[
    AudioRetentionService,
    Depends(get_audio_retention_service),
]
UploadKind = Literal["resume_source", "job_source", "interview_audio"]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
]


@router.post(
    "/uploads/{kind}",
    response_model=StoredObjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_object(
    kind: Annotated[UploadKind, Path()],
    file: Annotated[UploadFile, File()],
    service: UploadService,
    idempotency_key: IdempotencyKey,
) -> dict:
    try:
        return _execute(
            lambda: service.upload(
                kind=kind,
                filename=file.filename or "",
                content_type=file.content_type or "application/octet-stream",
                stream=file.file,
                idempotency_key=idempotency_key,
            )
        )
    finally:
        file.file.close()


@router.get("/uploads/{object_id}", response_model=StoredObjectResponse)
def get_upload(
    object_id: Annotated[int, Path(gt=0)],
    service: UploadService,
) -> dict:
    return _execute(lambda: service.get(object_id))


@router.delete(
    "/uploads/{object_id}",
    response_model=StoredObjectDeletionResponse,
)
def delete_upload(
    object_id: Annotated[int, Path(gt=0)],
    service: UploadService,
) -> dict:
    return _execute(lambda: service.delete(object_id))


@router.get("/retained-audio", response_model=RetainedAudioListResponse)
def list_retained_audio(service: RetentionService) -> dict:
    return _execute_retention(service.list_retained)


@router.delete(
    "/retained-audio",
    response_model=RetainedAudioDeletionResponse,
)
def delete_retained_audio(
    body: RetainedAudioDeletionRequest,
    service: RetentionService,
) -> dict:
    return _execute_retention(lambda: service.delete_batch(body.object_ids))


def _execute(action: Callable[[], dict]) -> dict:
    try:
        return action()
    except UploadNotFoundError as exc:
        raise APIError(
            status_code=404, code=exc.code, message="请求的资源不存在"
        ) from exc
    except UploadIdempotencyConflict as exc:
        raise APIError(
            status_code=409, code=exc.code, message="幂等键已用于不同文件"
        ) from exc
    except UploadValidationError as exc:
        raise APIError(status_code=422, code=exc.code, message=str(exc)) from exc
    except UploadServiceError as exc:
        raise APIError(
            status_code=400, code=exc.code, message="上传操作无法完成"
        ) from exc


def _execute_retention(action: Callable[[], dict]) -> dict:
    try:
        return action()
    except AudioRetentionValidationError as exc:
        raise APIError(status_code=422, code=exc.code, message=str(exc)) from exc
    except AudioRetentionError as exc:
        raise APIError(
            status_code=400,
            code=exc.code,
            message="保留音频操作无法完成",
        ) from exc
