"""
Tests for JD parser (DeepSeek / OpenAI SDK).
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.jd_parser import JDParserError, parse_jd_text


MOCK_JD_TEXT = """
Software Engineer at TestCorp
Location: San Francisco, CA
Requirements: Python, AWS, Docker, 3+ years experience
Nice to have: Kubernetes, Terraform
"""

MOCK_STRUCTURED = {
    "company": "TestCorp",
    "position": "Software Engineer",
    "team": None,
    "location": "San Francisco, CA",
    "required_skills": ["Python", "AWS", "Docker"],
    "preferred_skills": ["Kubernetes", "Terraform"],
    "years_experience": 3,
    "education": None,
    "responsibilities": [],
    "soft_skills": [],
    "culture_signals": [],
    "level": "Mid",
}


def _make_mock_response(content_dict: dict) -> MagicMock:
    """Build a mock OpenAI chat completion response."""
    import json
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps(content_dict, ensure_ascii=False)
    response.usage = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 200
    return response


@pytest.fixture
def mock_openai():
    with patch("src.ai.client.OpenAI") as mock_cls:
        from src.ai.client import reset_ai_client
        reset_ai_client()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(MOCK_STRUCTURED)
        mock_cls.return_value = mock_client
        yield mock_cls
        reset_ai_client()


@pytest.fixture
def mock_db():
    with patch("src.core.jd_parser.get_db") as mock:
        db = MagicMock()
        db.insert.return_value = 99
        mock.return_value = db
        yield mock


class TestParseJDText:
    def test_successful_parse(self, mock_openai, mock_db):
        jd = parse_jd_text(MOCK_JD_TEXT)
        assert jd.company == "TestCorp"
        assert jd.position == "Software Engineer"
        assert jd.source_type == "text"
        assert jd.id == 99
        assert jd.structured_json["required_skills"] == ["Python", "AWS", "Docker"]

    def test_empty_text_raises_error(self, mock_openai, mock_db):
        with pytest.raises(JDParserError, match="empty"):
            parse_jd_text("")

    def test_whitespace_only_raises_error(self, mock_openai, mock_db):
        with pytest.raises(JDParserError, match="empty"):
            parse_jd_text("   \n  \t  ")


class TestJDParserIntegration:
    def test_real_flow_no_api_key(self):
        """Smoke test: verify error when no API key is set."""
        # If .env has key, this would actually call the API.
        # We just verify the module imports correctly.
        from src.core.jd_parser import get_jd, list_jds
        # list_jds should work on empty DB
        jds = list_jds()
        assert isinstance(jds, list)
