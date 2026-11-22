"""Tests for guided empty states and non-persistent demo previews."""

import pytest

from ui.empty_states import EMPTY_STATES, get_demo_data, get_empty_state


def test_core_empty_states_have_clear_next_steps():
    for kind in ("resumes", "jobs", "applications", "interviews"):
        content = get_empty_state(kind)
        assert content.title
        assert content.description
        assert content.next_step
        assert content.demo_kind


def test_unknown_empty_state_is_rejected():
    with pytest.raises(KeyError, match="Unknown empty state"):
        get_empty_state("unknown")


def test_demo_data_is_explicitly_synthetic_and_non_persistent():
    for kind in ("resume", "job", "application", "interview"):
        demo = get_demo_data(kind)
        assert demo["_meta"] == {"synthetic": True, "persistent": False}
        assert "id" not in demo


def test_demo_data_returns_an_isolated_copy():
    first = get_demo_data("job")
    first["company"] = "Changed"
    first["evidence"]["proven"] = 999

    second = get_demo_data("job")

    assert second["company"] == "Northstar Labs（示例）"
    assert second["evidence"]["proven"] == 3


def test_application_demo_explains_a_complete_sample_flow():
    demo = get_demo_data("application")

    assert demo["status"] == "面试中"
    assert demo["next_step"]
    assert demo["interview_at"]
    assert demo["timeline"] == ["已收藏", "已投递", "收到面试邀请"]
