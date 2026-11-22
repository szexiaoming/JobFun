"""Requirement extraction, evidence validation, and persistence.

This module is intentionally independent from the existing score-based match
flow. A later iteration can connect it to the UI without changing this data
contract.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from config import get_active_model
from src.ai.client import AIClientError, get_ai_client
from src.ai.prompts.evidence_matching import build_evidence_match_message
from src.core.source_locator import assign_source_ids, bullet_text
from src.db.models import EvidenceMatch, EvidenceReview, JobRequirement
from src.db.sqlite_client import Database, get_db, row_to_model


REQUIREMENT_CATEGORIES = {
    "responsibility",
    "required",
    "preferred",
    "education",
    "experience",
}
EVIDENCE_STATUSES = {"proven", "partial", "missing", "uncertain"}
EVIDENCE_USER_STATUSES = {"", "confirmed", "rejected", "corrected"}
EVIDENCE_REVIEW_ACTIONS = {"confirmed", "rejected", "corrected"}

_MATCH_KEYS = {
    "requirement_id",
    "status",
    "evidence",
    "reasoning",
    "confidence",
    "needs_user_confirmation",
    "recommended_action",
}
_EVIDENCE_KEYS = {"text", "section", "entry", "bullet_index"}


class EvidenceMatcherError(Exception):
    """Raised when requirement or evidence data violates the contract."""


def normalize_requirement_key(text: str) -> str:
    """Create a stable, human-readable key for requirement deduplication."""
    normalized = re.sub(r"[^\w\s+#.-]", " ", text.casefold(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def extract_job_requirements(jd_id: int, jd_json: dict) -> list[JobRequirement]:
    """Deterministically split structured JD data into independent requirements."""
    if jd_id <= 0:
        raise EvidenceMatcherError("A persisted jd_id is required")
    if not isinstance(jd_json, dict) or not jd_json:
        raise EvidenceMatcherError("Structured JD data is required")

    now = _now()
    requirements: list[JobRequirement] = []
    seen: set[str] = set()

    def add(category: str, text: str, priority: int, source_span: str) -> None:
        clean_text = str(text or "").strip()
        key = normalize_requirement_key(clean_text)
        if not clean_text or not key or key in seen:
            return
        seen.add(key)
        requirements.append(JobRequirement(
            jd_id=jd_id,
            category=category,
            text=clean_text,
            normalized_key=key,
            priority=priority,
            source_span=source_span,
            created_at=now,
        ))

    for index, skill in enumerate(_string_list(jd_json.get("required_skills"))):
        add("required", skill, 1, f"required_skills[{index}]")

    years = jd_json.get("years_experience")
    if isinstance(years, (int, float)) and not isinstance(years, bool) and years >= 0:
        formatted_years = int(years) if float(years).is_integer() else years
        add(
            "experience",
            f"At least {formatted_years} years of experience",
            1,
            "years_experience",
        )

    for index, responsibility in enumerate(_string_list(jd_json.get("responsibilities"))):
        add("responsibility", responsibility, 2, f"responsibilities[{index}]")

    education = jd_json.get("education")
    if isinstance(education, str) and education.strip():
        add("education", education, 2, "education")

    for index, skill in enumerate(_string_list(jd_json.get("soft_skills"))):
        add("required", skill, 2, f"soft_skills[{index}]")

    for index, skill in enumerate(_string_list(jd_json.get("preferred_skills"))):
        add("preferred", skill, 3, f"preferred_skills[{index}]")

    return requirements


def prepare_job_requirements(
    jd_id: int,
    jd_json: dict,
    *,
    replace: bool = False,
    db: Optional[Database] = None,
) -> list[JobRequirement]:
    """Persist deterministic requirements, returning existing rows by default."""
    database = db or get_db()
    if database.get("job_descriptions", jd_id) is None:
        raise EvidenceMatcherError(f"Job description not found: id={jd_id}")
    existing_rows = database.find_by("job_requirements", "jd_id", jd_id)
    if existing_rows and not replace:
        return [row_to_model(row, JobRequirement) for row in existing_rows]

    if replace:
        for row in existing_rows:
            for evidence in database.find_by(
                "evidence_matches", "requirement_id", row["id"]
            ):
                database.delete("evidence_matches", evidence["id"])
            database.delete("job_requirements", row["id"])

    requirements = extract_job_requirements(jd_id, jd_json)
    for requirement in requirements:
        requirement.id = database.insert("job_requirements", requirement)
    return requirements


def validate_evidence_output(
    payload: dict,
    requirements: list[JobRequirement],
    resume_json: dict,
    *,
    match_id: int,
) -> list[EvidenceMatch]:
    """Validate AI output, including exact grounding in the supplied resume."""
    if match_id <= 0:
        raise EvidenceMatcherError("A persisted match_id is required")
    if not isinstance(payload, dict) or set(payload) != {"matches"}:
        raise EvidenceMatcherError("Evidence output must contain only 'matches'")
    if not isinstance(payload["matches"], list):
        raise EvidenceMatcherError("'matches' must be a list")
    if not requirements:
        raise EvidenceMatcherError("At least one persisted requirement is required")

    requirement_by_id = {
        requirement.id: requirement
        for requirement in requirements
        if requirement.id is not None
    }
    if len(requirement_by_id) != len(requirements):
        raise EvidenceMatcherError("All requirements must be persisted before matching")

    now = _now()
    source_aware_resume = assign_source_ids(resume_json)
    seen_ids: set[int] = set()
    validated: list[EvidenceMatch] = []

    for index, item in enumerate(payload["matches"]):
        path = f"matches[{index}]"
        if not isinstance(item, dict) or set(item) != _MATCH_KEYS:
            raise EvidenceMatcherError(f"{path} does not match the output contract")

        requirement_id = item["requirement_id"]
        if isinstance(requirement_id, bool) or not isinstance(requirement_id, int):
            raise EvidenceMatcherError(f"{path}.requirement_id must be an integer")
        if requirement_id not in requirement_by_id:
            raise EvidenceMatcherError(f"{path} references an unknown requirement")
        if requirement_id in seen_ids:
            raise EvidenceMatcherError(f"Duplicate evidence match for requirement {requirement_id}")
        seen_ids.add(requirement_id)

        status = item["status"]
        if status not in EVIDENCE_STATUSES:
            raise EvidenceMatcherError(f"{path}.status is invalid")

        evidence = item["evidence"]
        if not isinstance(evidence, list):
            raise EvidenceMatcherError(f"{path}.evidence must be a list")
        if status in {"proven", "partial"} and not evidence:
            raise EvidenceMatcherError(f"{status} matches require grounded evidence")
        if status == "missing" and evidence:
            raise EvidenceMatcherError("missing matches cannot contain evidence")

        validated_evidence = [
            _validate_evidence_item(
                source,
                source_aware_resume,
                f"{path}.evidence[{source_index}]",
            )
            for source_index, source in enumerate(evidence)
        ]

        reasoning = item["reasoning"]
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise EvidenceMatcherError(f"{path}.reasoning is required")

        confidence = item["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise EvidenceMatcherError(f"{path}.confidence must be between 0 and 1")

        needs_confirmation = item["needs_user_confirmation"]
        if not isinstance(needs_confirmation, bool):
            raise EvidenceMatcherError(
                f"{path}.needs_user_confirmation must be a boolean"
            )
        if status == "uncertain" and not needs_confirmation:
            raise EvidenceMatcherError("uncertain matches require user confirmation")

        action = item["recommended_action"]
        if not isinstance(action, str):
            raise EvidenceMatcherError(f"{path}.recommended_action must be a string")

        validated.append(EvidenceMatch(
            match_id=match_id,
            requirement_id=requirement_id,
            status=status,
            evidence_json=validated_evidence,
            reasoning=reasoning.strip(),
            confidence=float(confidence),
            needs_user_confirmation=needs_confirmation,
            recommended_action=action.strip(),
            created_at=now,
            updated_at=now,
        ))

    missing_ids = set(requirement_by_id) - seen_ids
    if missing_ids:
        raise EvidenceMatcherError(
            f"Evidence output does not cover requirements: {sorted(missing_ids)}"
        )

    return validated


def save_evidence_matches(
    match_id: int,
    requirements: list[JobRequirement],
    resume_json: dict,
    payload: dict,
    *,
    db: Optional[Database] = None,
) -> list[EvidenceMatch]:
    """Validate a complete result before replacing stored evidence matches."""
    database = db or get_db()
    match_row = database.get("match_results", match_id)
    if match_row is None:
        raise EvidenceMatcherError(f"Match result not found: id={match_id}")
    if any(requirement.jd_id != match_row["jd_id"] for requirement in requirements):
        raise EvidenceMatcherError("Requirements do not belong to the match result JD")

    validated = validate_evidence_output(
        payload,
        requirements,
        resume_json,
        match_id=match_id,
    )

    for row in database.find_by("evidence_matches", "match_id", match_id):
        database.delete("evidence_matches", row["id"])

    for evidence_match in validated:
        evidence_match.id = database.insert("evidence_matches", evidence_match)
    return validated


def run_evidence_match(
    match_id: int,
    jd_id: int,
    resume_json: dict,
    *,
    requirements: Optional[list[JobRequirement]] = None,
    db: Optional[Database] = None,
) -> list[EvidenceMatch]:
    """Run the standalone Evidence Matcher and persist validated results."""
    database = db or get_db()
    active_requirements = requirements or get_job_requirements(jd_id, db=database)
    if not active_requirements:
        raise EvidenceMatcherError("Prepare job requirements before evidence matching")

    prompt_requirements = [
        {
            "requirement_id": requirement.id,
            "category": requirement.category,
            "text": requirement.text,
            "priority": requirement.priority,
        }
        for requirement in active_requirements
    ]
    message = build_evidence_match_message(prompt_requirements, resume_json)

    try:
        payload = get_ai_client()._call(
            model=get_active_model("reasoning"),
            system=message["system"],
            user_text=message["user"],
            temperature=0.1,
            max_tokens=8192,
        )
    except AIClientError as e:
        raise EvidenceMatcherError(f"Evidence matching failed: {e}") from e

    return save_evidence_matches(
        match_id,
        active_requirements,
        resume_json,
        payload,
        db=database,
    )


def get_job_requirements(
    jd_id: int,
    *,
    db: Optional[Database] = None,
) -> list[JobRequirement]:
    database = db or get_db()
    return [
        row_to_model(row, JobRequirement)
        for row in database.find_by("job_requirements", "jd_id", jd_id)
    ]


def get_evidence_matches(
    match_id: int,
    *,
    db: Optional[Database] = None,
) -> list[EvidenceMatch]:
    database = db or get_db()
    matches = [
        row_to_model(row, EvidenceMatch)
        for row in database.find_by("evidence_matches", "match_id", match_id)
    ]
    for evidence_match in matches:
        evidence_match.needs_user_confirmation = bool(
            evidence_match.needs_user_confirmation
        )
    return matches


def record_evidence_review(
    evidence_match_id: int,
    action: str,
    *,
    note: str = "",
    corrected_status: Optional[str] = None,
    corrected_evidence: Optional[list[dict]] = None,
    resume_json: Optional[dict] = None,
    db: Optional[Database] = None,
) -> tuple[EvidenceMatch, EvidenceReview]:
    """Record a user's decision without discarding the original AI result."""
    database = db or get_db()
    if evidence_match_id <= 0:
        raise EvidenceMatcherError("A persisted evidence_match_id is required")
    if action not in EVIDENCE_REVIEW_ACTIONS:
        raise EvidenceMatcherError(f"Unsupported evidence review action: {action}")
    if not isinstance(note, str):
        raise EvidenceMatcherError("Evidence review note must be a string")

    row = database.get("evidence_matches", evidence_match_id)
    if row is None:
        raise EvidenceMatcherError(
            f"Evidence match not found: id={evidence_match_id}"
        )
    evidence_match = row_to_model(row, EvidenceMatch)
    previous_evidence = list(evidence_match.evidence_json)
    validated_correction: list[dict] = []
    new_status = evidence_match.status

    if action == "corrected":
        if corrected_status not in EVIDENCE_STATUSES:
            raise EvidenceMatcherError("A valid corrected_status is required")
        if corrected_evidence is None or not isinstance(corrected_evidence, list):
            raise EvidenceMatcherError("corrected_evidence must be a list")
        if corrected_status in {"proven", "partial"} and not corrected_evidence:
            raise EvidenceMatcherError(
                f"{corrected_status} corrections require grounded evidence"
            )
        if corrected_status == "missing" and corrected_evidence:
            raise EvidenceMatcherError("missing corrections cannot contain evidence")
        if corrected_evidence and not isinstance(resume_json, dict):
            raise EvidenceMatcherError(
                "Structured resume data is required to validate corrected evidence"
            )

        source_aware_resume = assign_source_ids(resume_json or {})
        validated_correction = [
            _validate_evidence_item(
                item,
                source_aware_resume,
                f"corrected_evidence[{index}]",
                allow_source_id=True,
            )
            for index, item in enumerate(corrected_evidence)
        ]
        new_status = corrected_status
    elif corrected_status is not None or corrected_evidence is not None:
        raise EvidenceMatcherError(
            "Corrected status and evidence are only valid for a corrected review"
        )

    now = _now()
    updates = {
        "user_status": action,
        "user_note": note.strip(),
        "updated_at": now,
        "needs_user_confirmation": int(new_status == "uncertain"),
    }
    if action == "corrected":
        updates.update({
            "status": new_status,
            "evidence_json": json.dumps(validated_correction, ensure_ascii=False),
        })
    database.update("evidence_matches", evidence_match_id, updates)

    review = EvidenceReview(
        evidence_match_id=evidence_match_id,
        match_id=evidence_match.match_id,
        requirement_id=evidence_match.requirement_id,
        action=action,
        previous_status=evidence_match.status,
        corrected_status=new_status if action == "corrected" else "",
        previous_evidence_json=previous_evidence,
        corrected_evidence_json=validated_correction,
        note=note.strip(),
        created_at=now,
    )
    review.id = database.insert("evidence_reviews", review)

    updated_row = database.get("evidence_matches", evidence_match_id)
    updated_match = row_to_model(updated_row, EvidenceMatch)
    updated_match.needs_user_confirmation = bool(
        updated_match.needs_user_confirmation
    )
    return updated_match, review


def get_evidence_reviews(
    evidence_match_id: int,
    *,
    db: Optional[Database] = None,
) -> list[EvidenceReview]:
    """Return the complete user decision history for one evidence match."""
    database = db or get_db()
    reviews = [
        row_to_model(row, EvidenceReview)
        for row in database.find_by(
            "evidence_reviews", "evidence_match_id", evidence_match_id
        )
    ]
    return sorted(reviews, key=lambda review: review.id or 0)


def _validate_evidence_item(
    source: dict,
    resume_json: dict,
    path: str,
    *,
    allow_source_id: bool = False,
) -> dict:
    allowed_keys = [_EVIDENCE_KEYS]
    if allow_source_id:
        allowed_keys.append(_EVIDENCE_KEYS | {"source_id"})
    if not isinstance(source, dict) or set(source) not in allowed_keys:
        raise EvidenceMatcherError(f"{path} does not match the evidence contract")

    text = source["text"]
    section_name = source["section"]
    entry_name = source["entry"]
    bullet_index = source["bullet_index"]
    if not all(isinstance(value, str) and value.strip() for value in (text, section_name, entry_name)):
        raise EvidenceMatcherError(f"{path} requires text, section, and entry")
    if bullet_index is not None and (
        isinstance(bullet_index, bool)
        or not isinstance(bullet_index, int)
        or bullet_index < 0
    ):
        raise EvidenceMatcherError(f"{path}.bullet_index must be a nonnegative integer or null")

    sections = resume_json.get("sections", []) if isinstance(resume_json, dict) else []
    section = next(
        (
            candidate
            for candidate in sections
            if isinstance(candidate, dict)
            and _same_text(candidate.get("title", ""), section_name)
        ),
        None,
    )
    if section is None:
        raise EvidenceMatcherError(f"{path} references an unknown resume section")

    entry = next(
        (
            candidate
            for candidate in section.get("entries", [])
            if isinstance(candidate, dict)
            and _same_text(candidate.get("header", ""), entry_name)
        ),
        None,
    )
    if entry is None:
        raise EvidenceMatcherError(f"{path} references an unknown resume entry")

    bullets = entry.get("bullets", [])
    if bullet_index is not None:
        if bullet_index >= len(bullets):
            raise EvidenceMatcherError(f"{path}.bullet_index is outside the resume entry")
        bullet = bullets[bullet_index]
        source_candidates = [
            (bullet_text(bullet), bullet.get("source_id", "") if isinstance(bullet, dict) else "")
        ]
    else:
        source_candidates = [(entry.get("header", ""), entry.get("source_id", ""))]
        source_candidates.extend(
            (
                bullet_text(bullet),
                bullet.get("source_id", "") if isinstance(bullet, dict) else "",
            )
            for bullet in bullets
        )

    normalized_quote = _normalize_source_text(text)
    matched_source_id = next(
        (
            source_id
            for candidate, source_id in source_candidates
            if normalized_quote in _normalize_source_text(candidate)
        ),
        None,
    )
    if matched_source_id is None:
        raise EvidenceMatcherError(f"{path}.text is not grounded in the referenced resume source")

    return {
        "text": text.strip(),
        "section": section.get("title", "").strip(),
        "entry": entry.get("header", "").strip(),
        "bullet_index": bullet_index,
        "source_id": matched_source_id,
    }


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_source_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _same_text(left: str, right: str) -> bool:
    return _normalize_source_text(left) == _normalize_source_text(right)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
