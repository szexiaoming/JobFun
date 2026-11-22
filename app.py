"""
AI JobFun — AI 求职助手
"""

import streamlit as st

from config import ensure_dirs, get_provider_display_name
from ui.agent_chat import render_agent_page
from ui.home import render_action_button, render_jd_preview, render_jd_section, render_resume_section
from ui.match import render_match_results
from ui.navigation import normalize_page, render_primary_navigation
from ui.sidebar import render_sidebar

# ── Page config ─────────────────────────────────────
st.set_page_config(
    page_title="JobFun — AI 求职助手",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Init ────────────────────────────────────────────
ensure_dirs()

st.markdown("""
<style>
    .stApp { max-width: 100%; }
    h1 { font-size: 1.8rem !important; }
    h2 { font-size: 1.3rem !important; margin-top: 1.5rem !important; }
    .stButton button { border-radius: 6px; }
    .stProgress > div > div { border-radius: 4px; }
</style>
""", unsafe_allow_html=True)


def main() -> None:
    render_sidebar()

    # ── Page routing ────────────────────────────────
    if "page" not in st.session_state:
        st.session_state["page"] = "workbench"
    st.session_state["page"] = normalize_page(st.session_state["page"])
    render_primary_navigation()

    st.divider()

    # ── Page content ────────────────────────────────
    page = st.session_state["page"]

    if page == "workbench":
        _render_workbench_page()
    elif page == "jobs":
        from ui.jobs import render_jobs_page
        render_jobs_page()
    elif page == "interview":
        from ui.interview_prep import render_interview_page
        render_interview_page()
    elif page == "profile":
        _render_profile_page()
    elif page == "agent":
        render_agent_page()

    # Footer
    st.divider()
    st.caption(
        f"JobFun · AI 只优化表达，不编造经历 · "
        f"Powered by {get_provider_display_name()}"
    )


def _render_home_page() -> None:
    """Main analysis flow."""
    st.title("🤖 JobFun — AI 求职助手")

    with st.expander("📄 步骤 1：上传简历", expanded=not st.session_state.get("resume")):
        render_resume_section()

    if st.session_state.get("resume"):
        with st.expander("📋 步骤 2：输入 JD", expanded=not st.session_state.get("jd")):
            render_jd_section()
            render_jd_preview()

        render_action_button()

    if st.session_state.get("run_match"):
        render_match_results()


def _render_workbench_page() -> None:
    """Keep analysis and the existing application board under Workbench."""
    from ui.workbench_overview import render_workbench_overview
    render_workbench_overview()

    views = ["开始分析", "申请看板"]
    if st.session_state.get("selected_application_id"):
        views.append("申请详情")
    elif st.session_state.get("workbench_view") == "申请详情":
        st.session_state["workbench_view"] = "申请看板"
    view = st.radio(
        "工作台视图",
        views,
        horizontal=True,
        key="workbench_view",
        label_visibility="collapsed",
    )
    if view == "申请看板":
        from ui.tracker import render_tracker_page
        render_tracker_page()
    elif view == "申请详情":
        from ui.tracker import render_application_focus
        render_application_focus()
    else:
        _render_home_page()


def _render_profile_page() -> None:
    """Keep resume management and the existing editor under Profile."""
    view = st.radio(
        "个人档案视图",
        ["简历管理", "修改当前简历"],
        horizontal=True,
        key="profile_view",
        label_visibility="collapsed",
    )
    if view == "修改当前简历":
        _render_editor_page()
    else:
        _render_resume_list_page()


def _render_editor_page() -> None:
    """Standalone editor page for modifying current resume."""
    st.title("✏️ 修改简历")

    if not st.session_state.get("match_data"):
        st.info("请先在首页完成一次匹配分析")
        return

    from ui.resume_editor import render_editor_section
    render_editor_section()


def _render_resume_list_page() -> None:
    """List all uploaded resumes."""
    st.title("📖 简历管理")

    from src.db.sqlite_client import get_db
    db = get_db()
    rows = db.list("resumes", limit=20)

    if not rows:
        from ui.empty_states import render_empty_state
        render_empty_state(
            "resumes",
            instance_key="profile",
            action_label="前往工作台上传简历",
            target_page="workbench",
            target_state={"workbench_view": "开始分析"},
        )
        return

    for r in rows:
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{r.get('name', '?')}** — v{r.get('base_version', 0)}")
                st.caption(f"创建: {r.get('created_at', '')}")
            with col2:
                if st.button("加载此简历", key=f"load_{r['id']}"):
                    # Load resume into session
                    import json
                    from src.db.models import Resume
                    resume = Resume(
                        id=r["id"],
                        name=r.get("name", ""),
                        latex_path=r.get("latex_path", ""),
                        structured_json=json.loads(r["structured_json"]) if isinstance(r.get("structured_json"), str) else r.get("structured_json", {}),
                    )
                    st.session_state["resume"] = resume
                    st.session_state["resume_json"] = resume.structured_json
                    st.session_state["page"] = "home"
                    st.success(f"已加载 {resume.name}")
                    st.rerun()


if __name__ == "__main__":
    main()
