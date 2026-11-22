"""Tests for interview attempt history, progress, and weakness aggregation."""

import pytest

from src.core.interview_insights import (
    get_interview_insights,
    get_question_progress,
)
from src.db.models import InterviewAttempt, InterviewFollowUp, InterviewQuestion
from src.db.sqlite_client import Database


def _attempt(
    question_id,
    application_id,
    scores,
    *,
    next_practice="继续练习",
):
    return InterviewAttempt(
        question_id=question_id,
        application_id=application_id,
        answer_text=f"Answer for question {question_id}",
        completeness_score=scores[0],
        truthfulness_score=scores[1],
        technical_score=scores[2],
        structure_score=scores[3],
        feedback_json={
            "summary": "Saved evaluation",
            "next_practice": next_practice,
        },
    )


@pytest.fixture
def insights_db(tmp_path):
    db = Database(tmp_path / "interview-insights.db")
    technical_id = db.insert(
        "interview_questions",
        InterviewQuestion(
            match_id=7,
            category="technical",
            question="Explain retry design",
        ),
    )
    behavioral_id = db.insert(
        "interview_questions",
        InterviewQuestion(
            match_id=7,
            category="behavioral",
            question="Describe a conflict",
        ),
    )
    follow_up_question_id = db.insert(
        "interview_questions",
        InterviewQuestion(
            match_id=7,
            category="technical",
            question="How did you test retries?",
        ),
    )

    first_attempt_id = db.insert(
        "interview_attempts",
        _attempt(technical_id, 11, (2, 3, 2, 3)),
    )
    db.insert(
        "interview_attempts",
        _attempt(technical_id, 11, (3, 4, 4, 3), next_practice="Add metrics"),
    )
    db.insert(
        "interview_attempts",
        _attempt(technical_id, 22, (5, 5, 5, 5)),
    )
    db.insert(
        "interview_attempts",
        _attempt(behavioral_id, 11, (4, 2, 3, 4), next_practice="Use STAR"),
    )
    db.insert(
        "interview_follow_ups",
        InterviewFollowUp(
            parent_attempt_id=first_attempt_id,
            question_id=follow_up_question_id,
            target_dimension="technical",
            rationale="Probe validation",
        ),
    )
    db.insert(
        "interview_attempts",
        _attempt(follow_up_question_id, 11, (3, 3, 4, 3)),
    )
    db.technical_id = technical_id
    db.behavioral_id = behavioral_id
    db.follow_up_question_id = follow_up_question_id
    yield db
    db.close()


def test_same_question_history_has_attempt_numbers_and_deltas(insights_db):
    progress = get_question_progress(
        insights_db.technical_id,
        application_id=11,
        db=insights_db,
    )

    assert [item.attempt_number for item in progress] == [2, 1]
    assert progress[0].score_deltas == {
        "completeness": 1,
        "truthfulness": 1,
        "technical": 2,
        "structure": 0,
    }
    assert progress[0].overall_delta == 1.0
    assert progress[1].overall_delta is None


def test_history_is_isolated_by_application(insights_db):
    progress = get_question_progress(
        insights_db.technical_id,
        application_id=22,
        db=insights_db,
    )

    assert len(progress) == 1
    assert progress[0].evaluation.overall_score == 5.0
    assert progress[0].attempt_number == 1


def test_insights_aggregate_dimensions_categories_and_attempt_types(insights_db):
    insights = get_interview_insights(7, application_id=11, db=insights_db)

    assert insights.attempt_count == 4
    assert insights.practiced_question_count == 3
    assert insights.main_attempt_count == 3
    assert insights.follow_up_attempt_count == 1
    assert insights.comparison_count == 1
    assert insights.overall_average == 3.12
    assert insights.dimension_averages == {
        "completeness": 3.0,
        "truthfulness": 3.0,
        "technical": 3.25,
        "structure": 3.25,
    }
    assert insights.dimension_changes == {
        "completeness": 1.0,
        "truthfulness": 1.0,
        "technical": 2.0,
        "structure": 0.0,
    }
    assert insights.category_averages == {
        "behavioral": 3.25,
        "technical": 3.08,
    }


def test_weak_areas_and_recommendations_use_latest_main_attempt(insights_db):
    insights = get_interview_insights(7, application_id=11, db=insights_db)

    assert set(insights.weak_dimensions) == {
        "completeness", "truthfulness", "technical", "structure"
    }
    assert insights.weak_categories == ["technical", "behavioral"]
    assert [item.question_id for item in insights.recommendations] == [
        insights_db.behavioral_id,
        insights_db.technical_id,
    ]
    first = insights.recommendations[0]
    assert first.latest_score == 3.25
    assert first.weakest_dimension == "truthfulness"
    assert first.next_practice == "Use STAR"
    assert insights_db.follow_up_question_id not in {
        item.question_id for item in insights.recommendations
    }


def test_high_scoring_application_has_no_weak_areas(insights_db):
    insights = get_interview_insights(7, application_id=22, db=insights_db)

    assert insights.attempt_count == 1
    assert insights.overall_average == 5.0
    assert insights.weak_dimensions == []
    assert insights.weak_categories == []


def test_empty_match_returns_safe_zero_state(insights_db):
    insights = get_interview_insights(999, application_id=11, db=insights_db)

    assert insights.attempt_count == 0
    assert insights.overall_average == 0.0
    assert insights.dimension_averages == {
        "completeness": 0.0,
        "truthfulness": 0.0,
        "technical": 0.0,
        "structure": 0.0,
    }
    assert insights.recommendations == []
