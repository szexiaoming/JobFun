"""
RAG Retriever: orchestrates JD indexing and similarity search.
Sits between the match engine and ChromaDB.
"""

from typing import Optional

from src.db.chroma_client import ChromaClientError, get_chroma
from src.utils.logger import logger


class RetrieverError(Exception):
    """Raised when a retrieval operation fails."""


def index_jd(jd_id: int, structured_json: dict) -> str:
    """
    Index a newly parsed JD into the vector store.
    Called after JD parsing succeeds.
    Returns the ChromaDB document ID.
    """
    try:
        chroma = get_chroma()
        doc_id = chroma.add_jd(jd_id, structured_json)
        logger.info("JD indexed: jd_id=%d, chroma_id=%s", jd_id, doc_id)
        return doc_id
    except ChromaClientError as e:
        logger.warning("Failed to index JD (non-fatal): %s", e)
        return ""
    except Exception as e:
        logger.warning("Failed to index JD (non-fatal): %s", e)
        return ""


def retrieve_context(structured_jd: dict) -> dict:
    """
    Retrieve RAG context for a match analysis.
    Returns dict with:
      - similar_jds: list of historically similar JDs
      - similar_suggestions: list of historically effective suggestions
      - has_context: bool, whether any context was found
    """
    chroma = get_chroma()
    jd_count = chroma.count_jds()

    similar_jds = []
    similar_suggestions = []

    if jd_count > 0:
        try:
            similar_jds = chroma.search_similar_jds(structured_jd, n_results=3)
            logger.info("Found %d similar JDs", len(similar_jds))
        except Exception as e:
            logger.warning("JD search failed: %s", e)

    sug_count = chroma.count_suggestions()
    if sug_count > 0:
        try:
            jd_text = _jd_to_text(structured_jd)
            similar_suggestions = chroma.search_similar_suggestions(jd_text, n_results=5)
            logger.info("Found %d similar suggestions", len(similar_suggestions))
        except Exception as e:
            logger.warning("Suggestion search failed: %s", e)

    return {
        "similar_jds": similar_jds,
        "similar_suggestions": similar_suggestions,
        "has_context": bool(similar_jds or similar_suggestions),
    }


def format_context_for_prompt(context: dict) -> str:
    """
    Format RAG context into a string for injection into the Claude/DeepSeek prompt.
    Returns empty string if no context.
    """
    if not context.get("has_context"):
        return ""

    parts = []

    similar_jds = context.get("similar_jds", [])
    if similar_jds:
        lines = ["## Historical Similar JDs (for reference)"]
        for i, jd in enumerate(similar_jds, 1):
            lines.append(
                f"{i}. {jd['company']} — {jd['position']} "
                f"(similarity: {jd.get('similarity', 0):.0%})"
            )
            if jd.get("skills"):
                lines.append(f"   Skills: {jd['skills']}")
        parts.append("\n".join(lines))

    similar_sug = context.get("similar_suggestions", [])
    if similar_sug:
        lines = ["## Historically Effective Suggestions (for reference)"]
        lines.append("These suggestions were accepted for similar JDs in the past:")
        for i, sug in enumerate(similar_sug, 1):
            lines.append(f"{i}. [{sug.get('category', '')}] {sug['suggestion_text'][:200]}")
        parts.append("\n".join(lines))

    return "\n\n" + "\n\n".join(parts)


def index_accepted_suggestion(
    suggestion_text: str,
    match_id: int,
    category: str,
    jd_id: int,
) -> str:
    """
    After a user accepts a suggestion, index it for future reuse.
    (Phase 3+)
    """
    try:
        chroma = get_chroma()
        return chroma.add_accepted_suggestion(
            suggestion_text, match_id, category, jd_id
        )
    except Exception as e:
        logger.warning("Failed to index suggestion (non-fatal): %s", e)
        return ""


def get_chroma_stats() -> dict:
    """Get ChromaDB statistics for the dashboard."""
    try:
        chroma = get_chroma()
        return {
            "jd_count": chroma.count_jds(),
            "suggestion_count": chroma.count_suggestions(),
        }
    except Exception:
        return {"jd_count": 0, "suggestion_count": 0}


def _jd_to_text(jd: dict) -> str:
    parts = []
    for key in ("company", "position", "team", "location"):
        if jd.get(key):
            parts.append(str(jd[key]))
    for key in ("required_skills", "preferred_skills", "responsibilities", "soft_skills"):
        vals = jd.get(key, [])
        if vals:
            parts.append(" ".join(vals))
    return " | ".join(parts)
