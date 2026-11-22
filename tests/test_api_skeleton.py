"""Acceptance tests for the Iteration 0.20 FastAPI skeleton."""

import asyncio
import sys

import httpx
from fastapi import Depends

from src.api.app import create_app
from src.api.dependencies import get_request_context
from src.api.errors import APIError
from src.services import ApplicationService, BaseApplicationService, RequestContext


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _request(app, method: str, path: str, *, raise_app_exceptions=True, **kwargs):
    async def send():
        transport = httpx.ASGITransport(
            app=app,
            raise_app_exceptions=raise_app_exceptions,
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_live_health_and_version_root_expose_no_user_data():
    skeleton = create_app()
    live = _request(skeleton, "GET", "/health/live")
    version = _request(skeleton, "GET", "/api/v1")

    assert live.status_code == 200
    assert live.json() == {"status": "ok", "service": "JobFun API", "version": "0.31.0"}
    assert live.headers["X-Request-ID"].startswith("req_")
    assert version.status_code == 200
    assert version.json() == {"api_version": "v1", "service": "JobFun API", "version": "0.31.0"}


def test_ready_health_uses_injected_checks_and_returns_503_on_failure():
    ready_app = create_app(readiness_probe=lambda: {"configuration": True})
    failed_app = create_app(
        readiness_probe=lambda: {"configuration": True, "database": False}
    )

    ready = _request(ready_app, "GET", "/health/ready")
    failed = _request(failed_app, "GET", "/health/ready")

    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "checks": {"configuration": "ok"}}
    assert failed.status_code == 503
    assert failed.json() == {
        "status": "not_ready",
        "checks": {"configuration": "ok", "database": "failed"},
    }


def test_safe_request_id_is_preserved_and_invalid_value_is_replaced():
    skeleton = create_app()
    preserved = _request(
        skeleton,
        "GET",
        "/health/live",
        headers={"X-Request-ID": "client_req_12345"},
    )
    replaced = _request(
        skeleton,
        "GET",
        "/health/live",
        headers={"X-Request-ID": "bad value\r\n"},
    )

    assert preserved.headers["X-Request-ID"] == "client_req_12345"
    assert replaced.headers["X-Request-ID"].startswith("req_")
    assert replaced.headers["X-Request-ID"] != "bad value\r\n"


def test_request_context_dependency_stays_transport_independent():
    skeleton = create_app()

    async def trusted_context():
        return RequestContext(
            request_id="req_trusted_context",
            user_id=7,
            username="tester",
            roles=("member",),
        )

    skeleton.dependency_overrides[get_request_context] = trusted_context

    @skeleton.get("/_test/context")
    async def context(context: RequestContext = Depends(get_request_context)):
        return {
            "request_id": context.request_id,
            "user_id": context.user_id,
            "roles": list(context.roles),
        }

    response = _request(skeleton, "GET", "/_test/context")

    assert response.status_code == 200
    assert response.json()["request_id"] == "req_trusted_context"
    assert response.json()["user_id"] == 7
    assert response.json()["roles"] == ["member"]


def test_application_service_contract_accepts_only_trusted_context():
    context = RequestContext(request_id="req_service_test")
    service = BaseApplicationService(context=context)

    assert isinstance(service, ApplicationService)
    assert service.context is context
    assert service.context.user_id is None


def test_expected_and_not_found_errors_use_one_safe_shape():
    skeleton = create_app()

    @skeleton.get("/_test/expected")
    async def expected_error():
        raise APIError(
            status_code=409,
            code="conflict",
            message="请求与当前状态冲突",
        )

    expected = _request(skeleton, "GET", "/_test/expected")
    missing = _request(skeleton, "GET", "/does-not-exist")

    assert expected.status_code == 409
    assert expected.json()["error"]["code"] == "conflict"
    assert expected.json()["error"]["request_id"] == expected.headers["X-Request-ID"]
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "resource_not_found"
    assert missing.json()["error"]["details"] == {}


def test_validation_error_does_not_echo_invalid_input():
    skeleton = create_app()

    @skeleton.get("/_test/validate")
    async def validate(count: int):
        return {"count": count}

    secret_input = "not-an-int-secret-value"
    response = _request(
        skeleton,
        "GET",
        "/_test/validate",
        params={"count": secret_input},
    )

    payload = response.json()
    assert response.status_code == 422
    assert payload["error"]["code"] == "validation_error"
    assert secret_input not in response.text
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]


def test_unexpected_error_is_sanitized():
    skeleton = create_app()

    @skeleton.get("/_test/crash")
    async def crash():
        raise RuntimeError("database-password-and-private-path")

    response = _request(
        skeleton,
        "GET",
        "/_test/crash",
        raise_app_exceptions=False,
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "database-password" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_openapi_keeps_skeleton_contracts_and_only_read_methods():
    response = _request(create_app(), "GET", "/openapi.json")

    paths = set(response.json()["paths"])
    assert {"/health/live", "/health/ready", "/health/worker", "/health/maintenance", "/api/v1", "/api/v1/me"} <= paths
    live_responses = response.json()["paths"]["/health/live"]["get"]["responses"]
    assert live_responses["200"]["content"]["application/json"]["schema"]
    assert live_responses["500"]["content"]["application/json"]["schema"]
    assert "ErrorResponse" in response.json()["components"]["schemas"]
    protected_read_paths = [
        "/api/v1/workbench",
        "/api/v1/resumes",
        "/api/v1/resumes/{resume_id}",
        "/api/v1/jobs",
        "/api/v1/jobs/{job_id}",
        "/api/v1/applications",
        "/api/v1/applications/{application_id}",
        "/api/v1/applications/{application_id}/interview-insights",
    ]
    for path in protected_read_paths:
        assert "get" in response.json()["paths"][path]
