"""Tests for the standalone Evidence Matcher data contract."""

from unittest.mock import MagicMock, patch

import pytest

from src.ai.prompts.evidence_matching import (
    EVIDENCE_MATCH_OUTPUT_SCHEMA,
    build_evidence_match_message,
)
from src.core.evidence_matcher import (
    EvidenceMatcherError,
    extract_job_requirements,
    get_evidence_matches,
    get_job_requirements,
    prepare_job_requirements,
    run_evidence_match,
    save_evidence_matches,
    validate_evidence_output,
)
from src.db.models import JobDescription, MatchResult, Resume
from src.db.sqlite_client import Database


JD = {
    "required_skills": ["Python", "AWS"],
    "preferred_skills": ["Docker", "Python"],
    "years_experience": 3,
    "education": "B.S. in Computer Science",
    "responsibilities": ["Build reliable APIs"],
    "soft_skills": ["Cross-team communication"],
}

RESUME = {
    "sections": [
        {
            "title": "Experience",
            "entries": [
                {
                    "header": "Engineer @ Acme",
                    "bullets": [
                        "Built Python APIs on AWS for internal services",
                        "Worked with product and platform teams",
                    ],
                }
            ],
        },
        {
            "title": "Education",
            "entries": [
                {
                    "header": "B.S. in Computer Science",
                    "bullets": [],
                }
            ],
        },
    ]
}


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "evidence.db")
    resume = Resume(name="Evidence Resume", latex_path="", structured_json=RESUME)
    resume.id = db.insert("resumes", resume)
    jd = JobDescription(
        company="TestCorp",
        position="Engineer",
        raw_text="Test JD",
        structured_json=JD,
    )
    jd.id = db.insert("job_descriptions", jd)
    match = MatchResult(resume_id=resume.id, jd_id=jd.id, total_score=70)
    match.id = db.insert("match_results", match)
    db.test_jd_id = jd.id
    db.test_match_id = match.id
    yield db
    db.close()


def _payload(requirements):
    matches = []
    for requirement in requirements:
        evidence = []
        status = "missing"
        confidence = 0.25

        if requirement.normalized_key in {"python", "aws"}:
            status = "proven"
            confidence = 0.95
            evidence = [{
                "text": "Built Python APIs on AWS",
                "section": "Experience",
                "entry": "Engineer @ Acme",
                "bullet_index": 0,
            }]
        elif requirement.category == "responsibility":
            status = "proven"
            confidence = 0.9
            evidence = [{
                "text": "Built Python APIs on AWS for internal services",
                "section": "Experience",
                "entry": "Engineer @ Acme",
                "bullet_index": 0,
            }]
        elif requirement.category == "education":
            status = "proven"
            confidence = 0.98
            evidence = [{
                "text": "B.S. in Computer Science",
                "section": "Education",
                "entry": "B.S. in Computer Science",
                "bullet_index": None,
            }]

        matches.append({
            "requirement_id": requirement.id,
            "status": status,
            "evidence": evidence,
            "reasoning": "Grounded comparison with the supplied resume.",
            "confidence": confidence,
            "needs_user_confirmation": False,
            "recommended_action": "Prepare an interview example." if evidence else "Do not add unsupported claims.",
        })
    return {"matches": matches}


def test_extract_requirements_is_stable_and_deduplicated():
    requirements = extract_job_requirements(7, JD)

    assert len(requirements) == 7
    assert [item.priority for item in requirements] == [1, 1, 1, 2, 2, 2, 3]
    assert sum(item.normalized_key == "python" for item in requirements) == 1
    assert {item.category for item in requirements} <= {
        "responsibility", "required", "preferred", "education", "experience"
    }
    assert requirements[0].source_span == "required_skills[0]"


def test_prepare_and_reload_requirements(database):
    created = prepare_job_requirements(database.test_jd_id, JD, db=database)
    loaded = get_job_requirements(database.test_jd_id, db=database)
    reused = prepare_job_requirements(
        database.test_jd_id,
        {"required_skills": ["Go"]},
        db=database,
    )

    assert len(created) == len(loaded) == len(reused) == 7
    assert all(item.id for item in created)
    assert {item.normalized_key for item in loaded} == {
        item.normalized_key for item in created
    }
    assert "go" not in {item.normalized_key for item in reused}


def test_prepare_requires_existing_job_description(database):
    with pytest.raises(EvidenceMatcherError, match="Job description not found"):
        prepare_job_requirements(9999, JD, db=database)


def test_output_contract_and_prompt_are_explicit():
    item_schema = EVIDENCE_MATCH_OUTPUT_SCHEMA["properties"]["matches"]["items"]
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["properties"]["status"]["enum"]) == {
        "proven", "partial", "missing", "uncertain"
    }

    message = build_evidence_match_message(
        [{"requirement_id": 1, "category": "required", "text": "Python"}],
        RESUME,
    )
    assert "requirement_id" in message["user"]
    assert "untrusted data" in message["system"]
    assert "do not paraphrase" in message["system"]


def test_validate_complete_grounded_output(database):
    requirements = prepare_job_requirements(database.test_jd_id, JD, db=database)

    matches = validate_evidence_output(
        _payload(requirements),
        requirements,
        RESUME,
        match_id=database.test_match_id,
    )

    assert len(matches) == len(requirements)
    assert any(item.status == "proven" for item in matches)
    assert any(item.status == "missing" for item in matches)
    assert all(0 <= item.confidence <= 1 for item in matches)
    assert all(
        source["source_id"]
        for item in matches
        for source in item.evidence_json
    )


def test_rejects_evidence_not_found_in_resume(database):
    requirements = prepare_job_requirements(database.test_jd_id, JD, db=database)
    payload = _payload(requirements)
    first_grounded = next(item for item in payload["matches"] if item["evidence"])
    first_grounded["evidence"][0]["text"] = "Led Kubernetes migration at global scale"

    with pytest.raises(EvidenceMatcherError, match="not grounded"):
        validate_evidence_output(
            payload,
            requirements,
            RESUME,
            match_id=database.test_match_id,
        )


def test_rejects_incomplete_or_duplicate_coverage(database):
    requirements = prepare_job_requirements(database.test_jd_id, JD, db=database)
    incomplete = _payload(requirements)
    incomplete["matches"].pop()

    with pytest.raises(EvidenceMatcherError, match="does not cover"):
        validate_evidence_output(
            incomplete,
            requirements,
            RESUME,
            match_id=database.test_match_id,
        )

    duplicate = _payload(requirements)
    duplicate["matches"].append(dict(duplicate["matches"][0]))
    with pytest.raises(EvidenceMatcherError, match="Duplicate"):
        validate_evidence_output(
            duplicate,
            requirements,
            RESUME,
            match_id=database.test_match_id,
        )


def test_uncertain_result_requires_confirmation(database):
    requirements = prepare_job_requirements(database.test_jd_id, JD, db=database)
    payload = _payload(requirements)
    payload["matches"][0].update({
        "status": "uncertain",
        "needs_user_confirmation": False,
    })

    with pytest.raises(EvidenceMatcherError, match="require user confirmation"):
        validate_evidence_output(
            payload,
            requirements,
            RESUME,
            match_id=database.test_match_id,
        )


def test_save_replaces_existing_matches_after_validation(database):
    requirements = prepare_job_requirements(database.test_jd_id, JD, db=database)
    first = save_evidence_matches(
        database.test_match_id,
        requirements,
        RESUME,
        _payload(requirements),
        db=database,
    )
    second = save_evidence_matches(
        database.test_match_id,
        requirements,
        RESUME,
        _payload(requirements),
        db=database,
    )
    loaded = get_evidence_matches(database.test_match_id, db=database)

    assert len(first) == len(second) == len(loaded) == len(requirements)
    assert database.count("evidence_matches") == len(requirements)
    assert isinstance(loaded[0].evidence_json, list)


def test_save_rejects_requirements_from_another_jd(database):
    other_jd = JobDescription(
        company="OtherCorp",
        position="Engineer",
        raw_text="Other JD",
        structured_json=JD,
    )
    other_jd.id = database.insert("job_descriptions", other_jd)
    other_requirements = prepare_job_requirements(other_jd.id, JD, db=database)

    with pytest.raises(EvidenceMatcherError, match="do not belong"):
        save_evidence_matches(
            database.test_match_id,
            other_requirements,
            RESUME,
            _payload(other_requirements),
            db=database,
        )


def test_run_evidence_match_uses_reasoning_model_and_persists(database):
    requirements = prepare_job_requirements(database.test_jd_id, JD, db=database)
    client = MagicMock()
    client._call.return_value = _payload(requirements)

    with patch("src.core.evidence_matcher.get_ai_client", return_value=client):
        results = run_evidence_match(
            database.test_match_id,
            database.test_jd_id,
            RESUME,
            requirements=requirements,
            db=database,
        )

    assert len(results) == len(requirements)
    assert client._call.call_args.kwargs["model"]
    assert database.count("evidence_matches") == len(requirements)
