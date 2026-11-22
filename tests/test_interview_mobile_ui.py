"""Static acceptance checks for the narrow-screen interview layout."""

from ui.interview_prep import INTERVIEW_MOBILE_CSS, _display_bullet_number


def test_mobile_css_stacks_columns_and_adds_touch_targets():
    assert "@media (max-width: 768px)" in INTERVIEW_MOBILE_CSS
    assert 'data-testid="stHorizontalBlock"' in INTERVIEW_MOBILE_CSS
    assert "flex-direction: column" in INTERVIEW_MOBILE_CSS
    assert "min-height: 44px" in INTERVIEW_MOBILE_CSS
    assert "width: 100% !important" in INTERVIEW_MOBILE_CSS


def test_mobile_css_protects_long_text_and_input_readability():
    assert "overflow-wrap: anywhere" in INTERVIEW_MOBILE_CSS
    assert "word-break: break-word" in INTERVIEW_MOBILE_CSS
    assert "font-size: 16px" in INTERVIEW_MOBILE_CSS
    assert "min-height: 150px" in INTERVIEW_MOBILE_CSS


def test_legacy_or_invalid_bullet_locations_render_safely():
    assert _display_bullet_number(0) == "1"
    assert _display_bullet_number(2) == "3"
    assert _display_bullet_number(None) == "—"
    assert _display_bullet_number(-1) == "—"
    assert _display_bullet_number(True) == "—"
