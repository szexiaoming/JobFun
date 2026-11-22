"""
Match results display: scores, skills, risks, and suggestions.
"""

import streamlit as st

from config import get_provider_display_name
from src.core.match_engine import MatchEngineError, run_match


SCORE_DISCLAIMER = "匹配分数仅用于辅助判断，不代表获得面试或录用的概率。"


def render_match_results() -> None:
    """Run match analysis and display results."""
    resume = st.session_state.get("resume")
    jd = st.session_state.get("jd")
    jd_json = st.session_state.get("jd_json")
    resume_json = st.session_state.get("resume_json")

    if not all([resume, jd_json, resume_json]):
        st.error("缺少简历或 JD 数据，请返回上一步")
        return

    # Run match (only once)
    if "match_data" not in st.session_state:
        with st.spinner(f"🤖 {get_provider_display_name()} 正在深度分析匹配度..."):
            try:
                match_data = run_match(
                    resume,
                    jd_json,
                    resume_json,
                    jd_id=getattr(jd, "id", 0) or 0,
                )
                st.session_state["match_data"] = match_data
            except MatchEngineError as e:
                st.error(f"❌ 匹配分析失败：{e}")
                if st.button("🔄 重试"):
                    st.session_state.pop("run_match", None)
                    st.rerun()
                return

    match_data = st.session_state["match_data"]
    match = match_data["match_result"]
    suggestions = match_data["suggestions"]

    # ── RAG Context (Phase 2) ──
    rag = match_data.get("rag_context", {})
    if rag.get("has_context"):
        sim_jds = rag.get("similar_jds", [])
        sim_sug = rag.get("similar_suggestions", [])
        with st.expander(f"🧠 历史参考：{len(sim_jds)} 个相似 JD，{len(sim_sug)} 条历史建议", expanded=False):
            if sim_jds:
                st.caption("**相似的历史 JD**")
                for jd in sim_jds:
                    st.markdown(
                        f"- **{jd.get('company', '?')}** — {jd.get('position', '?')} "
                        f"(相似度 {jd.get('similarity', 0):.0%})"
                    )
            if sim_sug:
                st.caption("**历史有效建议**")
                for sug in sim_sug:
                    st.markdown(
                        f"- [{sug.get('category', '')}] {sug.get('suggestion_text', '')[:120]}..."
                    )

    # ── Score Cards ──
    st.header("📊 匹配评分")
    _render_score_cards(match)

    # ── Evidence Matrix (Iteration 0.6) ──
    from ui.evidence_matrix import render_evidence_matrix
    render_evidence_matrix(
        match_id=match.id or 0,
        jd_id=match.jd_id or 0,
        jd_json=jd_json,
        resume_json=resume_json,
    )

    # ── Skills ──
    st.divider()
    _render_skills(match_data)

    # ── Risks ──
    if match_data.get("risks"):
        st.divider()
        _render_risks(match_data["risks"])

    # ── Summary ──
    if match_data.get("summary"):
        st.divider()
        st.markdown(f"**📝 综合评价**：{match_data['summary']}")

    # ── Gap-Filling Dialogue (Phase 3a) ──
    from ui.dialogue import render_gap_filling_section
    render_gap_filling_section()

    # ── Suggestions ──
    st.divider()
    _render_suggestions(suggestions)

    # ── Resume Editor (Phase 3b) ──
    from ui.resume_editor import render_editor_section
    render_editor_section()

    # ── Interview Prep ──
    st.divider()
    from ui.interview_prep import render_interview_button
    render_interview_button()

    # ── Add to Tracker ──
    from ui.tracker import render_add_to_tracker_button
    render_add_to_tracker_button()

    # ── Actions ──
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 重新分析", use_container_width=True, key="btn_rematch_main"):
            _reset_match()
            st.rerun()
    with col2:
        if st.button("📤 重新上传", use_container_width=True, key="btn_reset_upload"):
            _reset_all()
            st.rerun()


def _render_score_cards(match) -> None:
    """Render the six-dimension score cards."""
    st.caption(f"ℹ️ {SCORE_DISCLAIMER}")
    scores = [
        ("总匹配度", match.total_score),
        ("技能匹配", match.skill_score),
        ("经验匹配", match.experience_score),
        ("学历匹配", match.education_score),
        ("软技能", match.soft_skill_score),
        ("文化匹配", match.culture_score),
    ]

    cols = st.columns(6)
    for col, (label, score) in zip(cols, scores):
        with col:
            color = (
                "🟢" if score >= 80 else
                "🟡" if score >= 60 else
                "🟠" if score >= 40 else
                "🔴"
            )
            st.metric(
                label=label,
                value=f"{color} {score:.0f}%",
            )
            st.progress(score / 100)


def _render_skills(match_data: dict) -> None:
    """Render matched and missing skills."""
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("✅ 已匹配技能")
        skills = match_data.get("matched_skills", [])
        if skills:
            for s in skills:
                st.markdown(f"- `{s}`")
        else:
            st.caption("（无）")

    with col2:
        st.subheader("❌ 缺失技能")
        skills = match_data.get("missing_skills", [])
        if skills:
            for s in skills:
                st.markdown(f"- `{s}`")
        else:
            st.caption("（无）")


def _render_risks(risks: list) -> None:
    """Render risk points."""
    st.subheader("⚠️ 风险点")
    for r in risks:
        st.warning(r)


def _render_suggestions(suggestions: list) -> None:
    """Render editable suggestion cards with accept/reject."""
    st.header(f"💡 修改建议（共 {len(suggestions)} 条）")
    st.caption("点击 **✅ 采纳** 加入修改队列，或 **编辑文本后采纳**，或 **✕ 拒绝** 跳过")

    if "accepted_suggestions" not in st.session_state:
        st.session_state["accepted_suggestions"] = []

    from ui.components import suggestion_card

    for i, sug in enumerate(sorted(suggestions, key=lambda s: s.priority if hasattr(s, 'priority') else s.get('priority', 1))):
        result = suggestion_card(sug, i)
        if result is not None:
            # Accepted — add to pending list
            if result not in st.session_state["accepted_suggestions"]:
                st.session_state["accepted_suggestions"].append(result)
                st.rerun()
        # None = no decision yet or rejected


def _reset_match() -> None:
    """Clear match data only, keep resume and JD."""
    st.session_state.pop("match_data", None)
    st.session_state.pop("run_match", None)


def _reset_all() -> None:
    """Clear all session state."""
    for key in ["resume", "resume_json", "jd", "jd_json", "match_data", "run_match"]:
        st.session_state.pop(key, None)
