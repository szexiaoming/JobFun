"""Regression tests for application lifecycle rules."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.progress_manager import (
    ProgressError,
    create_application,
    get_pipeline_view,
    update_status,
)
from src.db.models import Application


def test_saved_application_has_no_applied_date():
    db = MagicMock()
    db.insert.return_value = 12

    with patch("src.core.progress_manager.get_db", return_value=db):
        app = create_application(jd_id=3, resume_id=4)

    assert app.status == "saved"
    assert app.applied_date == ""
    assert app.jd_id == 3
    assert app.resume_id == 4


def test_terminal_status_cannot_transition():
    db = MagicMock()
    db.get.return_value = {"id": 9, "status": "accepted", "notes": ""}

    with patch("src.core.progress_manager.get_db", return_value=db):
        with pytest.raises(ProgressError, match="Cannot transition"):
            update_status(9, "applied")

    db.update.assert_not_called()


def test_applied_date_is_set_on_applied_transition():
    db = MagicMock()
    saved = {
        "id": 9,
        "user_id": 1,
        "jd_id": 3,
        "resume_id": 4,
        "match_id": 5,
        "status": "saved",
        "applied_date": "",
        "notes": "",
        "next_step": "",
        "updated_at": "",
    }
    applied = dict(saved, status="applied", applied_date="2026-11-19")
    db.get.side_effect = [saved, applied]

    with patch("src.core.progress_manager.get_db", return_value=db):
        update_status(9, "applied")

    updates = db.update.call_args.args[2]
    assert updates["status"] == "applied"
    assert updates["applied_date"]


def test_pipeline_keeps_all_terminal_states_visible():
    apps = [
        Application(id=1, status="accepted"),
        Application(id=2, status="rejected"),
        Application(id=3, status="withdrawn"),
    ]

    with patch("src.core.progress_manager.list_applications", return_value=apps):
        pipeline = get_pipeline_view()

    assert [item["id"] for item in pipeline["accepted"]] == [1]
    assert [item["id"] for item in pipeline["rejected"]] == [2]
    assert [item["id"] for item in pipeline["withdrawn"]] == [3]
