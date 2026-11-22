"""End-to-end read-model parity and isolation tests for Iteration 0.22."""

import json

from src.db.models import (
    Application,
    InterviewAttempt,
    InterviewQuestion,
    JobDescription,
    MatchResult,
    Resume,
    User,
)
from src.db.sqlite_client import Database
from src.repositories.sqlite_ownership import SQLiteOwnershipRepository
from src.services.context import RequestContext
from src.services.read_models import ReadApplicationService
from tests.test_api_authentication import _authenticated_app, _issue
from tests.test_api_skeleton import _request


def _seed_chain(database: Database, user_id: int, suffix: str) -> dict[str, int]:
    resume_id = database.insert(
        "resumes",
        Resume(
            user_id=user_id,
            name=f"Resume {suffix}",
            latex_path=f"C:/private/{suffix}/resume.tex",
            pdf_path=f"C:/private/{suffix}/resume.pdf",
            structured_json={
                "sections": [{
                    "title": "Experience",
                    "entries": [{"header": suffix, "bullets": [f"Built API {suffix}"]}],
                }],
            },
        ),
    )
    job_id = database.insert(
        "job_descriptions",
        JobDescription(
            user_id=user_id,
            company=f"Company {suffix}",
            position="Backend Engineer",
            raw_text=f"Python role {suffix}",
            source_file=f"C:/private/{suffix}/job.pdf",
            source_url=f"https://example.test/{suffix}",
            structured_json={"company": f"Company {suffix}", "required_skills": ["Python"]},
        ),
    )
    match_id = database.insert(
        "match_results",
        MatchResult(
            resume_id=resume_id,
            jd_id=job_id,
            total_score=82,
            skill_score=84,
            experience_score=80,
            education_score=75,
            soft_skill_score=81,
            culture_score=79,
            matched_skills=["Python"],
            missing_skills=["Kafka"],
            risks=["Limited scale evidence"],
            raw_report=f"private model report {suffix}",
        ),
    )
    application_id = database.insert(
        "applications",
        Application(
            user_id=user_id,
            jd_id=job_id,
            resume_id=resume_id,
            match_id=match_id,
            status="interview",
            notes=f"Private notes {suffix}",
            next_step=f"Prepare examples {suffix}",
        ),
    )
    question_id = database.insert(
        "interview_questions",
        InterviewQuestion(
            match_id=match_id,
            category="technical",
            question=f"Explain retries {suffix}",
        ),
    )
    attempt_id = database.insert(
        "interview_attempts",
        InterviewAttempt(
            question_id=question_id,
            application_id=application_id,
            answer_text=f"Answer {suffix}",
            completeness_score=4,
            truthfulness_score=4,
            technical_score=3,
            structure_score=4,
            feedback_json={"summary": "Good", "next_practice": "Add metrics"},
        ),
    )
    return {
        "resume": resume_id,
        "job": job_id,
        "match": match_id,
        "application": application_id,
        "question": question_id,
        "attempt": attempt_id,
    }


def _service(database: Database, user_id: int, username: str) -> ReadApplicationService:
    return ReadApplicationService(
        RequestContext(
            request_id=f"req_local_{user_id}",
            user_id=user_id,
            username=username,
        ),
        SQLiteOwnershipRepository(database),
    )


def test_http_read_models_equal_direct_application_service_results(tmp_path):
    database = Database(tmp_path / "read-parity.db")
    database.update("users", 1, {"username": "alice"})
    chain = _seed_chain(database, 1, "alice")
    token = _issue(database).token
    application = _authenticated_app(database)
    service = _service(database, 1, "alice")
    headers = {"Authorization": f"Bearer {token}"}

    cases = [
        ("/api/v1/workbench", service.get_workbench()),
        ("/api/v1/resumes", service.list_resumes()),
        (f"/api/v1/resumes/{chain['resume']}", service.get_resume(chain["resume"])),
        ("/api/v1/jobs", service.list_jobs()),
        (f"/api/v1/jobs/{chain['job']}", service.get_job(chain["job"])),
        ("/api/v1/applications", service.list_applications()),
        (
            f"/api/v1/applications/{chain['application']}",
            service.get_application(chain["application"]),
        ),
        (
            f"/api/v1/applications/{chain['application']}/interview-insights",
            service.get_interview_insights(chain["application"]),
        ),
        (
            f"/api/v1/applications/{chain['application']}/interview-questions",
            service.list_interview_questions(chain["application"]),
        ),
        (
            f"/api/v1/interview-attempts/{chain['attempt']}",
            service.get_interview_attempt(chain["attempt"]),
        ),
    ]
    for path, expected in cases:
        response = _request(application, "GET", path, headers=headers)
        assert response.status_code == 200, path
        assert response.json() == expected, path
    database.close()


def test_lists_and_details_never_cross_user_boundary(tmp_path):
    database = Database(tmp_path / "read-isolation.db")
    database.update("users", 1, {"username": "alice"})
    user_two = database.insert("users", User(username="bob"))
    alice = _seed_chain(database, 1, "alice")
    bob = _seed_chain(database, user_two, "bob")
    alice_token = _issue(database, user_id=1, label="alice").token
    bob_token = _issue(database, user_id=user_two, label="bob").token
    application = _authenticated_app(database)

    alice_headers = {"Authorization": f"Bearer {alice_token}"}
    bob_headers = {"Authorization": f"Bearer {bob_token}"}
    for path in ("resumes", "jobs", "applications"):
        alice_list = _request(application, "GET", f"/api/v1/{path}", headers=alice_headers)
        bob_list = _request(application, "GET", f"/api/v1/{path}", headers=bob_headers)
        assert len(alice_list.json()) == 1
        assert len(bob_list.json()) == 1
        assert alice_list.json()[0]["id"] != bob_list.json()[0]["id"]

    foreign_paths = [
        f"/api/v1/resumes/{alice['resume']}",
        f"/api/v1/jobs/{alice['job']}",
        f"/api/v1/applications/{alice['application']}",
        f"/api/v1/applications/{alice['application']}/interview-insights",
        f"/api/v1/applications/{alice['application']}/interview-questions",
        f"/api/v1/interview-attempts/{alice['attempt']}",
    ]
    for path in foreign_paths:
        response = _request(application, "GET", path, headers=bob_headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"
    assert bob["application"] != alice["application"]
    database.close()


def test_read_responses_exclude_server_paths_and_internal_reports(tmp_path):
    database = Database(tmp_path / "read-safety.db")
    chain = _seed_chain(database, 1, "safety")
    token = _issue(database).token
    application = _authenticated_app(database)
    headers = {"Authorization": f"Bearer {token}"}

    responses = [
        _request(application, "GET", f"/api/v1/resumes/{chain['resume']}", headers=headers),
        _request(application, "GET", f"/api/v1/jobs/{chain['job']}", headers=headers),
        _request(
            application,
            "GET",
            f"/api/v1/applications/{chain['application']}",
            headers=headers,
        ),
    ]
    combined = json.dumps([response.json() for response in responses])
    assert all(response.status_code == 200 for response in responses)
    assert "C:/private" not in combined
    assert "private model report" not in combined
    assert all(field not in combined for field in ("latex_path", "pdf_path", "source_file", "raw_report"))
    database.close()


def test_read_routes_require_auth_validate_pagination_and_expose_only_get(tmp_path):
    database = Database(tmp_path / "read-contract.db")
    token = _issue(database).token
    application = _authenticated_app(database)

    unauthenticated = _request(application, "GET", "/api/v1/resumes")
    invalid_page = _request(
        application,
        "GET",
        "/api/v1/resumes?limit=101",
        headers={"Authorization": f"Bearer {token}"},
    )
    openapi = _request(application, "GET", "/openapi.json").json()

    assert unauthenticated.status_code == 401
    assert invalid_page.status_code == 422
    expected_read_paths = {
        "/api/v1/workbench",
        "/api/v1/resumes",
        "/api/v1/resumes/{resume_id}",
        "/api/v1/jobs",
        "/api/v1/jobs/{job_id}",
        "/api/v1/applications",
        "/api/v1/applications/{application_id}",
        "/api/v1/applications/{application_id}/interview-insights",
    }
    read_paths = {
        path: openapi["paths"][path]
        for path in expected_read_paths
    }
    assert len(read_paths) == 8
    for operations in read_paths.values():
        assert "get" in operations
        assert operations["get"]["security"] == [{"BearerAuth": []}]
    database.close()


def test_read_service_rejects_anonymous_context(tmp_path):
    database = Database(tmp_path / "anonymous-service.db")
    try:
        ReadApplicationService(
            RequestContext(request_id="req_anonymous"),
            SQLiteOwnershipRepository(database),
        )
    except ValueError as exc:
        assert "authenticated" in str(exc)
    else:
        raise AssertionError("Anonymous read service must be rejected")
    database.close()
