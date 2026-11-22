"""Written interview practice with a fixed, persisted evaluation rubric."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from config import get_active_model
from src.ai.client import AIClientError, get_ai_client
from src.ai.prompts.interview_evaluation import build_interview_evaluation_message
from src.core.application_context import ApplicationContextError, get_application_context
from src.core.source_locator import assign_source_ids, bullet_text
from src.db.models import InterviewAttempt
from src.db.sqlite_client import Database, get_db


RUBRIC_DIMENSIONS = {
    "completeness": {
        "label": "完整性",
        "description": "是否回应问题重点，并覆盖必要背景、做法、结果或取舍。",
    },
    "truthfulness": {
        "label": "真实性",
        "description": "是否区分事实、估计和个人贡献，避免无依据的确定性表达。",
    },
    "technical": {
        "label": "技术正确性",
        "description": "技术内容是否准确，并包含与题目相称的推理或取舍。",
    },
    "structure": {
        "label": "表达结构",
        "description": "回答是否有清晰顺序、重点明确且便于理解。",
    },
}

_SCORE_FIELDS = {
    "completeness": "completeness_score",
    "truthfulness": "truthfulness_score",
    "technical": "technical_score",
    "structure": "structure_score",
}
_CITATION_KEYS = {"source_id", "claim", "support_level", "note"}
_UNSUPPORTED_KEYS = {"claim", "reason"}
_SUPPORT_LEVELS = {"supported", "partial"}


class InterviewPracticeError(Exception):
    """Raised when an answer cannot be evaluated or persisted safely."""


@dataclass(frozen=True)
class InterviewEvaluation:
    attempt_id: int
    question_id: int
    application_id: int
    answer_text: str
    audio_path: str
    transcript: str
    scores: dict[str, int]
    feedback: dict[str, Any]
    created_at: str

    @property
    def overall_score(self) -> float:
        """Return the unweighted average on the same 0-5 scale."""
        return round(sum(self.scores.values()) / len(self.scores), 2)


def evaluate_text_answer(
    question_id: int,
    answer_text: str,
    *,
    application_id: int = 0,
    audio_path: str = "",
    transcript: str = "",
    db: Optional[Database] = None,
    client=None,
) -> InterviewEvaluation:
    """Evaluate and save one written answer using the fixed four-part rubric."""
    database = db or get_db()
    answer = str(answer_text or "").strip()
    if not answer:
        raise InterviewPracticeError("Answer cannot be empty")
    if len(answer) > 12_000:
        raise InterviewPracticeError("Answer is too long (maximum 12,000 characters)")
    confirmed_transcript = str(transcript or "").strip()
    if confirmed_transcript and confirmed_transcript != answer:
        raise InterviewPracticeError(
            "Confirmed transcript must match the evaluated answer"
        )
    if audio_path and not confirmed_transcript:
        raise InterviewPracticeError(
            "Retained audio requires a confirmed transcript"
        )

    question = database.get("interview_questions", question_id)
    if question is None:
        raise InterviewPracticeError(f"Interview question not found: {question_id}")
    evidence_sources, resume_id = _load_evidence_sources(
        database,
        question,
        application_id,
    )

    message = build_interview_evaluation_message(
        question.get("question", ""),
        answer,
        category=question.get("category", ""),
        answer_hint=question.get("suggested_answer", ""),
        evidence_sources=evidence_sources,
    )
    try:
        evaluator = client or get_ai_client()
        raw = evaluator._call(
            model=get_active_model("evaluation"),
            system=message["system"],
            user_text=message["user"],
            temperature=0.1,
        )
    except AIClientError as exc:
        raise InterviewPracticeError(f"Answer evaluation failed: {exc}") from exc

    scores, feedback = validate_evaluation(
        raw,
        evidence_sources=evidence_sources,
        answer_text=answer,
        resume_id=resume_id,
    )
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    attempt = InterviewAttempt(
        question_id=question_id,
        application_id=application_id,
        answer_text=answer,
        audio_path=str(audio_path or ""),
        transcript=confirmed_transcript,
        completeness_score=scores["completeness"],
        truthfulness_score=scores["truthfulness"],
        technical_score=scores["technical"],
        structure_score=scores["structure"],
        feedback_json=feedback,
        created_at=created_at,
    )
    attempt_id = database.insert("interview_attempts", attempt)
    return InterviewEvaluation(
        attempt_id=attempt_id,
        question_id=question_id,
        application_id=application_id,
        answer_text=answer,
        audio_path=str(audio_path or ""),
        transcript=confirmed_transcript,
        scores=scores,
        feedback=feedback,
        created_at=created_at,
    )


def validate_evaluation(
    raw: Any,
    *,
    evidence_sources: Optional[list[dict]] = None,
    answer_text: str = "",
    resume_id: int = 0,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Validate the model response before it can be displayed or saved."""
    if not isinstance(raw, dict) or set(raw) != {"scores", "feedback"}:
        raise InterviewPracticeError("Evaluation does not match the required rubric")
    raw_scores = raw["scores"]
    if not isinstance(raw_scores, dict) or set(raw_scores) != set(RUBRIC_DIMENSIONS):
        raise InterviewPracticeError("Evaluation scores do not match the required rubric")
    scores: dict[str, int] = {}
    for dimension in RUBRIC_DIMENSIONS:
        value = raw_scores[dimension]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
            raise InterviewPracticeError(
                f"Evaluation score must be an integer from 0 to 5: {dimension}"
            )
        scores[dimension] = value

    feedback = raw["feedback"]
    required_feedback = {
        "summary",
        "strengths",
        "improvements",
        "next_practice",
        "evidence_citations",
        "unsupported_claims",
    }
    if not isinstance(feedback, dict) or set(feedback) != required_feedback:
        raise InterviewPracticeError("Evaluation feedback does not match the required format")
    for field in ("summary", "next_practice"):
        if not isinstance(feedback[field], str) or not feedback[field].strip():
            raise InterviewPracticeError(f"Evaluation feedback is missing: {field}")
    for field in ("strengths", "improvements"):
        values = feedback[field]
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(item, str) and item.strip() for item in values)
        ):
            raise InterviewPracticeError(f"Evaluation feedback is missing: {field}")
    feedback = dict(feedback)
    feedback["evidence_citations"] = _validate_citations(
        feedback["evidence_citations"],
        evidence_sources or [],
        answer_text,
        resume_id,
    )
    feedback["unsupported_claims"] = _validate_unsupported_claims(
        feedback["unsupported_claims"],
        answer_text,
        allow_items=bool(evidence_sources),
    )
    feedback["evidence_context"] = {
        "resume_id": resume_id,
        "source_count": len(evidence_sources or []),
    }
    return scores, feedback


def build_resume_evidence_sources(structured_resume: dict) -> list[dict]:
    """Flatten a structured resume into stable, model-selectable evidence sources."""
    located = assign_source_ids(structured_resume)
    sources: list[dict] = []
    for section in located.get("sections", []):
        if not isinstance(section, dict):
            continue
        section_name = str(section.get("title", "")).strip()
        for entry in section.get("entries", []):
            if not isinstance(entry, dict):
                continue
            entry_name = str(entry.get("header", "")).strip()
            for bullet_index, bullet in enumerate(entry.get("bullets", [])):
                text = bullet_text(bullet).strip()
                source_id = str(
                    bullet.get("source_id", "") if isinstance(bullet, dict) else ""
                ).strip()
                if text and source_id:
                    sources.append({
                        "source_id": source_id,
                        "text": text,
                        "section": section_name,
                        "entry": entry_name,
                        "bullet_index": bullet_index,
                    })
    return sources


def get_question_attempts(
    question_id: int,
    *,
    db: Optional[Database] = None,
) -> list[InterviewEvaluation]:
    """Load saved attempts for one question, newest first."""
    database = db or get_db()
    rows = database.find_by("interview_attempts", "question_id", question_id)
    attempts = [_row_to_evaluation(row) for row in rows]
    return sorted(attempts, key=lambda item: item.attempt_id, reverse=True)


def _load_evidence_sources(
    database: Database,
    question: dict,
    application_id: int,
) -> tuple[list[dict], int]:
    if not application_id:
        return [], 0
    try:
        context = get_application_context(application_id, db=database)
    except ApplicationContextError as exc:
        raise InterviewPracticeError(str(exc)) from exc
    if context.application.match_id != question.get("match_id"):
        raise InterviewPracticeError(
            "The selected application is not linked to this interview question"
        )
    if context.resume is None:
        raise InterviewPracticeError(
            "The historical resume bound to this application is unavailable"
        )
    return (
        build_resume_evidence_sources(context.resume.structured_json),
        int(context.resume.id or 0),
    )


def _validate_citations(
    citations: Any,
    evidence_sources: list[dict],
    answer_text: str,
    resume_id: int,
) -> list[dict]:
    if not isinstance(citations, list):
        raise InterviewPracticeError("Evaluation evidence_citations must be a list")
    source_map = {item["source_id"]: item for item in evidence_sources}
    if citations and not source_map:
        raise InterviewPracticeError(
            "Evaluation cannot cite resume evidence without a bound historical resume"
        )
    validated = []
    for index, citation in enumerate(citations):
        path = f"evidence_citations[{index}]"
        if not isinstance(citation, dict) or set(citation) != _CITATION_KEYS:
            raise InterviewPracticeError(f"{path} does not match the citation format")
        source_id = citation["source_id"]
        source = source_map.get(source_id)
        if source is None:
            raise InterviewPracticeError(f"{path} references an unknown resume source")
        claim = _required_text(citation["claim"], f"{path}.claim")
        if not _is_excerpt(claim, answer_text):
            raise InterviewPracticeError(f"{path}.claim is not grounded in the answer")
        support_level = citation["support_level"]
        if support_level not in _SUPPORT_LEVELS:
            raise InterviewPracticeError(f"{path}.support_level is invalid")
        note = _required_text(citation["note"], f"{path}.note")
        validated.append({
            **citation,
            "claim": claim,
            "note": note,
            "resume_id": resume_id,
            "text": source["text"],
            "section": source["section"],
            "entry": source["entry"],
            "bullet_index": source["bullet_index"],
        })
    return validated


def _validate_unsupported_claims(
    claims: Any,
    answer_text: str,
    *,
    allow_items: bool,
) -> list[dict]:
    if not isinstance(claims, list):
        raise InterviewPracticeError("Evaluation unsupported_claims must be a list")
    if claims and not allow_items:
        raise InterviewPracticeError(
            "Evaluation cannot identify resume gaps without a bound historical resume"
        )
    validated = []
    for index, item in enumerate(claims):
        path = f"unsupported_claims[{index}]"
        if not isinstance(item, dict) or set(item) != _UNSUPPORTED_KEYS:
            raise InterviewPracticeError(f"{path} does not match the required format")
        claim = _required_text(item["claim"], f"{path}.claim")
        if not _is_excerpt(claim, answer_text):
            raise InterviewPracticeError(f"{path}.claim is not grounded in the answer")
        validated.append({
            "claim": claim,
            "reason": _required_text(item["reason"], f"{path}.reason"),
        })
    return validated


def _required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InterviewPracticeError(f"{path} is required")
    return value.strip()


def _is_excerpt(excerpt: str, source: str) -> bool:
    normalized_excerpt = re.sub(r"\s+", " ", excerpt.casefold()).strip()
    normalized_source = re.sub(r"\s+", " ", source.casefold()).strip()
    return bool(normalized_excerpt) and normalized_excerpt in normalized_source


def _row_to_evaluation(row: dict) -> InterviewEvaluation:
    feedback = row.get("feedback_json", {})
    if isinstance(feedback, str):
        try:
            feedback = json.loads(feedback)
        except json.JSONDecodeError:
            feedback = {}
    scores = {
        dimension: int(row.get(field, 0) or 0)
        for dimension, field in _SCORE_FIELDS.items()
    }
    return InterviewEvaluation(
        attempt_id=int(row["id"]),
        question_id=int(row["question_id"]),
        application_id=int(row.get("application_id", 0) or 0),
        answer_text=row.get("answer_text", ""),
        audio_path=row.get("audio_path", ""),
        transcript=row.get("transcript", ""),
        scores=scores,
        feedback=feedback if isinstance(feedback, dict) else {},
        created_at=row.get("created_at", ""),
    )
