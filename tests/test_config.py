"""Tests for provider-independent AI capability routing."""

import pytest

import config


def test_deepseek_capability_routes(monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "deepseek")
    monkeypatch.setattr(config, "DEEPSEEK_MODEL_FAST", "ds-fast")
    monkeypatch.setattr(config, "DEEPSEEK_MODEL_REASONING", "ds-reasoning")

    assert config.get_active_model("structured") == "ds-fast"
    assert config.get_active_model("agent") == "ds-fast"
    assert config.get_active_model("evaluation") == "ds-fast"
    assert config.get_active_model("reasoning") == "ds-reasoning"
    assert config.get_active_model("fast") == "ds-fast"
    assert config.supports_capability("vision") is False
    assert config.supports_vision() is False


def test_anthropic_routes_all_supported_capabilities(monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "anthropic")
    monkeypatch.setattr(config, "ANTHROPIC_MODEL", "claude-test")

    for capability in config.AI_CAPABILITIES:
        assert config.get_active_model(capability) == "claude-test"

    assert config.supports_vision() is True
    assert config.get_provider_display_name() == "Anthropic Claude"
    assert config.get_ai_runtime_label("vision") == "Anthropic Claude · claude-test"


def test_vision_route_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "deepseek")

    with pytest.raises(ValueError, match="does not support"):
        config.get_active_model("vision")


def test_unknown_provider_and_capability_are_rejected(monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "unknown")
    with pytest.raises(ValueError, match="Unsupported AI provider"):
        config.get_active_model("structured")

    monkeypatch.setattr(config, "AI_PROVIDER", "deepseek")
    with pytest.raises(ValueError, match="Unknown AI capability"):
        config.get_active_model("summarize_everything")


def test_transcription_configuration_is_independent_from_text_provider(monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "deepseek")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "speech-key")
    monkeypatch.setattr(config, "OPENAI_TRANSCRIPTION_MODEL", "speech-model")

    assert config.is_transcription_configured() is True
    assert config.get_transcription_runtime_label() == "OpenAI · speech-model"

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert config.is_transcription_configured() is False
