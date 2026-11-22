"""
Tests for match engine (mocked AI client).
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.match_engine import MatchEngineError, run_match
from src.db.models import MatchResult, Resume, Suggestion


MOCK_JD = {
    "company": "TestCorp",
    "position": "Software Engineer",
    "required_skills": ["Python", "AWS", "Docker"],
    "preferred_skills": ["Kubernetes"],
    "years_experience": 3,
    "level": "Mid",
}

MOCK_RESUME = {
    "preamble": {"packages": ["hyperref"]},
    "sections": [
        {
            "title": "Experience",
            "entries": [
                {
                    "header": "Dev @ Startup, 2023-Present",
                    "bullets": [
                        "Built APIs with Python and AWS Lambda",
                        "Containerized services with Docker",
                    ],
                }
            ],
        },
        {
            "title": "Education",
            "entries": [
                {"header": "B.S. CS, 2021", "bullets": []}
            ],
        },
    ],
}

MOCK_MATCH_RESPONSE = {
    "total_score": 78,
    "skill_score": 85,
    "experience_score": 72,
    "education_score": 90,
    "soft_skill_score": 65,
    "culture_score": 70,
    "matched_skills": ["Python", "AWS", "Docker"],
    "missing_skills": ["Kubernetes"],
    "risks": ["No K8s experience"],
    "summary": "Good match overall, missing one key skill.",
    "suggestions": [
        {
            "category": "keyword",
            "priority": 1,
            "original_text": "Containerized services with Docker",
            "suggested_text": "Containerized microservices with Docker; exploring Kubernetes orchestration",
            "rationale": "Mention K8s adjacency",
        },
        {
            "category": "wording",
            "priority": 2,
            "original_text": "Built APIs with Python and AWS Lambda",
            "suggested_text": "Architected serverless APIs with Python on AWS Lambda, handling 10K req/min",
            "rationale": "Stronger verbs + quantification",
        },
    ],
}


def _make_mock_openai_response(content_dict: dict) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps(content_dict, ensure_ascii=False)
    response.usage = MagicMock()
    response.usage.prompt_tokens = 300
    response.usage.completion_tokens = 500
    return response


@pytest.fixture
def mock_ai_client():
    with patch("src.ai.client.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response(MOCK_MATCH_RESPONSE)
        mock_cls.return_value = mock_client

        # Reset the singleton so it picks up the mock
        from src.ai.client import reset_ai_client
        reset_ai_client()
        yield mock_cls
        reset_ai_client()


@pytest.fixture
def mock_db():
    with patch("src.core.match_engine.get_db") as mock:
        db = MagicMock()
        db.insert.return_value = 42
        mock.return_value = db
        yield mock


class TestRunMatch:
    def test_successful_match(self, mock_ai_client, mock_db):
        resume = Resume(id=1, name="Test Resume", latex_path="/tmp/resume")
        result = run_match(resume, MOCK_JD, MOCK_RESUME, jd_id=7)

        assert result["match_result"].total_score == 78
        assert result["match_result"].jd_id == 7
        assert json.loads(result["match_result"].raw_report)["total_score"] == 78
        assert result["match_result"].skill_score == 85
        assert len(result["matched_skills"]) == 3
        assert len(result["missing_skills"]) == 1
        assert len(result["suggestions"]) == 2
        assert result["suggestions"][0].category == "keyword"

    def test_empty_jd_raises_error(self, mock_ai_client, mock_db):
        resume = Resume(id=1, name="Test", latex_path="/tmp/resume")
        with pytest.raises(MatchEngineError, match="JD is empty"):
            run_match(resume, {}, MOCK_RESUME)

    def test_empty_resume_raises_error(self, mock_ai_client, mock_db):
        resume = Resume(id=1, name="Test", latex_path="/tmp/resume")
        with pytest.raises(MatchEngineError, match="Resume has no parsed sections"):
            run_match(resume, MOCK_JD, {"sections": []})


class TestMatchResultModel:
    def test_match_result_creation(self):
        match = MatchResult(
            resume_id=1,
            jd_id=2,
            total_score=78.5,
            skill_score=85.0,
            matched_skills=["Python", "AWS"],
            missing_skills=["K8s"],
            risks=["Risk 1"],
        )
        assert match.total_score == 78.5
        assert len(match.matched_skills) == 2
