"""Authenticated, ownership-scoped read-only product routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from src.api.errors import APIError
from src.api.read_providers import get_read_application_service
from src.api.schemas import (
    ApplicationDetailResponse,
    ApplicationSummaryResponse,
    InterviewInsightsResponse,
    InterviewAttemptDetailResponse,
    InterviewQuestionResponse,
    JobDetailResponse,
    JobSummaryResponse,
    ResumeDetailResponse,
    ResumeSummaryResponse,
    WorkbenchResponse,
)
from src.services.read_models import ReadApplicationService


router = APIRouter(tags=["read-models"])
ReadService = Annotated[ReadApplicationService, Depends(get_read_application_service)]
ResourceId = Annotated[int, Path(gt=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/workbench", response_model=WorkbenchResponse)
async def workbench(service: ReadService) -> dict:
    return service.get_workbench()


@router.get("/resumes", response_model=list[ResumeSummaryResponse])
async def resumes(
    service: ReadService,
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[dict]:
    return service.list_resumes(limit=limit, offset=offset)


@router.get("/resumes/{resume_id}", response_model=ResumeDetailResponse)
async def resume_detail(resume_id: ResourceId, service: ReadService) -> dict:
    return _required(service.get_resume(resume_id))


@router.get("/jobs", response_model=list[JobSummaryResponse])
async def jobs(
    service: ReadService,
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[dict]:
    return service.list_jobs(limit=limit, offset=offset)


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def job_detail(job_id: ResourceId, service: ReadService) -> dict:
    return _required(service.get_job(job_id))


@router.get("/applications", response_model=list[ApplicationSummaryResponse])
async def applications(
    service: ReadService,
    limit: Limit = 50,
    offset: Offset = 0,
) -> list[dict]:
    return service.list_applications(limit=limit, offset=offset)


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationDetailResponse,
)
async def application_detail(
    application_id: ResourceId,
    service: ReadService,
) -> dict:
    return _required(service.get_application(application_id))


@router.get(
    "/applications/{application_id}/interview-insights",
    response_model=InterviewInsightsResponse,
)
async def interview_insights(
    application_id: ResourceId,
    service: ReadService,
) -> dict:
    return _required(service.get_interview_insights(application_id))


@router.get(
    "/applications/{application_id}/interview-questions",
    response_model=list[InterviewQuestionResponse],
)
async def interview_questions(
    application_id: ResourceId,
    service: ReadService,
) -> list[dict]:
    return _required(service.list_interview_questions(application_id))


@router.get(
    "/interview-attempts/{attempt_id}",
    response_model=InterviewAttemptDetailResponse,
)
async def interview_attempt_detail(
    attempt_id: ResourceId,
    service: ReadService,
) -> dict:
    return _required(service.get_interview_attempt(attempt_id))


def _required(value):
    if value is None:
        raise APIError(
            status_code=404,
            code="resource_not_found",
            message="请求的资源不存在",
        )
    return value
