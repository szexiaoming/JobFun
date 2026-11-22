"""
Job application progress manager.
CRUD for applications, status state machine, dashboard statistics.
"""

from datetime import datetime
from typing import Optional

from src.db.models import Application, ApplicationEvent
from src.db.sqlite_client import get_db, row_to_model
from src.utils.logger import logger


# ── Status State Machine ────────────────────────────

STATUS_FLOW = {
    "saved": ["applied", "withdrawn"],
    "applied": ["oa", "interview", "rejected", "withdrawn"],
    "oa": ["interview", "rejected", "withdrawn"],
    "interview": ["offer", "rejected", "withdrawn"],
    "offer": ["accepted", "rejected", "withdrawn"],
    "accepted": [],  # Terminal
    "rejected": [],  # Terminal
    "withdrawn": [],  # Terminal
}

STATUS_LABELS = {
    "saved": "📌 已收藏",
    "applied": "📤 已投递",
    "oa": "📝 笔试中",
    "interview": "🎤 面试中",
    "offer": "🎉 Offer",
    "accepted": "✅ 已接受",
    "rejected": "❌ 已拒绝",
    "withdrawn": "↩ 已撤回",
}

APPLIED_STATUSES = {"applied", "oa", "interview", "offer", "accepted", "rejected"}
RESPONSE_STATUSES = {"oa", "interview", "offer", "accepted", "rejected"}
INTERVIEW_STATUSES = {"interview", "offer", "accepted"}
OFFER_STATUSES = {"offer", "accepted"}


class ProgressError(Exception):
    """Raised when a progress operation fails."""


# ── CRUD ─────────────────────────────────────────────

def create_application(
    jd_id: int,
    resume_id: int,
    match_id: int = 0,
    notes: str = "",
) -> Application:
    """Create a new job application record."""
    db = get_db()

    now = _now()
    app = Application(
        user_id=1,
        jd_id=jd_id,
        resume_id=resume_id,
        match_id=match_id,
        status="saved",
        applied_date="",
        notes=notes,
        updated_at=now,
    )

    app_id = db.insert("applications", app)
    app.id = app_id
    _append_event(
        db,
        app_id,
        "created",
        "创建申请记录",
        details=notes.strip(),
        to_status="saved",
        occurred_at=now,
    )
    logger.info("Application created: id=%d, jd_id=%d", app_id, jd_id)
    return app


def update_status(app_id: int, new_status: str, notes: str = "") -> Application:
    """Update application status with validation."""
    if new_status not in STATUS_FLOW:
        raise ProgressError(f"Invalid status: {new_status}")

    db = get_db()
    row = db.get("applications", app_id)
    if not row:
        raise ProgressError(f"Application not found: id={app_id}")

    old_status = row["status"]

    # Validate transition
    allowed = STATUS_FLOW.get(old_status, [])
    if new_status not in allowed:
        raise ProgressError(
            f"Cannot transition from '{old_status}' to '{new_status}'. "
            f"Allowed: {allowed}"
        )

    now = _now()
    updates = {
        "status": new_status,
        "updated_at": now,
    }
    if notes:
        existing = row.get("notes", "")
        updates["notes"] = f"{existing}\n[{new_status}] {notes}".strip()

    # If transitioning to 'applied', set applied_date
    if new_status == "applied" and not row.get("applied_date"):
        updates["applied_date"] = datetime.now().strftime("%Y-%m-%d")

    db.update("applications", app_id, updates)
    _append_event(
        db,
        app_id,
        "status_changed",
        f"状态更新为 {STATUS_LABELS[new_status]}",
        details=notes.strip(),
        from_status=old_status,
        to_status=new_status,
        occurred_at=now,
    )
    logger.info("Application %d: %s → %s", app_id, old_status, new_status)

    return get_application(app_id)


def get_application(app_id: int) -> Application:
    """Get a single application by ID."""
    db = get_db()
    row = db.get("applications", app_id)
    if not row:
        raise ProgressError(f"Application not found: id={app_id}")
    return _row_to_app(row)


def list_applications(status: str = "", limit: int = 50) -> list[Application]:
    """List applications, optionally filtered by status."""
    db = get_db()
    if status:
        rows = db.find_by("applications", "status", status)
    else:
        rows = db.list("applications", limit=limit)
    return [_row_to_app(r) for r in rows]


def delete_application(app_id: int) -> None:
    """Delete an application record."""
    db = get_db()
    for event in db.find_by("application_events", "application_id", app_id):
        db.delete("application_events", event["id"])
    db.delete("applications", app_id)
    logger.info("Application deleted: id=%d", app_id)


def add_note(app_id: int, note: str) -> None:
    """Append a note to an application."""
    if not isinstance(note, str) or not note.strip():
        raise ProgressError("Note cannot be empty")
    if len(note.strip()) > 5000:
        raise ProgressError("Note exceeds 5000 characters")
    db = get_db()
    row = db.get("applications", app_id)
    if not row:
        raise ProgressError(f"Application not found: id={app_id}")

    existing = row.get("notes", "")
    now = _now()
    timestamp = now[:16]
    clean_note = note.strip()
    new_notes = f"{existing}\n[{timestamp}] {clean_note}".strip()

    db.update("applications", app_id, {"notes": new_notes, "updated_at": now})
    _append_event(
        db,
        app_id,
        "note_added",
        "添加备注",
        details=clean_note,
        occurred_at=now,
    )


def set_next_action(
    app_id: int,
    next_step: str,
    due_at: str = "",
    note: str = "",
) -> Application:
    """Set or clear the next action and its optional deadline."""
    if not isinstance(next_step, str) or len(next_step.strip()) > 500:
        raise ProgressError("Next action must be at most 500 characters")
    if not isinstance(note, str) or len(note.strip()) > 5000:
        raise ProgressError("Action note must be at most 5000 characters")
    clean_step = next_step.strip()
    clean_due = _validate_datetime(due_at, "Next action deadline") if clean_step else ""
    db = get_db()
    if db.get("applications", app_id) is None:
        raise ProgressError(f"Application not found: id={app_id}")

    now = _now()
    db.update("applications", app_id, {
        "next_step": clean_step,
        "next_step_due": clean_due,
        "updated_at": now,
    })
    _append_event(
        db,
        app_id,
        "next_action_updated" if clean_step else "next_action_cleared",
        f"下一步：{clean_step}" if clean_step else "清除下一步行动",
        details=note.strip(),
        occurred_at=now,
    )
    return get_application(app_id)


def schedule_interview(
    app_id: int,
    interview_at: str,
    note: str = "",
) -> Application:
    """Schedule or clear an interview without changing application status."""
    if not isinstance(note, str) or len(note.strip()) > 5000:
        raise ProgressError("Interview note must be at most 5000 characters")
    clean_time = _validate_datetime(interview_at, "Interview time")
    db = get_db()
    if db.get("applications", app_id) is None:
        raise ProgressError(f"Application not found: id={app_id}")

    now = _now()
    db.update("applications", app_id, {
        "interview_at": clean_time,
        "updated_at": now,
    })
    _append_event(
        db,
        app_id,
        "interview_scheduled" if clean_time else "interview_cleared",
        f"安排面试：{clean_time}" if clean_time else "清除面试时间",
        details=note.strip(),
        occurred_at=now,
    )
    return get_application(app_id)


def get_application_timeline(app_id: int) -> list[ApplicationEvent]:
    """Return the append-only application history in chronological order."""
    db = get_db()
    if db.get("applications", app_id) is None:
        raise ProgressError(f"Application not found: id={app_id}")
    events = [
        row_to_model(row, ApplicationEvent)
        for row in db.find_by("application_events", "application_id", app_id)
    ]
    return sorted(events, key=lambda event: (event.occurred_at, event.id or 0))


# ── Statistics ───────────────────────────────────────

def get_stats() -> dict:
    """Get dashboard statistics."""
    db = get_db()
    all_apps = [dict(r) for r in db.list("applications", limit=1000)]

    event_rows = db.list("application_events", limit=10000)
    stats = {
        "total": len(all_apps),
        "by_status": {},
        "pipeline": {"active": 0, "terminal": 0},
        "avg_match_score": 0.0,
    }
    stats.update(calculate_funnel_metrics(all_apps, event_rows))

    scores = []
    for app in all_apps:
        status = app.get("status", "saved")
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        if status in ("saved", "applied", "oa", "interview"):
            stats["pipeline"]["active"] += 1
        else:
            stats["pipeline"]["terminal"] += 1

        # Get match score
        match_id = app.get("match_id")
        if match_id:
            match_row = db.get("match_results", match_id)
            if match_row:
                scores.append(match_row.get("total_score", 0))

    if scores:
        stats["avg_match_score"] = sum(scores) / len(scores)

    return stats


def calculate_funnel_metrics(
    applications: list[dict],
    events: list[dict],
) -> dict:
    """Calculate funnel metrics from current state plus append-only history.

    Saved-only and withdrawn-before-application records are excluded from the
    denominator. Each application is counted at most once per milestone.
    """
    reached_by_application: dict[int, set[str]] = {}
    for event in events:
        application_id = event.get("application_id")
        to_status = event.get("to_status")
        if application_id and to_status:
            reached_by_application.setdefault(application_id, set()).add(to_status)

    applied_count = 0
    response_count = 0
    interview_count = 0
    offer_count = 0
    accepted_count = 0

    for application in applications:
        reached = set(reached_by_application.get(application.get("id"), set()))
        current_status = application.get("status", "saved")
        if current_status:
            reached.add(current_status)
        if application.get("applied_date"):
            reached.add("applied")

        has_applied = bool(reached & APPLIED_STATUSES)
        if not has_applied:
            continue
        applied_count += 1
        response_count += int(bool(reached & RESPONSE_STATUSES))
        interview_count += int(bool(reached & INTERVIEW_STATUSES))
        offer_count += int(bool(reached & OFFER_STATUSES))
        accepted_count += int("accepted" in reached)

    return {
        "applied_count": applied_count,
        "response_count": response_count,
        "interview_count": interview_count,
        "offer_count": offer_count,
        "accepted_count": accepted_count,
        "response_rate": _percentage(response_count, applied_count),
        "interview_conversion_rate": _percentage(interview_count, applied_count),
        "offer_conversion_rate": _percentage(offer_count, applied_count),
    }


def get_pipeline_view() -> dict[str, list[dict]]:
    """Return applications grouped by status for kanban display."""
    apps = list_applications()
    columns: dict[str, list[dict]] = {
        "saved": [], "applied": [], "oa": [],
        "interview": [], "offer": [], "accepted": [],
        "rejected": [], "withdrawn": [],
    }

    for app in apps:
        status = app.status
        if status in columns:
            columns[status].append({
                "id": app.id,
                "jd_id": app.jd_id,
                "resume_id": app.resume_id,
                "match_id": app.match_id,
                "status": status,
                "applied_date": app.applied_date,
                "notes": app.notes,
                "next_step": app.next_step,
                "next_step_due": app.next_step_due,
                "interview_at": app.interview_at,
                "updated_at": app.updated_at,
            })

    return columns


def _row_to_app(row: dict) -> Application:
    return Application(
        id=row["id"],
        user_id=row.get("user_id", 1),
        jd_id=row.get("jd_id", 0),
        resume_id=row.get("resume_id", 0),
        match_id=row.get("match_id", 0),
        status=row.get("status", "saved"),
        applied_date=row.get("applied_date", ""),
        notes=row.get("notes", ""),
        next_step=row.get("next_step", ""),
        next_step_due=row.get("next_step_due", ""),
        interview_at=row.get("interview_at", ""),
        updated_at=row.get("updated_at", ""),
    )


def _append_event(
    db,
    application_id: int,
    event_type: str,
    title: str,
    *,
    details: str = "",
    from_status: str = "",
    to_status: str = "",
    occurred_at: str = "",
) -> ApplicationEvent:
    now = occurred_at or _now()
    event = ApplicationEvent(
        application_id=application_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        title=title,
        details=details,
        occurred_at=now,
        created_at=_now(),
    )
    event.id = db.insert("application_events", event)
    return event


def _validate_datetime(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ProgressError(f"{label} must be a string")
    clean_value = value.strip()
    if not clean_value:
        return ""
    try:
        datetime.strptime(clean_value, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ProgressError(f"{label} must use YYYY-MM-DD HH:MM format") from exc
    return clean_value


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _percentage(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0
