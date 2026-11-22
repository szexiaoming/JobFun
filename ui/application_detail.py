"""Read-only application-bound job, resume, and match details."""

from __future__ import annotations

import streamlit as st

from src.core.application_context import (
    ApplicationContextError,
    build_resume_outline,
    get_application_context,
)


def render_application_bound_context(application_id: int) -> None:
    """Show exactly the historical records referenced by the application."""
    st.subheader("绑定资料")
    st.caption("以下资料来自该申请保存的历史关联，不会自动切换到当前简历。")
    try:
        context = get_application_context(application_id)
    except ApplicationContextError as exc:
        st.error(str(exc))
        return

    for issue in context.issues:
        st.warning(issue)

    if context.job and st.button(
        "查看绑定岗位",
        key=f"open_bound_job_{application_id}",
    ):
        st.session_state["selected_job_id"] = context.job.id
        st.session_state["page"] = "jobs"
        st.rerun()

    job_col, resume_col, match_col = st.columns(3)
    with job_col:
        st.markdown("**岗位**")
        if context.job:
            st.write(
                f"{context.job.company or '未填写公司'} — "
                f"{context.job.position or '未填写岗位'}"
            )
            st.caption(f"JD #{context.job.id} · {context.job.created_at or '时间未知'}")
        else:
            st.caption("岗位记录不可读取")
    with resume_col:
        st.markdown("**绑定简历版本**")
        if context.resume:
            st.write(f"{context.resume.name or '未命名简历'} · v{context.resume.base_version}")
            st.caption(
                f"简历 #{context.resume.id} · {context.resume.created_at or '时间未知'}"
            )
        else:
            st.caption("简历版本不可读取，未使用其他版本替代")
    with match_col:
        st.markdown("**绑定匹配报告**")
        if context.match:
            st.metric("匹配分", f"{context.match.total_score:.0f}%")
            st.caption(f"报告 #{context.match.id} · {context.match.created_at or '时间未知'}")
        elif context.application.match_id:
            st.caption("匹配报告不可读取或关联不一致")
        else:
            st.caption("该申请未绑定匹配报告")

    if context.resume:
        with st.expander("查看该版本简历内容", expanded=False):
            outline = build_resume_outline(context.resume.structured_json)
            if not outline:
                st.info("该简历版本没有可显示的结构化内容。")
            for section in outline:
                st.markdown(f"### {section['title'] or '未命名章节'}")
                for entry in section["entries"]:
                    if entry["header"]:
                        st.markdown(f"**{entry['header']}**")
                    for bullet in entry["bullets"]:
                        st.markdown(f"- {bullet}")
