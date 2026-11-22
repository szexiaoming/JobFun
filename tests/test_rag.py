"""
Tests for Phase 2 RAG: ChromaDB client, retriever, and integration.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.db.chroma_client import ChromaClient, _jd_to_text


# ── Helpers ──────────────────────────────────────────


class TestChromaClient:
    """Tests that don't require actual ChromaDB."""

    def test_jd_to_text(self):
        jd = {
            "company": "TestCorp",
            "position": "SDE",
            "required_skills": ["Python", "AWS"],
            "preferred_skills": ["K8s"],
            "responsibilities": ["Build stuff"],
        }
        text = _jd_to_text(jd)
        assert "TestCorp" in text
        assert "SDE" in text
        assert "Python" in text
        assert "AWS" in text
        assert "K8s" in text
        assert "Build stuff" in text

    def test_jd_to_text_empty(self):
        text = _jd_to_text({})
        assert text == ""

    def test_jd_to_text_missing_fields(self):
        jd = {"company": "OnlyCo"}
        text = _jd_to_text(jd)
        assert text == "OnlyCo"


class TestRetriever:
    """Tests with mocked ChromaDB."""

    def test_retrieve_context_empty_db(self):
        """When ChromaDB is empty, should return empty context gracefully."""
        with patch("src.core.retriever.get_chroma") as mock_chroma:
            chroma = MagicMock()
            chroma.count_jds.return_value = 0
            chroma.count_suggestions.return_value = 0
            mock_chroma.return_value = chroma

            from src.core.retriever import retrieve_context
            result = retrieve_context({"company": "Test"})
            assert result["has_context"] is False
            assert result["similar_jds"] == []

    def test_retrieve_context_with_data(self):
        """When ChromaDB has JDs, should return similar ones."""
        with patch("src.core.retriever.get_chroma") as mock_chroma:
            chroma = MagicMock()
            chroma.count_jds.return_value = 3
            chroma.count_suggestions.return_value = 2
            chroma.search_similar_jds.return_value = [
                {"jd_id": 1, "company": "ACorp", "position": "SDE", "similarity": 0.85},
                {"jd_id": 2, "company": "BCorp", "position": "Engineer", "similarity": 0.72},
            ]
            chroma.search_similar_suggestions.return_value = [
                {"suggestion_text": "Use Kafka keyword", "category": "keyword", "similarity": 0.90},
            ]
            mock_chroma.return_value = chroma

            from src.core.retriever import retrieve_context, format_context_for_prompt
            result = retrieve_context({"company": "Test", "required_skills": ["Python"]})
            assert result["has_context"] is True
            assert len(result["similar_jds"]) == 2
            assert len(result["similar_suggestions"]) == 1

            # Format for prompt
            prompt_text = format_context_for_prompt(result)
            assert "ACorp" in prompt_text
            assert "BCorp" in prompt_text
            assert "Kafka" in prompt_text

    def test_index_jd_non_fatal(self):
        """index_jd should not raise even if ChromaDB fails."""
        with patch("src.core.retriever.get_chroma") as mock_chroma:
            chroma = MagicMock()
            chroma.add_jd.side_effect = Exception("DB down")
            mock_chroma.return_value = chroma

            from src.core.retriever import index_jd
            result = index_jd(1, {"company": "Test"})
            assert result == ""  # Non-fatal, returns empty string


class TestFormatContext:
    def test_empty_context_returns_empty_string(self):
        from src.core.retriever import format_context_for_prompt
        assert format_context_for_prompt({"has_context": False}) == ""

    def test_no_context_key(self):
        from src.core.retriever import format_context_for_prompt
        assert format_context_for_prompt({}) == ""
