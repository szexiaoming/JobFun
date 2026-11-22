"""Tests for user-supplied experience records and lifecycle auditing."""

import pytest

from src.core.evidence_supplements import (
    EvidenceSupplementError,
    confirm_evidence_supplement,
    create_evidence_supplement,
    get_evidence_supplement_events,
    get_evidence_supplements,
    reject_evidence_supplement,
    update_evidence_supplement,
)
from src.db.models import EvidenceMatch, JobDescription, JobRequirement, MatchResult, Resume
from src.db.sqlite_client import Database


@pytest.fixture
def supplement_db(tmp_path):
    db = Database(tmp_path / "supplements.db")
    resume = Resume(name="Resume", latex_path="")
    resume.id = db.insert("resumes", resume)
    jd = JobDescription(company="Acme", position="Engineer")
    jd.id = db.insert("job_descriptions", jd)
    match = MatchResult(resume_id=resume.id, jd_id=jd.id)
    match.id = db.insert("match_results", match)
    requirement = JobRequirement(
        jd_id=jd.id,
        text="Kubernetes experience",
        normalized_key="kubernetes experience",
    )
    requirement.id = db.insert("job_requirements", requirement)
    evidence = EvidenceMatch(
        match_id=match.id,
        requirement_id=requirement.id,
        status="missing",
        reasoning="No resume evidence.",
    )
    evidence.id = db.insert("evidence_matches", evidence)
    db.test_match_id = match.id
    db.test_requirement_id = requirement.id
    db.test_evidence_id = evidence.id
    yield db
    db.close()


def _create(db):
    return create_evidence_supplement(
        db.test_match_id,
        db.test_requirement_id,
        evidence_match_id=db.test_evidence_id,
        title="Internal Kubernetes migration",
        description="Migrated three internal services to Kubernetes.",
        context_type="work",
        organization="Acme Labs",
        start_date="2024-03",
        end_date="2024-08",
        db=db,
    )


def test_create_draft_is_user_supplied_and_not_automatically_eligible(supplement_db):
    supplement = _create(supplement_db)
    loaded = get_evidence_supplements(supplement_db.test_match_id, db=supplement_db)

    assert supplement.source_type == "user_supplied"
    assert supplement.status == "draft"
    assert supplement.eligible_for_matching is False
    assert supplement.eligible_for_resume_edit is False
    assert loaded[0].id == supplement.id
    assert get_evidence_supplement_events(supplement.id, db=supplement_db)[0].event_type == "created"


def test_confirmation_requires_explicit_attestation(supplement_db):
    supplement = _create(supplement_db)

    with pytest.raises(EvidenceSupplementError, match="attestation is required"):
        confirm_evidence_supplement(
            supplement.id,
            user_attested=False,
            db=supplement_db,
        )


def test_confirmed_supplement_can_match_but_cannot_enter_resume_queue(supplement_db):
    supplement = _create(supplement_db)

    confirmed = confirm_evidence_supplement(
        supplement.id,
        user_attested=True,
        note="I confirm this happened as written.",
        db=supplement_db,
    )

    assert confirmed.status == "confirmed"
    assert confirmed.user_attested is True
    assert confirmed.eligible_for_matching is True
    assert confirmed.eligible_for_resume_edit is False
    events = get_evidence_supplement_events(supplement.id, db=supplement_db)
    assert [event.event_type for event in events] == ["created", "confirmed"]
    assert events[-1].snapshot_json["eligible_for_resume_edit"] is False


def test_update_is_audited_and_confirmed_content_is_locked(supplement_db):
    supplement = _create(supplement_db)
    updated = update_evidence_supplement(
        supplement.id,
        {"description": "Migrated five internal services to Kubernetes."},
        note="Corrected the service count.",
        db=supplement_db,
    )
    confirm_evidence_supplement(
        supplement.id,
        user_attested=True,
        db=supplement_db,
    )

    assert "five" in updated.description
    with pytest.raises(EvidenceSupplementError, match="Only draft"):
        update_evidence_supplement(
            supplement.id,
            {"title": "Changed after confirmation"},
            db=supplement_db,
        )
    events = get_evidence_supplement_events(supplement.id, db=supplement_db)
    assert [event.event_type for event in events] == ["created", "updated", "confirmed"]


def test_rejection_withdraws_matching_eligibility(supplement_db):
    supplement = _create(supplement_db)
    confirm_evidence_supplement(
        supplement.id,
        user_attested=True,
        db=supplement_db,
    )

    rejected = reject_evidence_supplement(
        supplement.id,
        note="I no longer want to use this experience.",
        db=supplement_db,
    )

    assert rejected.status == "rejected"
    assert rejected.user_attested is False
    assert rejected.eligible_for_matching is False
    assert rejected.eligible_for_resume_edit is False


def test_rejects_invalid_relationships_dates_and_context(supplement_db):
    other_jd = JobDescription(company="Other", position="Engineer")
    other_jd.id = supplement_db.insert("job_descriptions", other_jd)
    other_requirement = JobRequirement(
        jd_id=other_jd.id,
        text="Go",
        normalized_key="go",
    )
    other_requirement.id = supplement_db.insert("job_requirements", other_requirement)

    with pytest.raises(EvidenceSupplementError, match="does not belong"):
        create_evidence_supplement(
            supplement_db.test_match_id,
            other_requirement.id,
            title="Example",
            description="Example description",
            db=supplement_db,
        )
    with pytest.raises(EvidenceSupplementError, match="end_date cannot be earlier"):
        create_evidence_supplement(
            supplement_db.test_match_id,
            supplement_db.test_requirement_id,
            title="Example",
            description="Example description",
            context_type="work",
            start_date="2025-01",
            end_date="2024-12",
            db=supplement_db,
        )
    with pytest.raises(EvidenceSupplementError, match="Unsupported supplement context"):
        create_evidence_supplement(
            supplement_db.test_match_id,
            supplement_db.test_requirement_id,
            title="Example",
            description="Example description",
            context_type="invented",
            db=supplement_db,
        )

