"""Read-only interview attempt history, progress, and weakness aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.core.interview_practice import (
    RUBRIC_DIMENSIONS,
    InterviewEvaluation,
    get_question_attempts,
)
from src.db.sqlite_client import Database, get_db


WEAK_SCORE_THRESHOLD = 3.5


@dataclass(frozen=True)
class AttemptProgress:
    evaluation: InterviewEvaluation
    attempt_number: int
    score_deltas: dict[str, Optional[int]]
    overall_delta: Optional[float]


@dataclass(frozen=True)
class PracticeRecommendation:
    question_id: int
    question: str
    category: str
    attempt_count: int
    latest_score: float
    weakest_dimension: str
    next_practice: str


@dataclass(frozen=True)
class InterviewInsights:
    attempt_count: int = 0
    practiced_question_count: int = 0
    comparison_count: int = 0
    main_attempt_count: int = 0
    follow_up_attempt_count: int = 0
    overall_average: float = 0.0
    dimension_averages: dict[str, float] = field(default_factory=dict)
    dimension_changes: dict[str, float] = field(default_factory=dict)
    category_averages: dict[str, float] = field(default_factory=dict)
    weak_dimensions: list[str] = field(default_factory=list)
    weak_categories: list[str] = field(default_factory=list)
    recommendations: list[PracticeRecommendation] = field(default_factory=list)


def get_question_progress(
    question_id: int,
    *,
    application_id: Optional[int] = None,
    db: Optional[Database] = None,
) -> list[AttemptProgress]:
    """Return same-question attempts newest first with deltas from the prior try."""
    database = db or get_db()
    attempts = get_question_attempts(question_id, db=database)
    if application_id is not None:
        attempts = [
            attempt
            for attempt in attempts
            if attempt.application_id == application_id
        ]
    chronological = list(reversed(attempts))
    progress: list[AttemptProgress] = []
    previous: Optional[InterviewEvaluation] = None
    for number, attempt in enumerate(chronological, start=1):
        if previous is None:
            score_deltas = {dimension: None for dimension in RUBRIC_DIMENSIONS}
            overall_delta = None
        else:
            score_deltas = {
                dimension: attempt.scores[dimension] - previous.scores[dimension]
                for dimension in RUBRIC_DIMENSIONS
            }
            overall_delta = round(
                attempt.overall_score - previous.overall_score,
                2,
            )
        progress.append(AttemptProgress(
            evaluation=attempt,
            attempt_number=number,
            score_deltas=score_deltas,
            overall_delta=overall_delta,
        ))
        previous = attempt
    return list(reversed(progress))


def get_interview_insights(
    match_id: int,
    *,
    application_id: Optional[int] = None,
    db: Optional[Database] = None,
) -> InterviewInsights:
    """Aggregate attempts for one match and optional application context."""
    database = db or get_db()
    questions = database.find_by("interview_questions", "match_id", match_id)
    follow_up_ids = _follow_up_question_ids(database)
    samples: list[tuple[dict, InterviewEvaluation, bool]] = []
    recommendations: list[PracticeRecommendation] = []
    change_samples = {dimension: [] for dimension in RUBRIC_DIMENSIONS}
    comparison_count = 0

    for question in questions:
        question_id = int(question.get("id", 0) or 0)
        progress = get_question_progress(
            question_id,
            application_id=application_id,
            db=database,
        )
        is_follow_up = question_id in follow_up_ids
        for item in progress:
            samples.append((question, item.evaluation, is_follow_up))
        if len(progress) >= 2:
            comparison_count += 1
            latest = progress[0]
            for dimension, delta in latest.score_deltas.items():
                if delta is not None:
                    change_samples[dimension].append(delta)
        if progress and not is_follow_up:
            latest = progress[0].evaluation
            weakest = min(
                RUBRIC_DIMENSIONS,
                key=lambda dimension: latest.scores[dimension],
            )
            recommendations.append(PracticeRecommendation(
                question_id=question_id,
                question=question.get("question", ""),
                category=question.get("category", "other"),
                attempt_count=len(progress),
                latest_score=latest.overall_score,
                weakest_dimension=weakest,
                next_practice=str(latest.feedback.get("next_practice", "")).strip(),
            ))

    if not samples:
        return InterviewInsights(
            dimension_averages={dimension: 0.0 for dimension in RUBRIC_DIMENSIONS},
            dimension_changes={dimension: 0.0 for dimension in RUBRIC_DIMENSIONS},
        )

    dimension_averages = {
        dimension: _average([
            evaluation.scores[dimension]
            for _, evaluation, _ in samples
        ])
        for dimension in RUBRIC_DIMENSIONS
    }
    category_scores: dict[str, list[float]] = {}
    for question, evaluation, _ in samples:
        category = question.get("category", "other") or "other"
        category_scores.setdefault(category, []).append(evaluation.overall_score)
    category_averages = {
        category: _average(values)
        for category, values in sorted(category_scores.items())
    }
    dimension_changes = {
        dimension: _average(values) if values else 0.0
        for dimension, values in change_samples.items()
    }
    weak_dimensions = [
        dimension
        for dimension, score in sorted(
            dimension_averages.items(),
            key=lambda item: (item[1], item[0]),
        )
        if score < WEAK_SCORE_THRESHOLD
    ]
    weak_categories = [
        category
        for category, score in sorted(
            category_averages.items(),
            key=lambda item: (item[1], item[0]),
        )
        if score < WEAK_SCORE_THRESHOLD
    ]
    recommendations.sort(
        key=lambda item: (item.latest_score, item.attempt_count, item.question_id)
    )

    return InterviewInsights(
        attempt_count=len(samples),
        practiced_question_count=len({
            int(question.get("id", 0) or 0)
            for question, _, _ in samples
        }),
        comparison_count=comparison_count,
        main_attempt_count=sum(1 for _, _, is_follow_up in samples if not is_follow_up),
        follow_up_attempt_count=sum(1 for _, _, is_follow_up in samples if is_follow_up),
        overall_average=_average([
            evaluation.overall_score
            for _, evaluation, _ in samples
        ]),
        dimension_averages=dimension_averages,
        dimension_changes=dimension_changes,
        category_averages=category_averages,
        weak_dimensions=weak_dimensions,
        weak_categories=weak_categories,
        recommendations=recommendations[:3],
    )


def _follow_up_question_ids(database: Database) -> set[int]:
    count = database.count("interview_follow_ups")
    return {
        int(row["question_id"])
        for row in database.list("interview_follow_ups", limit=max(count, 1))
    }


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0
