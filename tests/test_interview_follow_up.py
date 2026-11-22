"""Tests for persisted, targeted interview follow-up questions."""

from unittest.mock import patch

import pytest

from src.core.interview_follow_up import (
    MAX_FOLLOW_UPS_PER_ATTEMPT,
    InterviewFollowUpError,
    generate_follow_up,
    get_follow_ups,
)
from src.core.interview_generator import _save_to_db, get_saved_questions
from src.core.interview_practice import evaluate_text_answer, get_question_attempts
from src.db.models import InterviewAttempt, InterviewQuestion
from src.db.sqlite_client import Database


FOLLOW_UP_RESPONSE = {
    "question": "你如何证明重试策略在故障场景下确实有效？",
    "target_dimension": "technical",
    "rationale": "原回答的技术正确性分数最低，缺少验证方法。",
}

EVALUATION_RESPONSE = {
    "scores": {
        "completeness": 4,
        "truthfulness": 4,
        "technical": 4,
        "structure": 4,
    },
    "feedback": {
        "summary": "追问回答覆盖了验证方法。",
        "strengths": ["给出了具体故障场景。"],
        "improvements": ["补充监控阈值。"],
        "next_practice": "用更短的顺序说明验证步骤。",
        "evidence_citations": [],
        "unsupported_claims": [],
    },
}


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def _call(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


@pytest.fixture
def follow_up_db(tmp_path):
    db = Database(tmp_path / "follow-up.db")
    question_id = db.insert(
        "interview_questions",
        InterviewQuestion(
            match_id=42,
            category="technical",
            question="如何设计可靠的异步任务系统？",
            difficulty="hard",
        ),
    )
    attempt_id = db.insert(
        "interview_attempts",
        InterviewAttempt(
            question_id=question_id,
            answer_text="我会增加重试和死信队列。",
            completeness_score=3,
            truthfulness_score=4,
            technical_score=2,
            structure_score=3,
            feedback_json={
                "summary": "方向正确，但缺少验证和取舍。",
                "improvements": ["说明如何验证重试策略。"],
                "next_practice": "补充故障测试。",
                "evidence_citations": [],
                "unsupported_claims": [],
            },
        ),
    )
    db.test_question_id = question_id
    db.test_attempt_id = attempt_id
    yield db
    db.close()


def test_follow_up_is_linked_to_attempt_and_saved_as_answerable_question(follow_up_db):
    client = FakeClient(FOLLOW_UP_RESPONSE)

    follow_up = generate_follow_up(
        follow_up_db.test_attempt_id,
        db=follow_up_db,
        client=client,
    )

    assert follow_up.parent_attempt_id == follow_up_db.test_attempt_id
    assert follow_up.target_dimension == "technical"
    saved_question = follow_up_db.get("interview_questions", follow_up.question_id)
    assert saved_question["match_id"] == 42
    assert saved_question["question"] == FOLLOW_UP_RESPONSE["question"]
    assert "我会增加重试和死信队列" in client.calls[0]["user_text"]
    assert '"selected_target_dimension": "technical"' in client.calls[0]["user_text"]
    assert get_follow_ups(follow_up_db.test_attempt_id, db=follow_up_db) == [follow_up]


def test_follow_up_answer_uses_the_existing_evaluation_pipeline(follow_up_db):
    follow_up = generate_follow_up(
        follow_up_db.test_attempt_id,
        db=follow_up_db,
        client=FakeClient(FOLLOW_UP_RESPONSE),
    )

    evaluation = evaluate_text_answer(
        follow_up.question_id,
        "我会注入超时故障，并检查重试次数和死信队列指标。",
        db=follow_up_db,
        client=FakeClient(EVALUATION_RESPONSE),
    )

    assert evaluation.question_id == follow_up.question_id
    assert len(get_question_attempts(follow_up.question_id, db=follow_up_db)) == 1


def test_unsupported_claim_forces_truthfulness_follow_up(follow_up_db):
    follow_up_db.update(
        "interview_attempts",
        follow_up_db.test_attempt_id,
        {"feedback_json": '{"unsupported_claims":[{"claim":"百万任务"}]}'},
    )
    response = {
        "question": "你提到百万任务，这一规模数据是如何测量的？",
        "target_dimension": "truthfulness",
        "rationale": "该规模声明未获得历史简历证据支持。",
    }

    result = generate_follow_up(
        follow_up_db.test_attempt_id,
        db=follow_up_db,
        client=FakeClient(response),
    )

    assert result.target_dimension == "truthfulness"


def test_model_cannot_redirect_follow_up_to_another_dimension(follow_up_db):
    invalid = {**FOLLOW_UP_RESPONSE, "target_dimension": "structure"}

    with pytest.raises(InterviewFollowUpError, match="selected dimension: technical"):
        generate_follow_up(
            follow_up_db.test_attempt_id,
            db=follow_up_db,
            client=FakeClient(invalid),
        )

    assert follow_up_db.count("interview_follow_ups") == 0


def test_invalid_follow_up_schema_creates_no_question_or_relation(follow_up_db):
    before_questions = follow_up_db.count("interview_questions")

    with pytest.raises(InterviewFollowUpError, match="required format"):
        generate_follow_up(
            follow_up_db.test_attempt_id,
            db=follow_up_db,
            client=FakeClient({"question": "Missing fields"}),
        )

    assert follow_up_db.count("interview_questions") == before_questions
    assert follow_up_db.count("interview_follow_ups") == 0


def test_follow_up_limit_is_enforced_before_another_model_call(follow_up_db):
    for _ in range(MAX_FOLLOW_UPS_PER_ATTEMPT):
        generate_follow_up(
            follow_up_db.test_attempt_id,
            db=follow_up_db,
            client=FakeClient(FOLLOW_UP_RESPONSE),
        )
    blocked_client = FakeClient(FOLLOW_UP_RESPONSE)

    with pytest.raises(InterviewFollowUpError, match="at most 3"):
        generate_follow_up(
            follow_up_db.test_attempt_id,
            db=follow_up_db,
            client=blocked_client,
        )

    assert blocked_client.calls == []
    assert follow_up_db.count("interview_follow_ups") == 3


def test_unknown_parent_attempt_is_rejected(follow_up_db):
    with pytest.raises(InterviewFollowUpError, match="not found"):
        generate_follow_up(9999, db=follow_up_db, client=FakeClient(FOLLOW_UP_RESPONSE))


def test_question_regeneration_preserves_unanswered_follow_up(follow_up_db):
    follow_up = generate_follow_up(
        follow_up_db.test_attempt_id,
        db=follow_up_db,
        client=FakeClient(FOLLOW_UP_RESPONSE),
    )

    with patch("src.core.interview_generator.get_db", return_value=follow_up_db):
        _save_to_db(
            42,
            {"technical": [{"question": "A newly generated main question"}]},
        )

    assert follow_up_db.get("interview_questions", follow_up.question_id) is not None
    assert get_follow_ups(follow_up_db.test_attempt_id, db=follow_up_db)[0].id == follow_up.id


def test_follow_ups_do_not_appear_as_top_level_saved_questions(follow_up_db):
    follow_up = generate_follow_up(
        follow_up_db.test_attempt_id,
        db=follow_up_db,
        client=FakeClient(FOLLOW_UP_RESPONSE),
    )

    with patch("src.core.interview_generator.get_db", return_value=follow_up_db):
        saved = get_saved_questions(42)

    saved_ids = {
        item["id"]
        for questions in saved.values()
        for item in questions
    }
    assert follow_up_db.test_question_id in saved_ids
    assert follow_up.question_id not in saved_ids
