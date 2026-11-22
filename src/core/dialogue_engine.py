"""
Interactive dialogue engine for gap-filling.
User describes real experience → AI evaluates + rewrites into resume bullets.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.ai.client import AIClientError, get_ai_client
from src.utils.logger import logger


class DialogueError(Exception):
    """Raised when the dialogue operation fails."""


@dataclass
class RewriteResult:
    """Result of an experience rewrite dialogue."""
    missing_skill: str = ""
    user_description: str = ""
    credibility: str = ""  # strong | plausible | weak | needs_clarification
    credibility_notes: str = ""
    fills_gap: bool = False
    gap_analysis: str = ""
    suggested_section: str = "Experience"
    follow_up_questions: list = field(default_factory=list)
    rewritten_bullets: list = field(default_factory=list)
    integration_advice: str = ""
    created_at: str = ""


def evaluate_experience(
    missing_skill: str,
    user_description: str,
    resume_context: str,
    jd_context: str = "",
) -> RewriteResult:
    """
    Evaluate and rewrite a user-described experience.

    Args:
        missing_skill: The skill/requirement from JD that the user is addressing
        user_description: User's natural language description of their experience
        resume_context: Summary of current resume structure (sections/entries)
        jd_context: Relevant JD requirements for context

    Returns:
        RewriteResult with credibility assessment and rewritten bullets
    """
    if not missing_skill.strip():
        raise DialogueError("Missing skill is required")
    if not user_description.strip():
        raise DialogueError("Please describe your experience")

    logger.info("Dialogue: rewriting experience for skill='%s'", missing_skill[:50])

    # Detect language — if resume/JD contains Chinese, output Chinese
    lang = "zh" if _has_chinese(resume_context + user_description) else "en"

    try:
        from config import get_active_model
        from src.ai.prompts.experience_rewrite import build_rewrite_message

        message = build_rewrite_message(
            missing_skill, user_description, resume_context, jd_context, language=lang
        )
        client = get_ai_client()
        raw = client._call(
            model=get_active_model("evaluation"),
            system=message["system"],
            user_text=message["user"],
            temperature=0.4,  # Slightly creative for writing
            max_tokens=4096,
        )

        result = RewriteResult(
            missing_skill=missing_skill,
            user_description=user_description,
            credibility=raw.get("credibility", "plausible"),
            credibility_notes=raw.get("credibility_notes", ""),
            fills_gap=raw.get("fills_gap", False),
            gap_analysis=raw.get("gap_analysis", ""),
            suggested_section=raw.get("suggested_section", "Experience"),
            follow_up_questions=raw.get("follow_up_questions", []),
            rewritten_bullets=raw.get("rewritten_bullets", []),
            integration_advice=raw.get("integration_advice", ""),
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        logger.info(
            "Dialogue result: credibility=%s, fills_gap=%s, bullets=%d",
            result.credibility, result.fills_gap, len(result.rewritten_bullets),
        )
        return result

    except AIClientError as e:
        raise DialogueError(f"AI rewrite failed: {e}") from e


def resume_context_summary(structured_resume: dict) -> str:
    """
    Create a concise summary of the resume structure for the dialogue prompt.
    Shows section titles and entry headers so AI can suggest proper placement.
    """
    lines = []
    for section in structured_resume.get("sections", []):
        title = section.get("title", "Untitled")
        lines.append(f"\n[{title}]")
        for entry in section.get("entries", []):
            header = entry.get("header", "")
            bullets = entry.get("bullets", [])
            if header:
                lines.append(f"  • {header}")
            for b in bullets[:2]:  # First 2 bullets for tone reference
                lines.append(f"    - {b[:120]}")
    return "\n".join(lines)


def jd_requirements_summary(jd_json: dict) -> str:
    """Extract key requirements from JD for dialogue context."""
    parts = []
    if jd_json.get("required_skills"):
        parts.append("Required: " + ", ".join(jd_json["required_skills"]))
    if jd_json.get("preferred_skills"):
        parts.append("Preferred: " + ", ".join(jd_json["preferred_skills"]))
    if jd_json.get("responsibilities"):
        parts.append("Responsibilities: " + "; ".join(jd_json["responsibilities"][:3]))
    return " | ".join(parts)


def format_bullets_for_display(bullets: list[str]) -> str:
    """Format rewritten bullets as markdown for UI display."""
    return "\n".join(f"- {b}" for b in bullets)


def _has_chinese(text: str) -> bool:
    """Check if text contains Chinese characters."""
    import re
    return bool(re.search(r'[一-鿿]', text))
