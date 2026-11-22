"""Authenticated personal-data export and account deletion endpoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from src.api.errors import APIError
from src.api.privacy_providers import get_privacy_application_service
from src.api.schemas import (
    AccountDeletionRequest,
    AccountDeletionResponse,
    DeletionChallengeResponse,
)
from src.services.privacy import (
    PrivacyApplicationService,
    PrivacyChallengeError,
    PrivacyResourceNotFound,
    PrivacyServiceError,
    PrivacyValidationError,
)


router = APIRouter(tags=["privacy"])
PrivacyService = Annotated[
    PrivacyApplicationService,
    Depends(get_privacy_application_service),
]
DeletionToken = Annotated[
    str,
    Header(alias="Deletion-Token", min_length=32, max_length=256),
]


@router.get("/me/export", response_class=StreamingResponse)
def export_personal_data(service: PrivacyService) -> StreamingResponse:
    package = _execute(service.export)
    return StreamingResponse(
        package.chunks(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "Content-Length": str(package.size_bytes),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(package.close),
    )


@router.post(
    "/me/deletion-challenge",
    response_model=DeletionChallengeResponse,
)
def create_deletion_challenge(response: Response, service: PrivacyService) -> dict:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return _execute(service.create_deletion_challenge)


@router.delete("/me", response_model=AccountDeletionResponse)
def delete_account(
    body: AccountDeletionRequest,
    response: Response,
    service: PrivacyService,
    deletion_token: DeletionToken,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return _execute(
        lambda: service.delete_account(
            deletion_token=deletion_token,
            username=body.username,
            confirmation=body.confirmation,
        )
    )


def _execute(action: Callable):
    try:
        return action()
    except PrivacyResourceNotFound as exc:
        raise APIError(
            status_code=404,
            code=exc.code,
            message="请求的资源不存在",
        ) from exc
    except PrivacyChallengeError as exc:
        raise APIError(
            status_code=409,
            code=exc.code,
            message="删除确认已失效，请重新发起",
        ) from exc
    except PrivacyValidationError as exc:
        raise APIError(
            status_code=422,
            code=exc.code,
            message=str(exc),
        ) from exc
    except PrivacyServiceError as exc:
        raise APIError(
            status_code=400,
            code=exc.code,
            message="隐私操作无法完成",
        ) from exc
