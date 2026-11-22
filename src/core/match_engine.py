"""
Match Engine: orchestrates the JD ↔ Resume matching analysis.

Calls the configured AI provider for deep analysis, persists results to SQLite,
and returns structured match results with suggestions.
"""

import json
from datetime import datetime
from typing import Optional

from src.ai.client import AIClientError, get_ai_client
from src.core.jd_parser import JDParserError, get_jd
from src.core.latex_parser import LaTeXParserError
from src.db.models import MatchResult, Resume, Suggestion
from src.db.sqlite_client import Database, get_db, row_to_model
from src.utils.logger import logger


class MatchEngineError(Exception):
    """Raised when the match analysis fails."""


# ── Main API ────────────────────────────────────────

def run_match(
    resume: Resume,
    jd_json: dict,
    resume_json: dict,
    jd_id: int = 0,
    *,
    db: Optional[Database] = None,
    client=None,
) -> dict:
    """
    Run a full match analysis between a resume and JD.

    Args:
        resume: The Resume model (must have id after DB insert)
        jd_json: Structured JD JSON (from jd_parser)
        resume_json: Structured resume JSON (from latex_parser)
        jd_id: Persisted job description ID. Required for a fully linked result.

    Returns:
        Full match report dict with keys:
          - match_result: MatchResult model (with id)
          - suggestions: list of Suggestion models (with ids)
          - matched_skills, missing_skills, risks
    """
    if not jd_json:
        raise MatchEngineError("JD is empty — parse a JD first")
    if not resume_json.get("sections"):
        raise MatchEngineError("Resume has no parsed sections — upload a resume first")

    logger.info("Running match: resume_id=%d", resume.id)

    # Phase 2: retrieve RAG context (similar JDs + historical suggestions)
    rag_context = {}
    rag_prompt_text = ""
    try:
        from src.core.retriever import retrieve_context, format_context_for_prompt
        rag_context = retrieve_context(jd_json)
        rag_prompt_text = format_context_for_prompt(rag_context)
        logger.info("RAG context: %d similar JDs, %d similar suggestions",
                    len(rag_context.get("similar_jds", [])),
                    len(rag_context.get("similar_suggestions", [])))
    except Exception as e:
        logger.warning("RAG retrieval failed (non-fatal): %s", e)

    try:
        matcher = client or get_ai_client()
        raw_report = matcher.match_and_suggest(jd_json, resume_json, rag_prompt_text)
    except AIClientError as e:
        raise MatchEngineError(f"AI matching failed: {e}") from e

    # Build MatchResult
    match = MatchResult(
        resume_id=resume.id,
        jd_id=jd_id,
        total_score=float(raw_report.get("total_score", 0)),
        skill_score=float(raw_report.get("skill_score", 0)),
        experience_score=float(raw_report.get("experience_score", 0)),
        education_score=float(raw_report.get("education_score", 0)),
        soft_skill_score=float(raw_report.get("soft_skill_score", 0)),
        culture_score=float(raw_report.get("culture_score", 0)),
        matched_skills=raw_report.get("matched_skills", []),
        missing_skills=raw_report.get("missing_skills", []),
        risks=raw_report.get("risks", []),
        raw_report=json.dumps(raw_report, ensure_ascii=False),
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    # Persist match
    database = db or get_db()
    match_id = database.insert("match_results", match)
    match.id = match_id

    # Persist suggestions
    suggestions = []
    raw_suggestions = raw_report.get("suggestions", [])
    for s in raw_suggestions:
        sug = Suggestion(
            match_id=match_id,
            category=s.get("category", ""),
            priority=int(s.get("priority", 1)),
            original_text=s.get("original_text", ""),
            suggested_text=s.get("suggested_text", ""),
            rationale=s.get("rationale", ""),
            status="pending",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        sug_id = database.insert("suggestions", sug)
        sug.id = sug_id
        suggestions.append(sug)

    logger.info(
        "Match done: id=%d, total=%.0f%%, %d suggestions",
        match_id, match.total_score, len(suggestions),
    )

    return {
        "match_result": match,
        "suggestions": suggestions,
        "matched_skills": match.matched_skills,
        "missing_skills": match.missing_skills,
        "risks": match.risks,
        "summary": raw_report.get("summary", ""),
        "rag_context": rag_context,  # Phase 2: similar JDs & historical suggestions
    }


def get_match(match_id: int) -> dict:
    """Retrieve a full match result with its suggestions."""
    db = get_db()
    match_row = db.get("match_results", match_id)
    if not match_row:
        raise MatchEngineError(f"Match not found: id={match_id}")

    match = row_to_model(match_row, MatchResult)
    suggestion_rows = db.get_suggestions_for_match(match_id)
    suggestions = [row_to_model(r, Suggestion) for r in suggestion_rows]

    return {
        "match_result": match,
        "suggestions": suggestions,
        "matched_skills": match.matched_skills,
        "missing_skills": match.missing_skills,
        "risks": match.risks,
    }


def list_matches(resume_id: Optional[int] = None, limit: int = 20) -> list[dict]:
    """List recent match results, optionally filtered by resume."""
    db = get_db()
    if resume_id:
        rows = db.find_by("match_results", "resume_id", resume_id)
    else:
        rows = db.list("match_results", limit=limit)
    return [row_to_model(r, MatchResult) for r in rows]
