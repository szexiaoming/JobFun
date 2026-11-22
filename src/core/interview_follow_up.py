"""Generate and persist targeted follow-ups for saved interview attempts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from config import get_active_model
from src.ai.client import AIClientError, get_ai_client
from src.ai.prompts.interview_follow_up import build_interview_follow_up_message
from src.core.interview_practice import RUBRIC_DIMENSIONS
from src.db.models import InterviewFollowUp, InterviewQuestion
from src.db.sqlite_client import Database, get_db


MAX_FOLLOW_UPS_PER_ATTEMPT = 3


class InterviewFollowUpError(Exception):
    """Raised when a follow-up cannot be generated or persisted safely."""


@dataclass(frozen=True)
class FollowUpQuestion:
    id: int
    parent_attempt_id: int
    question_id: int
    question: str
    target_dimension: str
    rationale: str
    created_at: str


def generate_follow_up(
    parent_attempt_id: int,
    *,
    db: Optional[Database] = None,
    client=None,
) -> FollowUpQuestion:
    """Generate one follow-up linked to an existing, evaluated answer."""
    database = db or get_db()
    attempt = database.get("interview_attempts", parent_attempt_id)
    if attempt is None:
        raise InterviewFollowUpError(
            f"Interview attempt not found: {parent_attempt_id}"
        )
    existing = database.find_by(
        "interview_follow_ups",
        "parent_attempt_id",
        parent_attempt_id,
    )
    if len(existing) >= MAX_FOLLOW_UPS_PER_ATTEMPT:
        raise InterviewFollowUpError(
            f"An interview attempt can have at most {MAX_FOLLOW_UPS_PER_ATTEMPT} follow-ups"
        )

    original_question = database.get(
        "interview_questions",
        int(attempt.get("question_id", 0) or 0),
    )
    if original_question is None:
        raise InterviewFollowUpError("The original interview question is unavailable")

    scores = {
        "completeness": int(attempt.get("completeness_score", 0) or 0),
        "truthfulness": int(attempt.get("truthfulness_score", 0) or 0),
        "technical": int(attempt.get("technical_score", 0) or 0),
        "structure": int(attempt.get("structure_score", 0) or 0),
    }
    feedback = _parse_feedback(attempt.get("feedback_json", {}))
    expected_target = _choose_target_dimension(scores, feedback)
    message = build_interview_follow_up_message(
        original_question=original_question.get("question", ""),
        answer_text=attempt.get("answer_text", ""),
        scores=scores,
        feedback=feedback,
        target_dimension=expected_target,
    )
    try:
        generator = client or get_ai_client()
        raw = generator._call(
            model=get_active_model("evaluation"),
            system=message["system"],
            user_text=message["user"],
            temperature=0.2,
        )
    except AIClientError as exc:
        raise InterviewFollowUpError(f"Follow-up generation failed: {exc}") from exc

    payload = validate_follow_up(raw, expected_target=expected_target)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    question = InterviewQuestion(
        match_id=int(original_question.get("match_id", 0) or 0),
        category=original_question.get("category", ""),
        question=payload["question"],
        difficulty=original_question.get("difficulty", "medium"),
        created_at=created_at,
    )
    question_id = database.insert("interview_questions", question)
    relation = InterviewFollowUp(
        parent_attempt_id=parent_attempt_id,
        question_id=question_id,
        target_dimension=payload["target_dimension"],
        rationale=payload["rationale"],
        created_at=created_at,
    )
    try:
        follow_up_id = database.insert("interview_follow_ups", relation)
    except Exception:
        database.delete("interview_questions", question_id)
        raise
    return FollowUpQuestion(
        id=follow_up_id,
        parent_attempt_id=parent_attempt_id,
        question_id=question_id,
        question=payload["question"],
        target_dimension=payload["target_dimension"],
        rationale=payload["rationale"],
        created_at=created_at,
    )


def validate_follow_up(
    raw: Any,
    *,
    expected_target: str = "",
) -> dict[str, str]:
    """Validate a follow-up response before creating database records."""
    required = {"question", "target_dimension", "rationale"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise InterviewFollowUpError("Follow-up does not match the required format")
    payload = {}
    for field in ("question", "rationale"):
        value = raw[field]
        if not isinstance(value, str) or not value.strip():
            raise InterviewFollowUpError(f"Follow-up {field} is required")
        payload[field] = value.strip()
    target = raw["target_dimension"]
    if target not in RUBRIC_DIMENSIONS:
        raise InterviewFollowUpError("Follow-up target_dimension is invalid")
    if expected_target and target != expected_target:
        raise InterviewFollowUpError(
            f"Follow-up must target the selected dimension: {expected_target}"
        )
    payload["target_dimension"] = target
    return payload


def get_follow_ups(
    parent_attempt_id: int,
    *,
    db: Optional[Database] = None,
) -> list[FollowUpQuestion]:
    """Load persisted follow-ups for one attempt in creation order."""
    database = db or get_db()
    rows = database.find_by(
        "interview_follow_ups",
        "parent_attempt_id",
        parent_attempt_id,
    )
    follow_ups = []
    for row in sorted(rows, key=lambda item: int(item.get("id", 0))):
        question = database.get("interview_questions", row["question_id"])
        if question is None:
            continue
        follow_ups.append(FollowUpQuestion(
            id=int(row["id"]),
            parent_attempt_id=int(row["parent_attempt_id"]),
            question_id=int(row["question_id"]),
            question=question.get("question", ""),
            target_dimension=row.get("target_dimension", ""),
            rationale=row.get("rationale", ""),
            created_at=row.get("created_at", ""),
        ))
    return follow_ups


def _parse_feedback(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _choose_target_dimension(scores: dict[str, int], feedback: dict) -> str:
    """Choose the follow-up target deterministically from persisted feedback."""
    if feedback.get("unsupported_claims"):
        return "truthfulness"
    priority = ("truthfulness", "technical", "completeness", "structure")
    lowest = min(scores.values())
    return next(dimension for dimension in priority if scores[dimension] == lowest)
