"""Tests for application response and conversion metrics."""

from src.core.progress_manager import calculate_funnel_metrics


def test_empty_funnel_returns_zero_without_division_error():
    metrics = calculate_funnel_metrics([], [])

    assert metrics["applied_count"] == 0
    assert metrics["response_rate"] == 0.0
    assert metrics["interview_conversion_rate"] == 0.0
    assert metrics["offer_conversion_rate"] == 0.0


def test_saved_and_pre_application_withdrawal_are_excluded():
    applications = [
        {"id": 1, "status": "saved", "applied_date": ""},
        {"id": 2, "status": "withdrawn", "applied_date": ""},
        {"id": 3, "status": "applied", "applied_date": "2026-11-20"},
    ]

    metrics = calculate_funnel_metrics(applications, [])

    assert metrics["applied_count"] == 1
    assert metrics["response_count"] == 0


def test_rejection_after_application_counts_as_response():
    applications = [
        {"id": 1, "status": "rejected", "applied_date": "2026-11-20"},
        {"id": 2, "status": "applied", "applied_date": "2026-11-20"},
    ]

    metrics = calculate_funnel_metrics(applications, [])

    assert metrics["applied_count"] == 2
    assert metrics["response_count"] == 1
    assert metrics["response_rate"] == 50.0


def test_history_preserves_interview_conversion_after_later_rejection():
    applications = [
        {"id": 7, "status": "rejected", "applied_date": "2026-11-20"},
    ]
    events = [
        {"application_id": 7, "to_status": "applied"},
        {"application_id": 7, "to_status": "interview"},
        {"application_id": 7, "to_status": "rejected"},
    ]

    metrics = calculate_funnel_metrics(applications, events)

    assert metrics["response_rate"] == 100.0
    assert metrics["interview_conversion_rate"] == 100.0
    assert metrics["offer_conversion_rate"] == 0.0


def test_repeated_events_count_each_application_only_once():
    applications = [
        {"id": 4, "status": "offer", "applied_date": "2026-11-20"},
    ]
    events = [
        {"application_id": 4, "to_status": "interview"},
        {"application_id": 4, "to_status": "interview"},
        {"application_id": 4, "to_status": "offer"},
    ]

    metrics = calculate_funnel_metrics(applications, events)

    assert metrics["applied_count"] == 1
    assert metrics["response_count"] == 1
    assert metrics["interview_count"] == 1
    assert metrics["offer_count"] == 1


def test_accepted_application_reaches_every_funnel_milestone():
    applications = [
        {"id": 9, "status": "accepted", "applied_date": "2026-11-20"},
    ]

    metrics = calculate_funnel_metrics(applications, [])

    assert metrics["response_rate"] == 100.0
    assert metrics["interview_conversion_rate"] == 100.0
    assert metrics["offer_conversion_rate"] == 100.0
    assert metrics["accepted_count"] == 1
