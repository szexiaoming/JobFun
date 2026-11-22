"""Tests for evidence source IDs and user review audit records."""

import pytest

from src.core.evidence_matcher import (
    EvidenceMatcherError,
    get_evidence_reviews,
    record_evidence_review,
    save_evidence_matches,
)
from src.db.models import JobDescription, JobRequirement, MatchResult, Resume
from src.db.sqlite_client import Database


RESUME_JSON = {
    "sections": [
        {
            "title": "Experience",
            "entries": [
                {
                    "header": "Engineer @ Acme",
                    "bullets": [
                        "Built Python APIs on AWS",
                        "Reduced request latency by 30%",
                    ],
                }
            ],
        }
    ]
}


@pytest.fixture
def saved_evidence(tmp_path):
    db = Database(tmp_path / "review.db")
    resume = Resume(name="Resume", latex_path="", structured_json=RESUME_JSON)
    resume.id = db.insert("resumes", resume)
    jd = JobDescription(company="Acme", position="Engineer", raw_text="Python")
    jd.id = db.insert("job_descriptions", jd)
    match = MatchResult(resume_id=resume.id, jd_id=jd.id)
    match.id = db.insert("match_results", match)
    requirement = JobRequirement(
        jd_id=jd.id,
        category="required",
        text="Python",
        normalized_key="python",
        priority=1,
    )
    requirement.id = db.insert("job_requirements", requirement)
    payload = {
        "matches": [
            {
                "requirement_id": requirement.id,
                "status": "proven",
                "evidence": [
                    {
                        "text": "Built Python APIs",
                        "section": "Experience",
                        "entry": "Engineer @ Acme",
                        "bullet_index": 0,
                    }
                ],
                "reasoning": "The resume explicitly mentions Python APIs.",
                "confidence": 0.95,
                "needs_user_confirmation": False,
                "recommended_action": "Keep this evidence visible.",
            }
        ]
    }
    saved = save_evidence_matches(
        match.id,
        [requirement],
        RESUME_JSON,
        payload,
        db=db,
    )[0]
    yield db, saved
    db.close()


def test_saved_evidence_contains_stable_source_id(saved_evidence):
    _, saved = saved_evidence

    assert saved.evidence_json[0]["source_id"].startswith("bul_")


def test_confirm_and_reject_append_review_history(saved_evidence):
    db, saved = saved_evidence

    confirmed, first_review = record_evidence_review(
        saved.id,
        "confirmed",
        note="This is accurate.",
        db=db,
    )
    rejected, second_review = record_evidence_review(
        saved.id,
        "rejected",
        note="The wording overstates my role.",
        db=db,
    )
    history = get_evidence_reviews(saved.id, db=db)

    assert confirmed.user_status == "confirmed"
    assert rejected.user_status == "rejected"
    assert first_review.previous_status == "proven"
    assert second_review.previous_evidence_json == saved.evidence_json
    assert [item.action for item in history] == ["confirmed", "rejected"]


def test_grounded_correction_updates_match_and_preserves_audit(saved_evidence):
    db, saved = saved_evidence
    correction = [
        {
            "text": "Reduced request latency",
            "section": "Experience",
            "entry": "Engineer @ Acme",
            "bullet_index": 1,
        }
    ]

    updated, review = record_evidence_review(
        saved.id,
        "corrected",
        corrected_status="partial",
        corrected_evidence=correction,
        resume_json=RESUME_JSON,
        note="This is the more relevant example.",
        db=db,
    )

    assert updated.status == "partial"
    assert updated.user_status == "corrected"
    assert updated.needs_user_confirmation is False
    assert updated.evidence_json[0]["source_id"].startswith("bul_")
    assert review.previous_status == "proven"
    assert review.previous_evidence_json == saved.evidence_json
    assert review.corrected_status == "partial"
    assert review.corrected_evidence_json == updated.evidence_json


def test_correction_rejects_fabricated_resume_evidence(saved_evidence):
    db, saved = saved_evidence

    with pytest.raises(EvidenceMatcherError, match="not grounded"):
        record_evidence_review(
            saved.id,
            "corrected",
            corrected_status="proven",
            corrected_evidence=[
                {
                    "text": "Led a global Kubernetes migration",
                    "section": "Experience",
                    "entry": "Engineer @ Acme",
                    "bullet_index": 0,
                }
            ],
            resume_json=RESUME_JSON,
            db=db,
        )

    assert db.count("evidence_reviews") == 0


def test_non_correction_cannot_smuggle_replacement_evidence(saved_evidence):
    db, saved = saved_evidence

    with pytest.raises(EvidenceMatcherError, match="only valid for a corrected review"):
        record_evidence_review(
            saved.id,
            "confirmed",
            corrected_status="missing",
            corrected_evidence=[],
            db=db,
        )

