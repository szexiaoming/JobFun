"""User-supplied experience records for Evidence Matcher gaps.

Supplements are intentionally separate from resume evidence. Confirmation makes
them eligible for a later evidence re-check, but never places them directly in
the resume editing queue.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from src.db.models import EvidenceSupplement, EvidenceSupplementEvent
from src.db.sqlite_client import Database, get_db, row_to_model


SUPPLEMENT_CONTEXT_TYPES = {
    "work",
    "project",
    "education",
    "volunteering",
    "other",
}
SUPPLEMENT_STATUSES = {"draft", "confirmed", "rejected"}
_EDITABLE_FIELDS = {
    "title",
    "description",
    "context_type",
    "organization",
    "start_date",
    "end_date",
}


class EvidenceSupplementError(Exception):
    """Raised when a user-supplied experience violates the data contract."""


def create_evidence_supplement(
    match_id: int,
    requirement_id: int,
    *,
    title: str,
    description: str,
    context_type: str = "other",
    organization: str = "",
    start_date: str = "",
    end_date: str = "",
    evidence_match_id: Optional[int] = None,
    db: Optional[Database] = None,
) -> EvidenceSupplement:
    """Create a draft supplement linked to a valid match requirement."""
    database = db or get_db()
    _validate_relationships(
        database,
        match_id,
        requirement_id,
        evidence_match_id,
    )
    cleaned = _validate_content({
        "title": title,
        "description": description,
        "context_type": context_type,
        "organization": organization,
        "start_date": start_date,
        "end_date": end_date,
    })
    now = _now()
    supplement = EvidenceSupplement(
        match_id=match_id,
        requirement_id=requirement_id,
        evidence_match_id=evidence_match_id,
        **cleaned,
        source_type="user_supplied",
        status="draft",
        user_attested=False,
        eligible_for_matching=False,
        eligible_for_resume_edit=False,
        created_at=now,
        updated_at=now,
    )
    supplement.id = database.insert("evidence_supplements", supplement)
    _append_event(database, supplement, "created")
    return supplement


def update_evidence_supplement(
    supplement_id: int,
    updates: dict,
    *,
    note: str = "",
    db: Optional[Database] = None,
) -> EvidenceSupplement:
    """Edit the factual content of a draft and append an audit snapshot."""
    database = db or get_db()
    supplement = _get_supplement(database, supplement_id)
    if supplement.status != "draft":
        raise EvidenceSupplementError("Only draft supplements can be edited")
    if not isinstance(updates, dict) or not updates:
        raise EvidenceSupplementError("Supplement updates are required")
    unknown = set(updates) - _EDITABLE_FIELDS
    if unknown:
        raise EvidenceSupplementError(
            f"Unsupported supplement fields: {sorted(unknown)}"
        )
    _validate_note(note)

    current = {field: getattr(supplement, field) for field in _EDITABLE_FIELDS}
    current.update(updates)
    cleaned = _validate_content(current)
    cleaned["updated_at"] = _now()
    database.update("evidence_supplements", supplement_id, cleaned)

    updated = _get_supplement(database, supplement_id)
    _append_event(database, updated, "updated", note)
    return updated


def confirm_evidence_supplement(
    supplement_id: int,
    *,
    user_attested: bool,
    note: str = "",
    db: Optional[Database] = None,
) -> EvidenceSupplement:
    """Confirm a supplement for later matching, not for automatic resume edits."""
    database = db or get_db()
    supplement = _get_supplement(database, supplement_id)
    if supplement.status != "draft":
        raise EvidenceSupplementError("Only draft supplements can be confirmed")
    if user_attested is not True:
        raise EvidenceSupplementError(
            "User attestation is required before confirming an experience"
        )
    _validate_note(note)

    database.update("evidence_supplements", supplement_id, {
        "status": "confirmed",
        "user_attested": 1,
        "eligible_for_matching": 1,
        "eligible_for_resume_edit": 0,
        "updated_at": _now(),
    })
    confirmed = _get_supplement(database, supplement_id)
    _append_event(database, confirmed, "confirmed", note)
    return confirmed


def reject_evidence_supplement(
    supplement_id: int,
    *,
    note: str = "",
    db: Optional[Database] = None,
) -> EvidenceSupplement:
    """Reject or withdraw a supplement and remove matching eligibility."""
    database = db or get_db()
    supplement = _get_supplement(database, supplement_id)
    if supplement.status == "rejected":
        raise EvidenceSupplementError("Supplement is already rejected")
    _validate_note(note)

    database.update("evidence_supplements", supplement_id, {
        "status": "rejected",
        "user_attested": 0,
        "eligible_for_matching": 0,
        "eligible_for_resume_edit": 0,
        "updated_at": _now(),
    })
    rejected = _get_supplement(database, supplement_id)
    _append_event(database, rejected, "rejected", note)
    return rejected


def get_evidence_supplements(
    match_id: int,
    *,
    requirement_id: Optional[int] = None,
    db: Optional[Database] = None,
) -> list[EvidenceSupplement]:
    """Load supplements for one match, optionally limited to one requirement."""
    database = db or get_db()
    supplements = [
        _row_to_supplement(row)
        for row in database.find_by("evidence_supplements", "match_id", match_id)
        if requirement_id is None or row["requirement_id"] == requirement_id
    ]
    return sorted(supplements, key=lambda item: item.id or 0)


def get_evidence_supplement_events(
    supplement_id: int,
    *,
    db: Optional[Database] = None,
) -> list[EvidenceSupplementEvent]:
    """Return the append-only lifecycle history for a supplement."""
    database = db or get_db()
    events = [
        row_to_model(row, EvidenceSupplementEvent)
        for row in database.find_by(
            "evidence_supplement_events", "supplement_id", supplement_id
        )
    ]
    return sorted(events, key=lambda item: item.id or 0)


def _validate_relationships(
    database: Database,
    match_id: int,
    requirement_id: int,
    evidence_match_id: Optional[int],
) -> None:
    match = database.get("match_results", match_id)
    if match is None:
        raise EvidenceSupplementError(f"Match result not found: id={match_id}")
    requirement = database.get("job_requirements", requirement_id)
    if requirement is None:
        raise EvidenceSupplementError(
            f"Job requirement not found: id={requirement_id}"
        )
    if requirement["jd_id"] != match["jd_id"]:
        raise EvidenceSupplementError(
            "Requirement does not belong to the match result JD"
        )
    if evidence_match_id is not None:
        evidence_match = database.get("evidence_matches", evidence_match_id)
        if evidence_match is None:
            raise EvidenceSupplementError(
                f"Evidence match not found: id={evidence_match_id}"
            )
        if (
            evidence_match["match_id"] != match_id
            or evidence_match["requirement_id"] != requirement_id
        ):
            raise EvidenceSupplementError(
                "Evidence match does not belong to the supplied match requirement"
            )


def _validate_content(values: dict) -> dict:
    cleaned = {}
    limits = {
        "title": 300,
        "description": 20_000,
        "organization": 300,
        "start_date": 7,
        "end_date": 7,
    }
    for field, limit in limits.items():
        value = values.get(field, "")
        if not isinstance(value, str):
            raise EvidenceSupplementError(f"{field} must be a string")
        cleaned[field] = value.strip()
        if len(cleaned[field]) > limit:
            raise EvidenceSupplementError(f"{field} exceeds {limit} characters")

    if not cleaned["title"]:
        raise EvidenceSupplementError("Supplement title is required")
    if not cleaned["description"]:
        raise EvidenceSupplementError("Supplement description is required")

    context_type = values.get("context_type")
    if context_type not in SUPPLEMENT_CONTEXT_TYPES:
        raise EvidenceSupplementError(
            f"Unsupported supplement context_type: {context_type}"
        )
    cleaned["context_type"] = context_type
    _validate_date_range(cleaned["start_date"], cleaned["end_date"])
    return cleaned


def _validate_date_range(start_date: str, end_date: str) -> None:
    for field, value in (("start_date", start_date), ("end_date", end_date)):
        if not value:
            continue
        match = re.fullmatch(r"(\d{4})(?:-(\d{2}))?", value)
        if not match or (match.group(2) and not 1 <= int(match.group(2)) <= 12):
            raise EvidenceSupplementError(
                f"{field} must use YYYY or YYYY-MM format"
            )
    if start_date and end_date:
        start_key = _date_key(start_date, default_month=1)
        end_key = _date_key(end_date, default_month=12)
        if end_key < start_key:
            raise EvidenceSupplementError("end_date cannot be earlier than start_date")


def _date_key(value: str, *, default_month: int) -> tuple[int, int]:
    year, _, month = value.partition("-")
    return int(year), int(month) if month else default_month


def _validate_note(note: str) -> None:
    if not isinstance(note, str):
        raise EvidenceSupplementError("Supplement note must be a string")
    if len(note) > 5_000:
        raise EvidenceSupplementError("Supplement note exceeds 5000 characters")


def _get_supplement(database: Database, supplement_id: int) -> EvidenceSupplement:
    row = database.get("evidence_supplements", supplement_id)
    if row is None:
        raise EvidenceSupplementError(
            f"Evidence supplement not found: id={supplement_id}"
        )
    return _row_to_supplement(row)


def _row_to_supplement(row: dict) -> EvidenceSupplement:
    supplement = row_to_model(row, EvidenceSupplement)
    supplement.user_attested = bool(supplement.user_attested)
    supplement.eligible_for_matching = bool(supplement.eligible_for_matching)
    supplement.eligible_for_resume_edit = bool(supplement.eligible_for_resume_edit)
    return supplement


def _append_event(
    database: Database,
    supplement: EvidenceSupplement,
    event_type: str,
    note: str = "",
) -> EvidenceSupplementEvent:
    event = EvidenceSupplementEvent(
        supplement_id=supplement.id or 0,
        event_type=event_type,
        snapshot_json=asdict(supplement),
        note=note.strip(),
        created_at=_now(),
    )
    event.id = database.insert("evidence_supplement_events", event)
    return event


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
