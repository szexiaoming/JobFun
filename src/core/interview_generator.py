"""
Interview question generator. Cross-analyzes JD + resume to produce
targeted interview prep questions across 5 categories.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.ai.client import AIClientError, get_ai_client
from config import get_active_model
from src.db.models import InterviewQuestion
from src.db.sqlite_client import get_db
from src.utils.logger import logger


class InterviewError(Exception):
    """Raised when interview question generation fails."""


@dataclass
class InterviewPrep:
    match_id: int = 0
    interview_focus: str = ""
    categories: dict = field(default_factory=dict)
    generated_at: str = ""


def generate_questions(
    jd_json: dict,
    resume_json: dict,
    match_id: int = 0,
    category: str = "all",
    save_to_db: bool = True,
) -> InterviewPrep:
    """
    Generate interview questions based on JD and resume.

    Args:
        jd_json: Structured JD
        resume_json: Structured resume
        match_id: Match result ID (for linking)
        category: "all" or one of technical|project_deep_dive|behavioral|english|system_design
        save_to_db: Persist questions to SQLite

    Returns:
        InterviewPrep with categorized questions
    """
    logger.info("Generating interview questions: match_id=%d, category=%s", match_id, category)

    try:
        from src.ai.prompts.interview import build_interview_message

        jd_str = json.dumps(jd_json, ensure_ascii=False, indent=2)
        resume_str = json.dumps(resume_json, ensure_ascii=False, indent=2)

        message = build_interview_message(jd_str, resume_str, category)
        client = get_ai_client()
        raw = client._call(
            model=get_active_model("structured"),
            system=message["system"],
            user_text=message["user"],
            temperature=0.5,  # Slightly creative for question variety
        )

        categories = raw.get("categories", {})
        if save_to_db and match_id:
            categories = _save_to_db(match_id, categories)

        prep = InterviewPrep(
            match_id=match_id,
            interview_focus=raw.get("interview_focus", ""),
            categories=categories,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        total = sum(len(v) for v in prep.categories.values())
        logger.info("Generated %d interview questions across %d categories",
                    total, len(prep.categories))
        return prep

    except AIClientError as e:
        raise InterviewError(f"Question generation failed: {e}") from e


def get_saved_questions(match_id: int) -> dict[str, list[dict]]:
    """Retrieve previously generated questions from DB."""
    db = get_db()
    rows = db.find_by("interview_questions", "match_id", match_id)
    follow_up_count = db.count("interview_follow_ups")
    follow_up_question_ids = {
        int(row["question_id"])
        for row in db.list(
            "interview_follow_ups",
            limit=max(follow_up_count, 1),
        )
    }

    categorized: dict[str, list[dict]] = {}
    for row in rows:
        if int(row.get("id", 0)) in follow_up_question_ids:
            continue
        cat = row.get("category", "other")
        categorized.setdefault(cat, []).append({
            "id": row.get("id", 0),
            "match_id": row.get("match_id", match_id),
            "question": row.get("question", ""),
            "difficulty": row.get("difficulty", "medium"),
            "tip": row.get("suggested_answer", ""),
        })

    return categorized


def _save_to_db(match_id: int, categories: dict) -> dict[str, list[dict]]:
    """Persist generated questions and return their stable database IDs."""
    db = get_db()
    count = 0
    saved: dict[str, list[dict]] = {}

    # Replace unanswered generated questions, but never orphan saved practice attempts.
    old = db.find_by("interview_questions", "match_id", match_id)
    for r in old:
        attempts = db.find_by("interview_attempts", "question_id", r["id"])
        follow_ups = db.find_by("interview_follow_ups", "question_id", r["id"])
        if not attempts and not follow_ups:
            db.delete("interview_questions", r["id"])

    for cat_name, questions in categories.items():
        for q in questions:
            iq = InterviewQuestion(
                match_id=match_id,
                category=cat_name,
                question=q.get("question", ""),
                suggested_answer=q.get("tip", ""),
                difficulty=q.get("difficulty", "medium"),
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            question_id = db.insert("interview_questions", iq)
            saved.setdefault(cat_name, []).append({
                "id": question_id,
                "match_id": match_id,
                "question": iq.question,
                "difficulty": iq.difficulty,
                "tip": iq.suggested_answer,
            })
            count += 1

    logger.info("Saved %d interview questions to DB", count)
    return saved
