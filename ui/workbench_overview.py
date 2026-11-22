"""Compact read-only overview for the Workbench landing area."""

from __future__ import annotations

import streamlit as st

from src.core.progress_manager import STATUS_LABELS
from src.core.workbench import get_workbench_summary


def render_workbench_overview() -> None:
    summary = get_workbench_summary()
    st.subheader("今日概览")
    columns = st.columns(4)
    columns[0].metric("全部申请", summary.total_applications)
    columns[1].metric("进行中", summary.active_applications)
    columns[2].metric("待办行动", len(summary.pending_actions))
    columns[3].metric("未来 7 天面试", len(summary.upcoming_interviews))

    if not summary.total_applications:
        st.caption("完成岗位分析并加入看板后，这里会显示待办行动和近期面试。")
        return

    if summary.overdue_actions:
        with st.expander(
            f"⚠️ 已逾期行动（{len(summary.overdue_actions)}）",
            expanded=True,
        ):
            for item in summary.overdue_actions:
                st.markdown(
                    f"- **{item.company} — {item.position}**：{item.next_step} "
                    f"（{item.next_step_due}）"
                )

    if summary.upcoming_interviews:
        with st.expander(
            f"🎤 近期面试（{len(summary.upcoming_interviews)}）",
            expanded=True,
        ):
            for item in summary.upcoming_interviews:
                st.markdown(
                    f"- **{item.company} — {item.position}**：{item.interview_at} · "
                    f"{STATUS_LABELS.get(item.status, item.status)}"
                )
