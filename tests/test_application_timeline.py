"""Tests for application events, next actions, and interview scheduling."""

import sqlite3
from unittest.mock import patch

import pytest

from src.core.progress_manager import (
    ProgressError,
    add_note,
    create_application,
    get_application_timeline,
    schedule_interview,
    set_next_action,
    update_status,
)
from src.db.models import JobDescription, Resume
from src.db.sqlite_client import Database


@pytest.fixture
def timeline_db(tmp_path):
    db = Database(tmp_path / "timeline.db")
    resume = Resume(name="Resume", latex_path="")
    resume.id = db.insert("resumes", resume)
    jd = JobDescription(company="Acme", position="Engineer")
    jd.id = db.insert("job_descriptions", jd)
    db.test_resume_id = resume.id
    db.test_jd_id = jd.id
    yield db
    db.close()


def _create(db):
    with patch("src.core.progress_manager.get_db", return_value=db):
        return create_application(db.test_jd_id, db.test_resume_id)


def test_create_application_appends_creation_event(timeline_db):
    app = _create(timeline_db)

    with patch("src.core.progress_manager.get_db", return_value=timeline_db):
        events = get_application_timeline(app.id)

    assert len(events) == 1
    assert events[0].event_type == "created"
    assert events[0].to_status == "saved"


def test_status_change_appends_event_without_changing_transition_rules(timeline_db):
    app = _create(timeline_db)

    with patch("src.core.progress_manager.get_db", return_value=timeline_db):
        updated = update_status(app.id, "applied", "Submitted on company site")
        events = get_application_timeline(app.id)

    assert updated.status == "applied"
    assert updated.applied_date
    assert events[-1].event_type == "status_changed"
    assert events[-1].from_status == "saved"
    assert events[-1].to_status == "applied"

    with patch("src.core.progress_manager.get_db", return_value=timeline_db):
        with pytest.raises(ProgressError, match="Cannot transition"):
            update_status(app.id, "offer")


def test_next_action_and_deadline_are_saved_and_audited(timeline_db):
    app = _create(timeline_db)

    with patch("src.core.progress_manager.get_db", return_value=timeline_db):
        updated = set_next_action(
            app.id,
            "Prepare system design examples",
            "2026-12-02 18:30",
            "Focus on scaling trade-offs",
        )
        events = get_application_timeline(app.id)

    assert updated.next_step == "Prepare system design examples"
    assert updated.next_step_due == "2026-12-02 18:30"
    assert events[-1].event_type == "next_action_updated"
    assert events[-1].details == "Focus on scaling trade-offs"


def test_interview_time_does_not_change_application_status(timeline_db):
    app = _create(timeline_db)

    with patch("src.core.progress_manager.get_db", return_value=timeline_db):
        updated = schedule_interview(
            app.id,
            "2026-12-05 10:00",
            "Technical interview",
        )
        events = get_application_timeline(app.id)

    assert updated.status == "saved"
    assert updated.interview_at == "2026-12-05 10:00"
    assert events[-1].event_type == "interview_scheduled"


def test_note_is_required_and_appears_in_timeline(timeline_db):
    app = _create(timeline_db)

    with patch("src.core.progress_manager.get_db", return_value=timeline_db):
        with pytest.raises(ProgressError, match="cannot be empty"):
            add_note(app.id, "  ")
        add_note(app.id, "Recruiter requested availability")
        events = get_application_timeline(app.id)

    assert events[-1].event_type == "note_added"
    assert events[-1].details == "Recruiter requested availability"


def test_invalid_schedule_format_is_rejected_without_event(timeline_db):
    app = _create(timeline_db)

    with patch("src.core.progress_manager.get_db", return_value=timeline_db):
        with pytest.raises(ProgressError, match="YYYY-MM-DD HH:MM"):
            schedule_interview(app.id, "next Tuesday")
        events = get_application_timeline(app.id)

    assert [event.event_type for event in events] == ["created"]


def test_existing_database_receives_new_time_columns(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            jd_id INTEGER NOT NULL,
            resume_id INTEGER NOT NULL,
            match_id INTEGER,
            status TEXT DEFAULT 'saved',
            applied_date TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            next_step TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
        """
    )
    connection.commit()
    connection.close()

    db = Database(path)
    columns = {
        row[1] for row in db._conn.execute("PRAGMA table_info(applications)")
    }
    db.close()

    assert "next_step_due" in columns
    assert "interview_at" in columns
