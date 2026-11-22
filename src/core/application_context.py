"""Read-only historical context bound to a single application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.db.models import Application, JobDescription, MatchResult, Resume
from src.db.sqlite_client import Database, get_db, row_to_model


class ApplicationContextError(Exception):
    """Raised when the application itself cannot be loaded."""


@dataclass
class ApplicationContext:
    application: Application
    job: Optional[JobDescription] = None
    resume: Optional[Resume] = None
    match: Optional[MatchResult] = None
    issues: list[str] = field(default_factory=list)


def get_application_context(
    application_id: int,
    *,
    db: Optional[Database] = None,
) -> ApplicationContext:
    """Load only the records explicitly referenced by an application.

    This function deliberately never falls back to the active resume, latest
    resume, latest match, or another job description.
    """
    database = db or get_db()
    application_row = database.get("applications", application_id)
    if application_row is None:
        raise ApplicationContextError(
            f"Application not found: id={application_id}"
        )
    application = row_to_model(application_row, Application)
    context = ApplicationContext(application=application)

    job_row = database.get("job_descriptions", application.jd_id)
    if job_row is None:
        context.issues.append(f"绑定的岗位记录不可读取：jd_id={application.jd_id}")
    else:
        context.job = row_to_model(job_row, JobDescription)

    resume_row = database.get("resumes", application.resume_id)
    if resume_row is None:
        context.issues.append(
            f"绑定的简历版本不可读取：resume_id={application.resume_id}"
        )
    else:
        context.resume = row_to_model(resume_row, Resume)

    if application.match_id:
        match_row = database.get("match_results", application.match_id)
        if match_row is None:
            context.issues.append(
                f"绑定的匹配报告不可读取：match_id={application.match_id}"
            )
        elif (
            match_row.get("jd_id") != application.jd_id
            or match_row.get("resume_id") != application.resume_id
        ):
            context.issues.append(
                "绑定的匹配报告与该申请的岗位或简历版本不一致"
            )
        else:
            context.match = row_to_model(match_row, MatchResult)

    return context


def build_resume_outline(structured_json: dict) -> list[dict]:
    """Build a safe read-only outline from a historical structured resume."""
    if not isinstance(structured_json, dict):
        return []
    outline = []
    for section in structured_json.get("sections", []):
        if not isinstance(section, dict):
            continue
        entries = []
        for entry in section.get("entries", []):
            if not isinstance(entry, dict):
                continue
            bullets = []
            for bullet in entry.get("bullets", []):
                if isinstance(bullet, dict):
                    text = str(bullet.get("text", "")).strip()
                else:
                    text = str(bullet or "").strip()
                if text:
                    bullets.append(text)
            entries.append({
                "header": str(entry.get("header", "")).strip(),
                "bullets": bullets,
            })
        outline.append({
            "title": str(section.get("title", "")).strip(),
            "entries": entries,
        })
    return outline
