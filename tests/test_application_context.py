"""Tests for historical JD, resume, and match bindings on applications."""

import pytest

from src.core.application_context import (
    ApplicationContextError,
    build_resume_outline,
    get_application_context,
)
from src.db.models import Application, JobDescription, MatchResult, Resume
from src.db.sqlite_client import Database


@pytest.fixture
def context_db(tmp_path):
    db = Database(tmp_path / "context.db")
    old_resume = Resume(
        name="Backend Resume",
        base_version=1,
        latex_path="",
        structured_json={
            "sections": [{
                "title": "Experience",
                "entries": [{
                    "header": "Engineer @ Acme",
                    "bullets": ["Built APIs"],
                }],
            }],
        },
    )
    old_resume.id = db.insert("resumes", old_resume)
    current_resume = Resume(
        name="Current Resume",
        base_version=2,
        latex_path="",
        structured_json={"sections": []},
    )
    current_resume.id = db.insert("resumes", current_resume)
    jd = JobDescription(company="Northstar", position="Backend Engineer")
    jd.id = db.insert("job_descriptions", jd)
    match = MatchResult(
        resume_id=old_resume.id,
        jd_id=jd.id,
        total_score=81,
    )
    match.id = db.insert("match_results", match)
    application = Application(
        jd_id=jd.id,
        resume_id=old_resume.id,
        match_id=match.id,
    )
    application.id = db.insert("applications", application)
    db.old_resume_id = old_resume.id
    db.current_resume_id = current_resume.id
    db.test_jd_id = jd.id
    db.test_match_id = match.id
    db.test_application_id = application.id
    yield db
    db.close()


def test_context_loads_exact_historical_bindings(context_db):
    context = get_application_context(
        context_db.test_application_id,
        db=context_db,
    )

    assert context.resume.id == context_db.old_resume_id
    assert context.resume.name == "Backend Resume"
    assert context.resume.base_version == 1
    assert context.job.id == context_db.test_jd_id
    assert context.match.id == context_db.test_match_id
    assert context.issues == []


def test_missing_bound_resume_never_falls_back_to_newer_resume(context_db):
    context_db.delete("resumes", context_db.old_resume_id)

    context = get_application_context(
        context_db.test_application_id,
        db=context_db,
    )

    assert context.resume is None
    assert any("resume_id" in issue for issue in context.issues)
    assert all(
        str(context_db.current_resume_id) not in issue
        for issue in context.issues
    )


def test_mismatched_match_report_is_not_exposed(context_db):
    wrong_match = MatchResult(
        resume_id=context_db.current_resume_id,
        jd_id=context_db.test_jd_id,
        total_score=99,
    )
    wrong_match.id = context_db.insert("match_results", wrong_match)
    context_db.update(
        "applications",
        context_db.test_application_id,
        {"match_id": wrong_match.id},
    )

    context = get_application_context(
        context_db.test_application_id,
        db=context_db,
    )

    assert context.match is None
    assert any("不一致" in issue for issue in context.issues)


def test_missing_optional_match_does_not_replace_it_with_latest(context_db):
    context_db.update(
        "applications",
        context_db.test_application_id,
        {"match_id": 0},
    )

    context = get_application_context(
        context_db.test_application_id,
        db=context_db,
    )

    assert context.match is None
    assert context_db.test_match_id != 0


def test_resume_outline_supports_legacy_and_source_aware_bullets():
    outline = build_resume_outline({
        "sections": [{
            "title": "Projects",
            "entries": [{
                "header": "JobFun",
                "bullets": [
                    "Built an evidence matcher",
                    {"text": "Added stable source IDs", "source_id": "bul_1"},
                ],
            }],
        }],
    })

    assert outline[0]["title"] == "Projects"
    assert outline[0]["entries"][0]["bullets"] == [
        "Built an evidence matcher",
        "Added stable source IDs",
    ]


def test_unknown_application_is_rejected(context_db):
    with pytest.raises(ApplicationContextError, match="Application not found"):
        get_application_context(9999, db=context_db)
