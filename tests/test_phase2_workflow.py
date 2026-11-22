"""Phase 2 closure tests for workbench visibility and full record linkage."""

from datetime import datetime
from unittest.mock import patch

from src.core.application_context import get_application_context
from src.core.evidence_matcher import get_evidence_matches
from src.core.progress_manager import create_application, set_next_action
from src.core.workbench import get_workbench_summary
from src.db.models import (
    Application,
    EvidenceMatch,
    JobDescription,
    JobRequirement,
    MatchResult,
    Resume,
)
from src.db.sqlite_client import Database
from ui.jobs import build_job_catalog


def test_workbench_sorts_overdue_actions_and_upcoming_interviews(tmp_path):
    db = Database(tmp_path / "workbench.db")
    jd = JobDescription(company="Acme", position="Engineer")
    jd.id = db.insert("job_descriptions", jd)
    overdue = Application(
        jd_id=jd.id,
        resume_id=1,
        status="applied",
        next_step="Reply to recruiter",
        next_step_due="2026-11-19 12:00",
        interview_at="2026-11-22 10:00",
    )
    overdue.id = db.insert("applications", overdue)
    later = Application(
        jd_id=jd.id,
        resume_id=1,
        status="interview",
        next_step="Prepare examples",
        next_step_due="2026-11-23 18:00",
    )
    later.id = db.insert("applications", later)

    summary = get_workbench_summary(
        db=db,
        now=datetime(2026, 11, 20, 9, 0),
    )
    db.close()

    assert summary.total_applications == 2
    assert summary.active_applications == 2
    assert [item.application_id for item in summary.pending_actions] == [
        overdue.id,
        later.id,
    ]
    assert [item.application_id for item in summary.overdue_actions] == [overdue.id]
    assert [item.application_id for item in summary.upcoming_interviews] == [overdue.id]


def test_workbench_excludes_terminal_and_out_of_window_items(tmp_path):
    db = Database(tmp_path / "window.db")
    jd = JobDescription(company="Acme", position="Engineer")
    jd.id = db.insert("job_descriptions", jd)
    app = Application(
        jd_id=jd.id,
        resume_id=1,
        status="rejected",
        interview_at="2026-12-20 10:00",
    )
    db.insert("applications", app)

    summary = get_workbench_summary(
        db=db,
        now=datetime(2026, 11, 20, 9, 0),
    )
    db.close()

    assert summary.active_applications == 0
    assert summary.upcoming_interviews == []


def test_job_catalog_keeps_application_ids_for_direct_opening():
    catalog = build_job_catalog(
        [{"id": 8, "company": "Acme", "position": "Engineer", "structured_json": {}}],
        [],
        [
            {"id": 21, "jd_id": 8, "status": "saved"},
            {"id": 22, "jd_id": 8, "status": "interview"},
        ],
    )

    assert [application["id"] for application in catalog[0].applications] == [21, 22]
    assert catalog[0].application_count == 2


def test_complete_phase2_chain_preserves_all_record_ids(tmp_path):
    db = Database(tmp_path / "phase2.db")
    resume = Resume(
        name="Backend Resume",
        latex_path="",
        structured_json={
            "sections": [{
                "title": "Experience",
                "entries": [{"header": "Engineer", "bullets": ["Built Python APIs"]}],
            }],
        },
    )
    resume.id = db.insert("resumes", resume)
    jd = JobDescription(
        company="Northstar",
        position="Backend Engineer",
        structured_json={"required_skills": ["Python"]},
    )
    jd.id = db.insert("job_descriptions", jd)
    match = MatchResult(resume_id=resume.id, jd_id=jd.id, total_score=80)
    match.id = db.insert("match_results", match)
    requirement = JobRequirement(
        jd_id=jd.id,
        text="Python",
        normalized_key="python",
        priority=1,
    )
    requirement.id = db.insert("job_requirements", requirement)
    evidence = EvidenceMatch(
        match_id=match.id,
        requirement_id=requirement.id,
        status="proven",
        evidence_json=[{
            "text": "Built Python APIs",
            "section": "Experience",
            "entry": "Engineer",
            "bullet_index": 0,
            "source_id": "bul_demo",
        }],
        reasoning="Direct resume evidence.",
    )
    evidence.id = db.insert("evidence_matches", evidence)

    with patch("src.core.progress_manager.get_db", return_value=db):
        application = create_application(
            jd_id=jd.id,
            resume_id=resume.id,
            match_id=match.id,
        )
        set_next_action(
            application.id,
            "Prepare Python project examples",
            "2026-11-25 18:00",
        )

    context = get_application_context(application.id, db=db)
    stored_evidence = get_evidence_matches(match.id, db=db)
    summary = get_workbench_summary(
        db=db,
        now=datetime(2026, 11, 20, 9, 0),
    )
    db.close()

    assert context.application.jd_id == jd.id
    assert context.application.resume_id == resume.id
    assert context.application.match_id == match.id
    assert context.job.id == jd.id
    assert context.resume.id == resume.id
    assert context.match.id == match.id
    assert stored_evidence[0].requirement_id == requirement.id
    assert summary.pending_actions[0].application_id == application.id


def test_invalid_stored_dates_do_not_break_workbench_summary(tmp_path):
    db = Database(tmp_path / "invalid_date.db")
    app = Application(
        jd_id=999,
        resume_id=999,
        status="saved",
        next_step="Follow up",
        next_step_due="not-a-date",
        interview_at="also-invalid",
    )
    app.id = db.insert("applications", app)

    summary = get_workbench_summary(db=db, now=datetime(2026, 11, 20, 9, 0))
    db.close()

    assert summary.pending_actions[0].application_id == app.id
    assert summary.pending_actions[0].is_overdue is False
    assert summary.upcoming_interviews == []
