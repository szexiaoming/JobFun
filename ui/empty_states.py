"""Consistent empty states and non-persistent synthetic previews."""

from __future__ import annotations

import copy
from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class EmptyStateContent:
    icon: str
    title: str
    description: str
    next_step: str
    demo_kind: str = ""


EMPTY_STATES = {
    "resumes": EmptyStateContent(
        "📄",
        "还没有简历",
        "上传、粘贴或导入一份简历后，才能建立个人档案和分析岗位。",
        "前往工作台上传第一份简历。",
        "resume",
    ),
    "jobs": EmptyStateContent(
        "💼",
        "还没有岗位",
        "导入一份职位描述后，可以查看要求、证据和匹配建议。",
        "前往工作台导入第一份 JD。",
        "job",
    ),
    "applications": EmptyStateContent(
        "📌",
        "还没有申请记录",
        "完成岗位分析后，将岗位加入看板即可开始跟踪进展。",
        "先从岗位详情选择一个岗位。",
        "application",
    ),
    "interviews": EmptyStateContent(
        "🎯",
        "还没有面试内容",
        "选择一个已分析岗位后，可以生成针对该 JD 和真实经历的问题。",
        "先完成一次岗位与简历匹配。",
        "interview",
    ),
    "search_results": EmptyStateContent(
        "🔎",
        "没有符合条件的结果",
        "当前搜索词或筛选条件没有匹配到岗位。",
        "尝试清空搜索词或切换筛选条件。",
    ),
}


_DEMO_DATA = {
    "resume": {
        "_meta": {"synthetic": True, "persistent": False},
        "name": "示例简历（不会保存）",
        "headline": "Backend Engineer",
        "skills": ["Python", "FastAPI", "PostgreSQL", "AWS"],
        "experience": "构建并维护日均 200 万请求的 API 服务",
    },
    "job": {
        "_meta": {"synthetic": True, "persistent": False},
        "company": "Northstar Labs（示例）",
        "position": "Backend Engineer",
        "match_score": 78,
        "evidence": {"proven": 3, "partial": 1, "missing": 1, "uncertain": 1},
    },
    "application": {
        "_meta": {"synthetic": True, "persistent": False},
        "company": "Northstar Labs（示例）",
        "position": "Backend Engineer",
        "status": "面试中",
        "next_step": "准备系统设计案例",
        "interview_at": "2026-12-05 10:00",
        "timeline": ["已收藏", "已投递", "收到面试邀请"],
    },
    "interview": {
        "_meta": {"synthetic": True, "persistent": False},
        "category": "系统设计",
        "question": "如何设计一个能够承载突发流量的任务处理服务？",
        "tip": "结合真实项目说明队列、限流、幂等和故障恢复。",
    },
}


def get_empty_state(kind: str) -> EmptyStateContent:
    if kind not in EMPTY_STATES:
        raise KeyError(f"Unknown empty state: {kind}")
    return EMPTY_STATES[kind]


def get_demo_data(kind: str) -> dict:
    """Return an isolated copy so previews cannot mutate the template."""
    if kind not in _DEMO_DATA:
        raise KeyError(f"Unknown demo data: {kind}")
    return copy.deepcopy(_DEMO_DATA[kind])


def render_empty_state(
    kind: str,
    *,
    instance_key: str,
    action_label: str = "",
    target_page: str = "",
    target_state: dict | None = None,
    show_demo: bool = True,
) -> None:
    """Render one guided empty state and an optional session-only preview."""
    content = get_empty_state(kind)
    toggle_key = f"empty_demo_{kind}_{instance_key}"

    with st.container(border=True):
        st.subheader(f"{content.icon} {content.title}")
        st.write(content.description)
        st.caption(f"下一步：{content.next_step}")

        action_col, demo_col = st.columns(2)
        if action_label and target_page:
            if action_col.button(
                action_label,
                key=f"empty_action_{kind}_{instance_key}",
                type="primary",
                use_container_width=True,
            ):
                st.session_state["page"] = target_page
                for key, value in (target_state or {}).items():
                    st.session_state[key] = value
                st.rerun()

        if show_demo and content.demo_kind:
            label = (
                "收起示例"
                if st.session_state.get(toggle_key)
                else "查看安全示例"
            )
            if demo_col.button(
                label,
                key=f"empty_toggle_{kind}_{instance_key}",
                use_container_width=True,
            ):
                st.session_state[toggle_key] = not st.session_state.get(toggle_key, False)
                st.rerun()

    if show_demo and content.demo_kind and st.session_state.get(toggle_key):
        _render_demo_preview(content.demo_kind)


def _render_demo_preview(kind: str) -> None:
    demo = get_demo_data(kind)
    with st.container(border=True):
        st.info("以下是合成示例，仅用于预览；不会保存、不会参与统计，也不会触发 AI。")
        if kind == "resume":
            st.markdown(f"**{demo['name']}** · {demo['headline']}")
            st.write("技能：" + "、".join(demo["skills"]))
            st.caption(demo["experience"])
        elif kind == "job":
            st.markdown(f"**{demo['company']} — {demo['position']}**")
            st.metric("示例匹配分", f"{demo['match_score']}%")
            st.caption(
                " · ".join(
                    f"{label} {count}"
                    for label, count in demo["evidence"].items()
                )
            )
        elif kind == "application":
            st.markdown(f"**{demo['company']} — {demo['position']}**")
            st.write(f"状态：{demo['status']}")
            st.write(f"下一步：{demo['next_step']} · {demo['interview_at']}")
            st.caption(" → ".join(demo["timeline"]))
        elif kind == "interview":
            st.markdown(f"**{demo['category']}**")
            st.write(demo["question"])
            st.caption(f"提示：{demo['tip']}")
