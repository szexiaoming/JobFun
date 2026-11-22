"""End-to-end Phase 3 interview practice workflow acceptance tests."""

import copy

from src.core.interview_follow_up import generate_follow_up, get_follow_ups
from src.core.interview_insights import get_interview_insights, get_question_progress
from src.core.interview_practice import evaluate_text_answer
from src.db.models import Application, InterviewQuestion, JobDescription, MatchResult, Resume
from src.db.sqlite_client import Database


class FakeClient:
    def __init__(self, response):
        self.response = response

    def _call(self, **kwargs):
        return copy.deepcopy(self.response)


def _evaluation(scores, *, citation=None, next_practice="继续练习"):
    citations = [citation] if citation else []
    return {
        "scores": {
            "completeness": scores[0],
            "truthfulness": scores[1],
            "technical": scores[2],
            "structure": scores[3],
        },
        "feedback": {
            "summary": "基于当前回答生成的评价。",
            "strengths": ["回答包含具体做法。"],
            "improvements": ["补充验证方法和技术取舍。"],
            "next_practice": next_practice,
            "evidence_citations": citations,
            "unsupported_claims": [],
        },
    }


def test_complete_answer_evidence_follow_up_repeat_and_progress_flow(tmp_path):
    db = Database(tmp_path / "phase3-workflow.db")
    try:
        resume_id = db.insert(
            "resumes",
            Resume(
                name="Historical Backend Resume",
                base_version=2,
                latex_path="",
                structured_json={
                    "sections": [{
                        "title": "项目经历",
                        "entries": [{
                            "header": "任务平台",
                            "bullets": [{
                                "text": "构建异步任务系统，并实现幂等、重试和死信队列。",
                                "source_id": "bul_async",
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
            MatchResult(resume_id=resume_id, jd_id=jd_id, total_score=82),
        )
        application_id = db.insert(
            "applications",
            Application(
                jd_id=jd_id,
                resume_id=resume_id,
                match_id=match_id,
                status="interview",
            ),
        )
        question_id = db.insert(
            "interview_questions",
            InterviewQuestion(
                match_id=match_id,
                category="technical",
                question="如何设计可靠的异步任务系统？",
                difficulty="hard",
            ),
        )

        first_answer = "我曾构建异步任务系统，并使用幂等键和死信队列。"
        first = evaluate_text_answer(
            question_id,
            first_answer,
            application_id=application_id,
            db=db,
            client=FakeClient(_evaluation(
                (3, 4, 2, 3),
                citation={
                    "source_id": "bul_async",
                    "claim": "构建异步任务系统",
                    "support_level": "supported",
                    "note": "历史简历包含相同项目事实。",
                },
                next_practice="补充故障注入和监控指标。",
            )),
        )
        assert first.feedback["evidence_citations"][0]["resume_id"] == resume_id
        assert first.feedback["evidence_citations"][0]["text"].startswith("构建异步")

        follow_up = generate_follow_up(
            first.attempt_id,
            db=db,
            client=FakeClient({
                "question": "你会如何验证重试策略在故障场景下有效？",
                "target_dimension": "technical",
                "rationale": "第一次回答的技术正确性分数最低。",
            }),
        )
        follow_up_result = evaluate_text_answer(
            follow_up.question_id,
            "我会注入超时故障，并检查重试次数、积压量和死信指标。",
            application_id=application_id,
            db=db,
            client=FakeClient(_evaluation((4, 4, 4, 4))),
        )
        assert follow_up_result.application_id == application_id
        assert get_follow_ups(first.attempt_id, db=db)[0].question_id == follow_up.question_id

        second = evaluate_text_answer(
            question_id,
            "我会先定义投递语义，再用幂等键、指数退避、死信队列和故障注入验证方案。",
            application_id=application_id,
            db=db,
            client=FakeClient(_evaluation(
                (4, 4, 4, 4),
                next_practice="练习用一分钟说明完整取舍。",
            )),
        )
        progress = get_question_progress(
            question_id,
            application_id=application_id,
            db=db,
        )
        assert [item.evaluation.attempt_id for item in progress] == [
            second.attempt_id,
            first.attempt_id,
        ]
        assert progress[0].score_deltas == {
            "completeness": 1,
            "truthfulness": 0,
            "technical": 2,
            "structure": 1,
        }

        insights = get_interview_insights(
            match_id,
            application_id=application_id,
            db=db,
        )
        assert insights.attempt_count == 3
        assert insights.main_attempt_count == 2
        assert insights.follow_up_attempt_count == 1
        assert insights.comparison_count == 1
        assert insights.dimension_changes["technical"] == 2.0
        assert insights.recommendations[0].question_id == question_id
        assert insights.recommendations[0].next_practice == "练习用一分钟说明完整取舍。"
    finally:
        db.close()
