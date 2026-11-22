"""Tests for written interview attempts, rubric, and grounded resume citations."""

import copy
import json
from unittest.mock import patch

import pytest

from src.core.interview_generator import _save_to_db, get_saved_questions
from src.core.interview_practice import (
    RUBRIC_DIMENSIONS,
    InterviewPracticeError,
    build_resume_evidence_sources,
    evaluate_text_answer,
    get_question_attempts,
)
from src.db.models import (
    Application,
    InterviewQuestion,
    JobDescription,
    MatchResult,
    Resume,
)
from src.db.sqlite_client import Database


VALID_EVALUATION = {
    "scores": {
        "completeness": 4,
        "truthfulness": 5,
        "technical": 3,
        "structure": 4,
    },
    "feedback": {
        "summary": "回答清晰，技术取舍还可以更具体。",
        "strengths": ["明确说明了自己的职责范围。"],
        "improvements": ["补充选择队列方案时比较过的替代方案。"],
        "next_practice": "用一句话先给结论，再说明两个关键取舍。",
        "evidence_citations": [],
        "unsupported_claims": [],
    },
}


class FakeEvaluationClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def _call(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


@pytest.fixture
def interview_db(tmp_path):
    db = Database(tmp_path / "interview-practice.db")
    resume_id = db.insert(
        "resumes",
        Resume(
            name="Backend",
            latex_path="",
            structured_json={
                "sections": [{
                    "title": "项目经历",
                    "entries": [{
                        "header": "任务平台",
                        "bullets": [{
                            "text": "构建异步任务系统，并实现幂等键、退避重试和死信队列。",
                            "source_id": "bul_queue",
                        }],
                    }],
                }],
            },
        ),
    )
    jd_id = db.insert(
        "job_descriptions",
        JobDescription(company="Acme", position="Backend Engineer"),
    )
    match_id = db.insert(
        "match_results",
        MatchResult(resume_id=resume_id, jd_id=jd_id, total_score=80),
    )
    application_id = db.insert(
        "applications",
        Application(jd_id=jd_id, resume_id=resume_id, match_id=match_id),
    )
    question_id = db.insert(
        "interview_questions",
        InterviewQuestion(
            match_id=match_id,
            category="technical",
            question="如何设计一个可靠的异步任务系统？",
            suggested_answer="说明一致性、重试和可观测性。",
            difficulty="hard",
        ),
    )
    db.test_match_id = match_id
    db.test_resume_id = resume_id
    db.test_application_id = application_id
    db.test_question_id = question_id
    yield db
    db.close()


def test_fixed_rubric_has_exactly_the_four_planned_dimensions():
    assert tuple(RUBRIC_DIMENSIONS) == (
        "completeness",
        "truthfulness",
        "technical",
        "structure",
    )


def test_written_answer_is_evaluated_and_persisted(interview_db):
    client = FakeEvaluationClient(VALID_EVALUATION)

    result = evaluate_text_answer(
        interview_db.test_question_id,
        "我会先定义投递语义，再设计幂等键、退避重试和死信队列。",
        application_id=interview_db.test_application_id,
        db=interview_db,
        client=client,
    )

    assert result.overall_score == 4.0
    assert result.application_id == interview_db.test_application_id
    assert result.feedback["next_practice"].startswith("用一句话")
    assert len(client.calls) == 1
    assert "0 to 5" in client.calls[0]["system"]
    assert "异步任务系统" in client.calls[0]["user_text"]
    assert len(get_question_attempts(interview_db.test_question_id, db=interview_db)) == 1


def test_empty_answer_is_rejected_before_model_call(interview_db):
    client = FakeEvaluationClient(VALID_EVALUATION)

    with pytest.raises(InterviewPracticeError, match="cannot be empty"):
        evaluate_text_answer(
            interview_db.test_question_id,
            "   ",
            db=interview_db,
            client=client,
        )

    assert client.calls == []
    assert interview_db.count("interview_attempts") == 0


def test_invalid_model_score_is_not_saved(interview_db):
    invalid = {
        **VALID_EVALUATION,
        "scores": {**VALID_EVALUATION["scores"], "technical": 6},
    }

    with pytest.raises(InterviewPracticeError, match="integer from 0 to 5"):
        evaluate_text_answer(
            interview_db.test_question_id,
            "这是一个待评价的完整回答。",
            db=interview_db,
            client=FakeEvaluationClient(invalid),
        )

    assert interview_db.count("interview_attempts") == 0


def test_application_must_share_the_question_match(interview_db):
    other_resume_id = interview_db.insert(
        "resumes", Resume(name="Other", latex_path="")
    )
    other_jd_id = interview_db.insert(
        "job_descriptions", JobDescription(company="Other", position="Role")
    )
    other_match_id = interview_db.insert(
        "match_results",
        MatchResult(resume_id=other_resume_id, jd_id=other_jd_id),
    )
    other_application_id = interview_db.insert(
        "applications",
        Application(
            jd_id=other_jd_id,
            resume_id=other_resume_id,
            match_id=other_match_id,
        ),
    )

    with pytest.raises(InterviewPracticeError, match="not linked"):
        evaluate_text_answer(
            interview_db.test_question_id,
            "这是一个不会发送给模型的回答。",
            application_id=other_application_id,
            db=interview_db,
            client=FakeEvaluationClient(VALID_EVALUATION),
        )

    assert interview_db.count("interview_attempts") == 0


def test_saved_questions_return_stable_ids_for_practice(interview_db):
    categories = {
        "behavioral": [{
            "question": "讲一次你处理项目风险的经历。",
            "difficulty": "medium",
            "tip": "使用 STAR。",
        }],
    }

    with patch("src.core.interview_generator.get_db", return_value=interview_db):
        saved = _save_to_db(interview_db.test_match_id, categories)
        loaded = get_saved_questions(interview_db.test_match_id)

    assert saved["behavioral"][0]["id"] > 0
    assert loaded["behavioral"][0]["id"] == saved["behavioral"][0]["id"]
    assert loaded["behavioral"][0]["match_id"] == interview_db.test_match_id


def test_regeneration_preserves_questions_with_saved_attempts(interview_db):
    evaluate_text_answer(
        interview_db.test_question_id,
        "我会先定义可靠性目标，再说明幂等、重试和监控方案。",
        db=interview_db,
        client=FakeEvaluationClient(VALID_EVALUATION),
    )

    with patch("src.core.interview_generator.get_db", return_value=interview_db):
        _save_to_db(
            interview_db.test_match_id,
            {"technical": [{"question": "新问题", "difficulty": "easy"}]},
        )

    assert interview_db.get(
        "interview_questions", interview_db.test_question_id
    ) is not None
    assert len(get_question_attempts(interview_db.test_question_id, db=interview_db)) == 1


def test_resume_evidence_sources_keep_stable_location_metadata(interview_db):
    resume = interview_db.get("resumes", interview_db.test_resume_id)

    sources = build_resume_evidence_sources(json.loads(resume["structured_json"]))

    assert sources == [{
        "source_id": "bul_queue",
        "text": "构建异步任务系统，并实现幂等键、退避重试和死信队列。",
        "section": "项目经历",
        "entry": "任务平台",
        "bullet_index": 0,
    }]


def test_evidence_citation_is_verified_and_enriched_from_historical_resume(interview_db):
    response = copy.deepcopy(VALID_EVALUATION)
    response["feedback"]["evidence_citations"] = [{
        "source_id": "bul_queue",
        "claim": "构建异步任务系统",
        "support_level": "supported",
        "note": "历史简历包含相同项目事实。",
    }]
    client = FakeEvaluationClient(response)

    result = evaluate_text_answer(
        interview_db.test_question_id,
        "我曾构建异步任务系统，并重点处理幂等和重试。",
        application_id=interview_db.test_application_id,
        db=interview_db,
        client=client,
    )

    citation = result.feedback["evidence_citations"][0]
    assert citation["resume_id"] == interview_db.test_resume_id
    assert citation["section"] == "项目经历"
    assert citation["entry"] == "任务平台"
    assert citation["bullet_index"] == 0
    assert citation["text"].startswith("构建异步任务系统")
    assert result.feedback["evidence_context"] == {
        "resume_id": interview_db.test_resume_id,
        "source_count": 1,
    }
    assert '"evidence_mode": "historical_resume"' in client.calls[0]["user_text"]
    assert '"source_id": "bul_queue"' in client.calls[0]["user_text"]


@pytest.mark.parametrize(
    ("source_id", "claim", "error"),
    [
        ("bul_unknown", "构建异步任务系统", "unknown resume source"),
        ("bul_queue", "不存在于回答中的断言", "not grounded in the answer"),
    ],
)
def test_invalid_evidence_citation_is_not_saved(
    interview_db,
    source_id,
    claim,
    error,
):
    response = copy.deepcopy(VALID_EVALUATION)
    response["feedback"]["evidence_citations"] = [{
        "source_id": source_id,
        "claim": claim,
        "support_level": "supported",
        "note": "测试引用。",
    }]

    with pytest.raises(InterviewPracticeError, match=error):
        evaluate_text_answer(
            interview_db.test_question_id,
            "我曾构建异步任务系统。",
            application_id=interview_db.test_application_id,
            db=interview_db,
            client=FakeEvaluationClient(response),
        )

    assert interview_db.count("interview_attempts") == 0


def test_evaluation_uses_bound_resume_instead_of_newer_resume(interview_db):
    interview_db.insert(
        "resumes",
        Resume(
            name="New Current Resume",
            base_version=2,
            latex_path="",
            structured_json={
                "sections": [{
                    "title": "新版本",
                    "entries": [{
                        "header": "其他项目",
                        "bullets": ["只存在于最新简历的内容"],
                    }],
                }],
            },
        ),
    )
    client = FakeEvaluationClient(VALID_EVALUATION)

    evaluate_text_answer(
        interview_db.test_question_id,
        "我会说明异步系统的设计。",
        application_id=interview_db.test_application_id,
        db=interview_db,
        client=client,
    )

    prompt = client.calls[0]["user_text"]
    assert "构建异步任务系统" in prompt
    assert "只存在于最新简历的内容" not in prompt


def test_unbound_practice_cannot_claim_resume_evidence(interview_db):
    response = copy.deepcopy(VALID_EVALUATION)
    response["feedback"]["evidence_citations"] = [{
        "source_id": "bul_queue",
        "claim": "构建异步任务系统",
        "support_level": "supported",
        "note": "不应被接受。",
    }]

    with pytest.raises(InterviewPracticeError, match="without a bound historical resume"):
        evaluate_text_answer(
            interview_db.test_question_id,
            "我曾构建异步任务系统。",
            db=interview_db,
            client=FakeEvaluationClient(response),
        )


def test_unsupported_claim_is_kept_only_when_grounded_in_answer(interview_db):
    response = copy.deepcopy(VALID_EVALUATION)
    response["feedback"]["unsupported_claims"] = [{
        "claim": "处理过每秒百万任务",
        "reason": "绑定简历只说明实现方案，没有这个规模指标。",
    }]

    result = evaluate_text_answer(
        interview_db.test_question_id,
        "我处理过每秒百万任务，并设计了重试方案。",
        application_id=interview_db.test_application_id,
        db=interview_db,
        client=FakeEvaluationClient(response),
    )

    assert result.feedback["unsupported_claims"] == [{
        "claim": "处理过每秒百万任务",
        "reason": "绑定简历只说明实现方案，没有这个规模指标。",
    }]


def test_confirmed_voice_transcript_metadata_is_persisted(interview_db):
    transcript = "我会先定义可靠性目标，再说明重试和监控。"

    result = evaluate_text_answer(
        interview_db.test_question_id,
        transcript,
        application_id=interview_db.test_application_id,
        audio_path="data/interview_audio/question_1/example.wav",
        transcript=transcript,
        db=interview_db,
        client=FakeEvaluationClient(VALID_EVALUATION),
    )
    stored = get_question_attempts(
        interview_db.test_question_id,
        db=interview_db,
    )[0]

    assert result.transcript == transcript
    assert result.audio_path.endswith("example.wav")
    assert stored.transcript == transcript
    assert stored.audio_path == result.audio_path


def test_voice_transcript_must_match_evaluated_answer(interview_db):
    client = FakeEvaluationClient(VALID_EVALUATION)

    with pytest.raises(InterviewPracticeError, match="must match"):
        evaluate_text_answer(
            interview_db.test_question_id,
            "Edited answer",
            transcript="Original transcript",
            db=interview_db,
            client=client,
        )

    assert client.calls == []
    assert interview_db.count("interview_attempts") == 0
