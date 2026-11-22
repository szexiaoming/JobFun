"""
JD Parser: extracts structured job description data from text or images.

Supports three input modes:
  - Text paste → configured AI provider structured extraction
  - Image upload → configured vision provider (OCR + extraction in one call)
  - PDF upload → (Phase 2+, falls back to error for now)
"""

from datetime import datetime
from pathlib import Path

from src.ai.client import AIClientError, get_ai_client
from src.db.models import JobDescription
from src.db.sqlite_client import get_db
from src.utils.logger import logger


class JDParserError(Exception):
    """Raised when JD parsing fails."""


def parse_jd_text(text: str) -> JobDescription:
    """
    Parse a JD from plain text.
    Calls the configured AI provider for structured extraction, persists to DB,
    and returns the model.
    """
    if not text.strip():
        raise JDParserError("JD text is empty")

    try:
        client = get_ai_client()
        structured = client.extract_jd_from_text(text.strip())
    except AIClientError as e:
        raise JDParserError(f"AI extraction failed: {e}") from e

    jd = JobDescription(
        company=structured.get("company") or "",
        position=structured.get("position") or "",
        raw_text=text.strip(),
        source_type="text",
        structured_json=structured,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    db = get_db()
    jd_id = db.insert("job_descriptions", jd)
    jd.id = jd_id
    logger.info("JD parsed from text → id=%d, company=%s, position=%s",
                jd_id, jd.company, jd.position)

    # Phase 2: auto-index into ChromaDB for RAG
    try:
        from src.core.retriever import index_jd
        index_jd(jd_id, structured)
    except Exception as e:
        logger.warning("Failed to index JD into ChromaDB (non-fatal): %s", e)

    return jd


def parse_jd_image(image_data: bytes, filename: str) -> JobDescription:
    """
    Parse a JD from an image file (screenshot or photo).
    Uses the configured vision model for OCR + structured extraction in one call.
    """
    # Detect media type from extension
    ext = Path(filename).suffix.lower()
    media_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = media_map.get(ext)
    if not media_type:
        raise JDParserError(f"Unsupported image format: {ext}")

    try:
        client = get_ai_client()
        structured = client.extract_jd_from_image(image_data, media_type)
    except AIClientError as e:
        raise JDParserError(f"AI vision extraction failed: {e}") from e

    jd = JobDescription(
        company=structured.get("company") or "",
        position=structured.get("position") or "",
        raw_text="",  # Image mode — raw text from Vision is in structured_json
        source_type="image",
        source_file=filename,
        structured_json=structured,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    db = get_db()
    jd_id = db.insert("job_descriptions", jd)
    jd.id = jd_id
    logger.info("JD parsed from image → id=%d, company=%s, position=%s",
                jd_id, jd.company, jd.position)
    return jd


def get_jd(jd_id: int) -> JobDescription:
    """Retrieve a JD from the database by ID."""
    db = get_db()
    row = db.get("job_descriptions", jd_id)
    if not row:
        raise JDParserError(f"JD not found: id={jd_id}")
    return _row_to_jd(row)


def list_jds(limit: int = 20) -> list[JobDescription]:
    """List recent JDs."""
    db = get_db()
    rows = db.list("job_descriptions", limit=limit)
    return [_row_to_jd(r) for r in rows]


def _row_to_jd(row: dict) -> JobDescription:
    import json
    return JobDescription(
        id=row["id"],
        user_id=row.get("user_id", 1),
        company=row.get("company", ""),
        position=row.get("position", ""),
        raw_text=row.get("raw_text", ""),
        source_type=row.get("source_type", "text"),
        source_file=row.get("source_file", ""),
        structured_json=json.loads(row["structured_json"]) if isinstance(row.get("structured_json"), str) else row.get("structured_json", {}),
        source_url=row.get("source_url", ""),
        created_at=row.get("created_at", ""),
    )
