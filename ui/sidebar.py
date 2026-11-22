"""
Sidebar navigation and status display.
"""

import streamlit as st

from src.db.sqlite_client import get_db


def render_sidebar() -> None:
    """Render the sidebar with navigation and status."""
    with st.sidebar:
        st.markdown("## 🤖 JobFun")
        st.caption("AI 求职助手")

        st.divider()

        # Progress indicators
        has_resume = bool(st.session_state.get("resume"))
        has_jd = bool(st.session_state.get("jd"))
        has_match = bool(st.session_state.get("match_data"))
        has_modifications = bool(
            st.session_state.get("accepted_suggestions") or
            st.session_state.get("pending_additions")
        )

        st.markdown("**流程进度**")

        steps = [
            ("📄 上传简历", has_resume),
            ("📋 输入 JD", has_jd),
            ("📊 匹配分析", has_match),
            ("✏️ 修改简历", has_modifications),
            ("📄 生成 PDF", bool(st.session_state.get("pdf_result"))),
        ]

        for label, done in steps:
            icon = "✅" if done else "○"
            st.markdown(f"{icon} {label}")

        st.divider()

        # Stats
        if has_match:
            match = st.session_state["match_data"]["match_result"]
            score = match.total_score
            color = "🟢" if score >= 80 else "🟡" if score >= 60 else "🟠" if score >= 40 else "🔴"
            st.metric("当前匹配度", f"{color} {score:.0f}%")

        # Quick actions
        st.divider()
        st.caption("**快捷操作**")

        with st.expander("🧪 实验功能", expanded=False):
            st.caption("Agent 暂不属于一级导航。")
            if st.button("🤖 打开 Agent", use_container_width=True, key="sidebar_agent"):
                st.session_state["page"] = "agent"
                st.rerun()

        if has_match:
            if st.button("🔄 清空重新开始", use_container_width=True):
                for k in list(st.session_state.keys()):
                    if not k.startswith("_"):
                        del st.session_state[k]
                st.rerun()

        # Token usage
        try:
            from src.ai.client import get_ai_client
            client = get_ai_client()
            usage = client.token_usage
            if usage["input"] > 0:
                st.caption(f"Token: {usage['input']:,} in / {usage['output']:,} out")
        except Exception:
            pass

        # DB stats
        try:
            db = get_db()
            st.caption(
                f"数据: {db.count('resumes')} 简历 | "
                f"{db.count('job_descriptions')} JD | "
                f"{db.count('match_results')} 匹配"
            )
        except Exception:
            pass
