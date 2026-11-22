"""
Reusable UI components: suggestion cards with inline edit, preview panel.
"""

import streamlit as st

from src.utils.logger import logger


def suggestion_card(sug, index: int) -> dict | None:
    """
    Render an editable suggestion card with Accept / Edit / Reject.

    Returns:
        None if rejected
        {"original": str, "suggested": str, "edited": bool} if accepted/modified
    """
    category_emoji = {
        "keyword": "🔑", "structure": "📐", "wording": "✨",
        "highlight": "🎯", "de_emphasize": "📉", "quantify": "📏",
    }
    category_label = {
        "keyword": "关键词注入", "structure": "结构调整", "wording": "表达优化",
        "highlight": "亮点突出", "de_emphasize": "内容弱化", "quantify": "量化增强",
    }

    cat = getattr(sug, "category", "") if hasattr(sug, "category") else sug.get("category", "")
    priority = getattr(sug, "priority", 1) if hasattr(sug, "priority") else sug.get("priority", 1)
    original = getattr(sug, "original_text", "") if hasattr(sug, "original_text") else sug.get("original_text", "")
    suggested = getattr(sug, "suggested_text", "") if hasattr(sug, "suggested_text") else sug.get("suggested_text", "")
    rationale = getattr(sug, "rationale", "") if hasattr(sug, "rationale") else sug.get("rationale", "")
    emoji = category_emoji.get(cat, "💡")

    # Track edit state
    edit_key = f"edit_sug_{index}"
    if edit_key not in st.session_state:
        st.session_state[edit_key] = suggested

    with st.container(border=True):
        # Header row
        hcol1, hcol2, hcol3, hcol4 = st.columns([0.05, 0.55, 0.2, 0.2])
        with hcol1:
            st.markdown(f"**P{priority}**")
        with hcol2:
            st.caption(f"{emoji} {category_label.get(cat, cat)}")
        with hcol3:
            accept = st.button("✅ 采纳", key=f"accept_{index}", use_container_width=True)
        with hcol4:
            reject = st.button("✕ 拒绝", key=f"reject_{index}", use_container_width=True)

        # Content
        with st.expander(f"原文: {original[:60]}...", expanded=(priority <= 2)):
            st.caption("**原文**")
            st.markdown(f"_{original}_")

            st.caption("**建议修改为**（可直接编辑）")
            edited = st.text_area(
                "修改建议",
                value=st.session_state[edit_key],
                key=f"ta_edit_{index}",
                label_visibility="collapsed",
                height=80,
            )
            st.session_state[edit_key] = edited

            if rationale:
                st.caption(f"💭 {rationale}")

        if accept:
            return {"original": original, "suggested": st.session_state[edit_key], "edited": st.session_state[edit_key] != suggested}
        if reject:
            return None

    return None  # No decision yet


def render_preview_panel(resume_json: dict, pending_changes: list[dict]) -> None:
    """
    Render a markdown preview of the resume with pending changes applied.
    Shows what the modified sections will look like.
    """
    st.subheader("📄 简历预览")

    # Build preview from structured resume + pending changes
    sections = resume_json.get("sections", [])

    # Track which section gets new bullets
    additions_by_section = {}
    for change in pending_changes:
        sec = change.get("suggested_section", "Experience")
        additions_by_section.setdefault(sec, []).extend(change.get("bullets", []))

    # Also track text replacements
    replacements = {}
    for change in pending_changes:
        orig = change.get("original_text", "")
        sug = change.get("suggested_text", "")
        if orig and sug and orig != sug:
            replacements[orig] = sug

    for section in sections:
        title = section.get("title", "")
        with st.container(border=True):
            st.markdown(f"### {title}")

            for entry in section.get("entries", []):
                header = entry.get("header", "")
                bullets = list(entry.get("bullets", []))

                # Apply replacements
                bullets = [replacements.get(b, b) for b in bullets]

                # Add new bullets if this section has additions
                if title in additions_by_section:
                    bullets.extend(additions_by_section[title])

                if header:
                    st.markdown(f"**{header}**")

                for b in bullets:
                    # Highlight modified bullets
                    is_modified = b in [replacements.get(orig) for orig in replacements]
                    if is_modified:
                        st.markdown(f"- ✨ *{b}*")
                    elif b in additions_by_section.get(title, []):
                        st.markdown(f"- 🆕 {b}")
                    else:
                        st.markdown(f"- {b}")

                st.markdown("")


def status_badge(score: float) -> str:
    """Return a colored badge emoji for a score."""
    if score >= 80:
        return "🟢"
    elif score >= 60:
        return "🟡"
    elif score >= 40:
        return "🟠"
    return "🔴"
