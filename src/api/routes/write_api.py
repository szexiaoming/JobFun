"""Authenticated idempotent writes and durable AI job submission."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, status

from src.api.errors import APIError
from src.api.schemas import (
    ApplicationCreateRequest,
    ApplicationMutationResponse,
    ApplicationUpdateRequest,
    InterviewAttemptCreateRequest,
    InterviewTranscriptionCreateRequest,
    InterviewTranscriptionDraftResponse,
    GapExplanationRequest,
    GapExplanationResponse,
    JobCreateRequest,
    MatchCreateRequest,
    OperationResponse,
    ResumeCreateRequest,
)
from src.api.write_providers import get_write_application_service
from src.services.write_models import (
    IdempotencyConflictError,
    RateLimitError,
    ResourceNotFoundError,
    WriteApplicationService,
    WriteServiceError,
    WriteValidationError,
)


router = APIRouter(tags=["writes"])
WriteService = Annotated[WriteApplicationService, Depends(get_write_application_service)]
ResourceId = Annotated[int, Path(gt=0)]
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
    "/resumes",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_resume(
    body: ResumeCreateRequest,
    service: WriteService,
    idempotency_key: IdempotencyKey,
) -> dict:
    return _execute(
        lambda: service.queue_resume_parse(
            name=body.name,
            text=body.text,
            idempotency_key=idempotency_key,
        )
    )


@router.post(
    "/jobs",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_job(
    body: JobCreateRequest,
    service: WriteService,
    idempotency_key: IdempotencyKey,
) -> dict:
    return _execute(
        lambda: service.queue_job_parse(
            text=body.text,
            source_url=body.source_url,
            idempotency_key=idempotency_key,
        )
    )


@router.post(
    "/matches",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_match(
    body: MatchCreateRequest,
    service: WriteService,
    idempotency_key: IdempotencyKey,
) -> dict:
    return _execute(
        lambda: service.queue_match(
            resume_id=body.resume_id,
            job_id=body.job_id,
            idempotency_key=idempotency_key,
        )
    )


@router.post(
    "/applications/{application_id}/gap-explanations",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_gap_explanation(
    application_id: ResourceId,
    body: GapExplanationRequest,
    service: WriteService,
    idempotency_key: IdempotencyKey,
) -> dict:
    return _execute(lambda: service.queue_gap_explanation(
        application_id=application_id,
        requirement_key=body.requirement_key,
        idempotency_key=idempotency_key,
    ))


@router.get(
    "/gap-explanations/{operation_id}",
    response_model=GapExplanationResponse,
)
async def gap_explanation_result(
    operation_id: ResourceId,
    service: WriteService,
) -> dict:
    return _required_gap(service.get_gap_explanation(operation_id))


@router.post(
    "/applications",
    response_model=ApplicationMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application(
    body: ApplicationCreateRequest,
    service: WriteService,
    idempotency_key: IdempotencyKey,
) -> dict:
    return _execute(
        lambda: service.create_application(
            job_id=body.job_id,
            resume_id=body.resume_id,
            match_id=body.match_id,
            notes=body.notes,
            idempotency_key=idempotency_key,
        )
    )


@router.patch(
    "/applications/{application_id}",
    response_model=ApplicationMutationResponse,
)
async def update_application(
    application_id: ResourceId,
    body: ApplicationUpdateRequest,
    service: WriteService,
    idempotency_key: IdempotencyKey,
) -> dict:
    return _execute(
        lambda: service.update_application(
            application_id,
            changes=body.model_dump(),
            idempotency_key=idempotency_key,
        )
    )


@router.post(
    "/interview-attempts",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_interview_attempt(
    body: InterviewAttemptCreateRequest,
    service: WriteService,
    idempotency_key: IdempotencyKey,
) -> dict:
    return _execute(
        lambda: service.queue_interview_answer(
            application_id=body.application_id,
            question_id=body.question_id,
            answer_text=body.answer_text,
            transcription_operation_id=body.transcription_operation_id,
            retain_audio=body.retain_audio,
            idempotency_key=idempotency_key,
        )
    )


@router.post(
    "/interview-transcriptions",
    response_model=OperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_interview_transcription(
    body: InterviewTranscriptionCreateRequest,
    service: WriteService,
    idempotency_key: IdempotencyKey,
) -> dict:
    return _execute(
        lambda: service.queue_interview_transcription(
            application_id=body.application_id,
            question_id=body.question_id,
            object_id=body.object_id,
            retain_audio=body.retain_audio,
            idempotency_key=idempotency_key,
        )
    )


@router.get(
    "/interview-transcriptions/{operation_id}",
    response_model=InterviewTranscriptionDraftResponse,
)
async def interview_transcription_draft(
    operation_id: ResourceId,
    service: WriteService,
) -> dict:
    draft = service.get_interview_transcription(operation_id)
    if draft is None:
        raise APIError(
            status_code=404,
            code="resource_not_found",
            message="请求的资源不存在",
        )
    return draft


@router.get("/operations/{operation_id}", response_model=OperationResponse)
async def operation_status(operation_id: ResourceId, service: WriteService) -> dict:
    operation = service.get_operation(operation_id)
    if operation is None:
        raise APIError(
            status_code=404,
            code="resource_not_found",
            message="请求的资源不存在",
        )
    return operation


def _execute(action: Callable[[], dict]) -> dict:
    try:
        return action()
    except ResourceNotFoundError as exc:
        raise APIError(
            status_code=404,
            code=exc.code,
            message="请求的资源不存在",
        ) from exc
    except IdempotencyConflictError as exc:
        raise APIError(
            status_code=409,
            code=exc.code,
            message="幂等键已用于不同请求",
        ) from exc
    except RateLimitError as exc:
        raise APIError(
            status_code=429,
            code=exc.code,
            message="操作过于频繁，请稍后重试",
            headers={"Retry-After": "60"},
        ) from exc
    except WriteValidationError as exc:
        raise APIError(
            status_code=422,
            code=exc.code,
            message=str(exc),
        ) from exc
    except WriteServiceError as exc:
        raise APIError(
            status_code=400,
            code=exc.code,
            message="写入操作无法完成",
        ) from exc


def _required_gap(value: dict | None) -> dict:
    if value is None:
        raise APIError(
            status_code=404,
            code="resource_not_found",
            message="请求的资源不存在",
        )
    return value
