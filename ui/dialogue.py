"""
Dialogue UI: interactive gap-filling interface.
Lets users describe real experience to address missing JD skills.
"""

import streamlit as st

from src.core.dialogue_engine import (
    DialogueError,
    RewriteResult,
    evaluate_experience,
    format_bullets_for_display,
    jd_requirements_summary,
    resume_context_summary,
)
from src.utils.logger import logger


def render_gap_filling_section() -> None:
    """Render the interactive gap-filling dialogue section."""

    match_data = st.session_state.get("match_data")
    resume_json = st.session_state.get("resume_json", {})
    jd_json = st.session_state.get("jd_json", {})

    if not match_data:
        return

    missing_skills = match_data.get("missing_skills", [])
    if not missing_skills:
        return

    st.divider()
    st.header("💬 补充经历对话")

    st.markdown(
        "如果你在以下缺失技能中有实际经验，可以在这里描述，"
        "AI 会帮你评估并改写成适合写进简历的表达。"
    )

    # Initialize session state for dialogue
    if "dialogue_results" not in st.session_state:
        st.session_state["dialogue_results"] = []  # list of RewriteResult

    # Show each missing skill with a "fill" expander
    for skill in missing_skills:
        with st.expander(f"➕ 针对 **{skill}** — 我有相关经验", expanded=False):
            _render_skill_dialogue(
                skill, resume_json, jd_json
            )

    # Show already-submitted rewrites
    if st.session_state["dialogue_results"]:
        st.divider()
        st.subheader("📝 已生成的新增内容")
        for i, result in enumerate(st.session_state["dialogue_results"]):
            _render_rewrite_card(result, i)


def _render_skill_dialogue(skill: str, resume_json: dict, jd_json: dict) -> None:
    """Render the dialogue input for a single missing skill."""
    user_input = st.text_area(
        f"描述你在 **{skill}** 方面的实际经历",
        placeholder=(
            f"例如：我在 XX 项目中用到了 {skill}，具体是...\n"
            "尽量写清楚：做了什么、用了什么技术、取得了什么结果"
        ),
        key=f"dialogue_input_{skill}",
        height=100,
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        submit = st.button(
            "🤖 评估并改写", key=f"dialogue_submit_{skill}",
            use_container_width=True,
        )
    with col2:
        if user_input:
            st.caption(f"已输入 {len(user_input)} 字")

    if submit and user_input.strip():
        with st.spinner("AI 正在评估并改写..."):
            try:
                resume_ctx = resume_context_summary(resume_json)
                jd_ctx = jd_requirements_summary(jd_json)
                result = evaluate_experience(
                    missing_skill=skill,
                    user_description=user_input.strip(),
                    resume_context=resume_ctx,
                    jd_context=jd_ctx,
                )
                # Add to session
                st.session_state["dialogue_results"].append(result)
                st.success(f"✅ 评估完成！可信度：{_cred_label(result.credibility)}")
                st.rerun()

            except DialogueError as e:
                st.error(f"❌ {e}")


def _render_rewrite_card(result: RewriteResult, index: int) -> None:
    """Render a single rewrite result card."""
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown(f"**目标技能**：`{result.missing_skill}`")
            # Gap analysis
            if result.fills_gap:
                st.success(f"✅ 可填补 JD 缺口 — {result.gap_analysis}")
            else:
                st.warning(f"⚠️ 部分覆盖 — {result.gap_analysis}")

        with col2:
            cred = result.credibility
            if cred == "strong":
                st.success(f"可信度：{_cred_label(cred)}")
            elif cred == "plausible":
                st.info(f"可信度：{_cred_label(cred)}")
            elif cred == "needs_clarification":
                st.warning(f"可信度：{_cred_label(cred)}")
            else:
                st.error(f"可信度：{_cred_label(cred)}")

        # Credibility notes
        if result.credibility_notes:
            st.caption(f"💭 {result.credibility_notes}")

        # Follow-up questions if needed
        if result.follow_up_questions:
            st.warning("**需要补充信息**：")
            for q in result.follow_up_questions:
                st.markdown(f"- _{q}_")

        # Rewritten bullets — editable
        if result.rewritten_bullets:
            st.markdown("**改写后的简历要点**（可直接编辑修改）：")
            edit_key = f"dialogue_bullets_{index}"
            if edit_key not in st.session_state:
                st.session_state[edit_key] = "\n".join(result.rewritten_bullets)

            edited_text = st.text_area(
                "简历要点",
                value=st.session_state[edit_key],
                key=f"ta_dialogue_{index}",
                label_visibility="collapsed",
                height=120,
                help="每行一条要点，可自由编辑修改",
            )
            st.session_state[edit_key] = edited_text

            # Suggested section
            st.caption(
                f"📁 建议放入：**{result.suggested_section}** | "
                f"💡 {result.integration_advice}"
            )

        # User description (collapsed)
        with st.expander("查看原始描述"):
            st.text(result.user_description)

        # Action: approve with edited text
        if f"approved_{index}" not in st.session_state:
            st.session_state[f"approved_{index}"] = False

        if st.session_state[f"approved_{index}"]:
            st.success("✅ 已加入修改队列")
        else:
            c1, c2 = st.columns([1, 3])
            with c1:
                if st.button("✅ 加入修改", key=f"approve_{index}"):
                    # Use edited text
                    edit_key = f"dialogue_bullets_{index}"
                    edited_bullets = [
                        b.strip() for b in st.session_state.get(edit_key, "").split("\n")
                        if b.strip()
                    ]
                    result.rewritten_bullets = edited_bullets
                    st.session_state[f"approved_{index}"] = True
                    _queue_for_modification(result)
                    st.rerun()
            with c2:
                if st.button("🗑️ 移除", key=f"remove_{index}"):
                    st.session_state["dialogue_results"].pop(index)
                    st.rerun()


def _queue_for_modification(result: RewriteResult) -> None:
    """Add approved rewritten bullets to the pending modifications queue."""
    if "pending_additions" not in st.session_state:
        st.session_state["pending_additions"] = []

    st.session_state["pending_additions"].append({
        "missing_skill": result.missing_skill,
        "bullets": result.rewritten_bullets,
        "suggested_section": result.suggested_section,
        "integration_advice": result.integration_advice,
    })
    # Flag to show success toast
    st.session_state["just_added"] = True
    logger.info("Queued addition: skill=%s, bullets=%d",
                result.missing_skill, len(result.rewritten_bullets))


def get_pending_additions() -> list[dict]:
    """Get pending additions for the LaTeX modifier."""
    return st.session_state.get("pending_additions", [])


def _cred_label(credibility: str) -> str:
    labels = {
        "strong": "强 — 具体可验证",
        "plausible": "合理 — 可进一步细化",
        "weak": "弱 — 难以说服招聘方",
        "needs_clarification": "需要补充信息",
    }
    return labels.get(credibility, credibility)
