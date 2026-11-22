"""Read-only workbench summary for application actions and interviews."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from src.core.progress_manager import STATUS_FLOW
from src.db.sqlite_client import Database, get_db


@dataclass
class WorkbenchItem:
    application_id: int
    jd_id: int
    company: str
    position: str
    status: str
    next_step: str = ""
    next_step_due: str = ""
    interview_at: str = ""
    is_overdue: bool = False


@dataclass
class WorkbenchSummary:
    total_applications: int = 0
    active_applications: int = 0
    pending_actions: list[WorkbenchItem] = field(default_factory=list)
    overdue_actions: list[WorkbenchItem] = field(default_factory=list)
    upcoming_interviews: list[WorkbenchItem] = field(default_factory=list)


def get_workbench_summary(
    *,
    db: Optional[Database] = None,
    now: Optional[datetime] = None,
    interview_window_days: int = 7,
) -> WorkbenchSummary:
    """Aggregate current work without modifying application records."""
    database = db or get_db()
    current_time = now or datetime.now()
    applications = database.list("applications", limit=1000)
    jobs = {
        row["id"]: row
        for row in database.list("job_descriptions", limit=1000)
    }
    return build_workbench_summary(
        applications,
        jobs,
        now=current_time,
        interview_window_days=interview_window_days,
    )


def build_workbench_summary(
    applications: list[dict],
    jobs: dict[int, dict],
    *,
    now: Optional[datetime] = None,
    interview_window_days: int = 7,
) -> WorkbenchSummary:
    """Build the summary from an already ownership-scoped read model."""
    current_time = now or datetime.now()
    summary = WorkbenchSummary(total_applications=len(applications))

    for application in applications:
        status = application.get("status", "saved")
        if STATUS_FLOW.get(status):
            summary.active_applications += 1
        job = jobs.get(application.get("jd_id"), {})
        item = WorkbenchItem(
            application_id=application["id"],
            jd_id=application.get("jd_id", 0),
            company=job.get("company") or "未填写公司",
            position=job.get("position") or "未填写岗位",
            status=status,
            next_step=application.get("next_step", ""),
            next_step_due=application.get("next_step_due", ""),
            interview_at=application.get("interview_at", ""),
        )

        if item.next_step:
            due = _parse_datetime(item.next_step_due)
            item.is_overdue = bool(due and due < current_time)
            summary.pending_actions.append(item)
            if item.is_overdue:
                summary.overdue_actions.append(item)

        interview_time = _parse_datetime(item.interview_at)
        if (
            interview_time
            and current_time <= interview_time <= current_time + timedelta(days=interview_window_days)
        ):
            summary.upcoming_interviews.append(item)

    summary.pending_actions.sort(key=_action_sort_key)
    summary.overdue_actions.sort(key=_action_sort_key)
    summary.upcoming_interviews.sort(key=lambda item: item.interview_at)
    return summary


def _action_sort_key(item: WorkbenchItem) -> tuple:
    return (not item.is_overdue, item.next_step_due or "9999-12-31 23:59", item.application_id)


def _parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None
