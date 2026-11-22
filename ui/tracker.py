"""
Job application tracker — kanban board + stats.
"""

from datetime import datetime, time

import streamlit as st

from src.core.progress_manager import (
    STATUS_FLOW,
    STATUS_LABELS,
    ProgressError,
    add_note,
    create_application,
    delete_application,
    get_application,
    get_application_timeline,
    get_pipeline_view,
    get_stats,
    list_applications,
    schedule_interview,
    set_next_action,
    update_status,
)
from src.core.jd_parser import list_jds
from src.db.sqlite_client import get_db
from ui.empty_states import render_empty_state


def render_tracker_page() -> None:
    """Main tracker page with kanban view."""
    st.title("📋 求职进度管理")

    tab_board, tab_list, tab_timeline, tab_stats = st.tabs(
        ["📌 看板", "📋 列表", "🕒 行动与时间线", "📊 统计"]
    )

    with tab_board:
        _render_kanban()

    with tab_list:
        _render_list()

    with tab_timeline:
        _render_timeline_manager()

    with tab_stats:
        _render_dashboard()


def _render_kanban() -> None:
    """Kanban board view."""
    pipeline = get_pipeline_view()
    has_items = any(v for v in pipeline.values())

    if not has_items:
        render_empty_state(
            "applications",
            instance_key="board",
            action_label="前往岗位列表",
            target_page="jobs",
        )
        return

    st.caption("进行中的申请")
    _render_status_columns(
        pipeline,
        ["saved", "applied", "oa", "interview", "offer"],
    )

    st.divider()
    st.caption("已结束的申请")
    _render_status_columns(pipeline, ["accepted", "rejected", "withdrawn"])

    # New application button
    st.divider()
    with st.expander("➕ 新增申请", expanded=False):
        _render_new_application_form()


def _render_status_columns(pipeline: dict, status_order: list[str]) -> None:
    """Render one group of status columns."""
    cols = st.columns(len(status_order))

    for col, status in zip(cols, status_order):
        with col:
            items = pipeline.get(status, [])
            label = STATUS_LABELS.get(status, status)
            count = len(items)

            st.markdown(f"**{label}** ({count})")

            for item in items:
                with st.container(border=True):
                    # Get JD info
                    jd = _get_jd_info(item.get("jd_id", 0))
                    match_score = _get_match_score(item.get("match_id", 0))

                    st.caption(jd.get("company", "?") or jd.get("position", "??"))
                    if match_score is not None:
                        color = "green" if match_score >= 80 else "orange" if match_score >= 60 else "red"
                        st.markdown(f"匹配: :{color}[{match_score:.0f}%]")
                    if item.get("next_step"):
                        st.caption(
                            f"下一步：{item['next_step']}"
                            + (f" · {item['next_step_due']}" if item.get("next_step_due") else "")
                        )
                    if item.get("interview_at"):
                        st.caption(f"面试：{item['interview_at']}")

                    # Quick status change
                    allowed = STATUS_FLOW.get(status, [])
                    if allowed:
                        new_status = st.selectbox(
                            "→", allowed,
                            key=f"kanban_{item['id']}",
                            format_func=lambda s: STATUS_LABELS.get(s, s),
                            label_visibility="collapsed",
                        )
                        if st.button("更新", key=f"upd_{item['id']}"):
                            try:
                                update_status(item["id"], new_status)
                                st.rerun()
                            except ProgressError as e:
                                st.error(str(e))

                    # Notes
                    if item.get("notes"):
                        with st.expander("📝"):
                            st.text(item["notes"])

                    if st.button("🗑️", key=f"del_{item['id']}"):
                        delete_application(item["id"])
                        st.rerun()

def _render_list() -> None:
    """List view of all applications."""
    apps = list_applications()

    if not apps:
        render_empty_state(
            "applications",
            instance_key="list",
            show_demo=False,
        )
        return

    for app in apps:
        jd = _get_jd_info(app.jd_id)
        match_score = _get_match_score(app.match_id)

        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col1:
                company = jd.get("company", "?") or "?"
                pos = jd.get("position", "") or ""
                st.markdown(f"**{company}** — {pos}")
                st.caption(f"投递: {app.applied_date or '—'} | {STATUS_LABELS.get(app.status, app.status)}")
                if app.next_step:
                    st.caption(
                        f"下一步：{app.next_step}"
                        + (f" · {app.next_step_due}" if app.next_step_due else "")
                    )
                if app.interview_at:
                    st.caption(f"面试：{app.interview_at}")
            with col2:
                if match_score is not None:
                    st.metric("匹配", f"{match_score:.0f}%")
            with col3:
                allowed = STATUS_FLOW.get(app.status, [])
                if allowed:
                    ns = st.selectbox("→", allowed, key=f"list_{app.id}", label_visibility="collapsed")
                    if st.button("✓", key=f"go_{app.id}"):
                        update_status(app.id, ns)
                        st.rerun()
            with col4:
                if st.button("🗑️", key=f"dell_{app.id}"):
                    delete_application(app.id)
                    st.rerun()


def _render_dashboard() -> None:
    """Statistics dashboard."""
    stats = get_stats()

    if stats["total"] == 0:
        render_empty_state(
            "applications",
            instance_key="stats",
            show_demo=False,
        )
        return

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总申请", stats["total"])
    with col2:
        st.metric("进行中", stats["pipeline"]["active"])
    with col3:
        st.metric("已结束", stats["pipeline"]["terminal"])
    with col4:
        st.metric("平均匹配度", f"{stats['avg_match_score']:.0f}%")

    st.divider()
    st.subheader("申请转化")
    st.caption(
        "统计口径：只计算已经投递过的申请；仅收藏或投递前撤回不进入分母。"
        "响应包括笔试、面试、Offer、接受或拒绝通知。"
    )
    funnel_cols = st.columns(4)
    with funnel_cols[0]:
        st.metric("已投递基数", stats["applied_count"])
    with funnel_cols[1]:
        st.metric(
            "响应率",
            f"{stats['response_rate']:.1f}%",
            help="收到笔试、面试、Offer、接受或拒绝结果的申请 / 已投递申请",
        )
    with funnel_cols[2]:
        st.metric(
            "面试转化率",
            f"{stats['interview_conversion_rate']:.1f}%",
            help="曾进入面试、Offer 或接受阶段的申请 / 已投递申请",
        )
    with funnel_cols[3]:
        st.metric(
            "Offer 转化率",
            f"{stats['offer_conversion_rate']:.1f}%",
            help="曾获得 Offer 或已接受的申请 / 已投递申请",
        )

    if stats["applied_count"]:
        st.caption(
            f"响应 {stats['response_count']} · "
            f"进入面试 {stats['interview_count']} · "
            f"获得 Offer {stats['offer_count']} · "
            f"接受 Offer {stats['accepted_count']}"
        )

    # Status distribution
    st.divider()
    st.subheader("状态分布")
    cols = st.columns(len(stats["by_status"]))
    for col, (status, count) in zip(cols, sorted(stats["by_status"].items())):
        with col:
            st.metric(STATUS_LABELS.get(status, status), count)


def _render_timeline_manager() -> None:
    """Manage next actions and interview times, and show append-only history."""
    apps = list_applications(limit=200)
    if not apps:
        render_empty_state(
            "applications",
            instance_key="timeline",
            show_demo=False,
        )
        return

    options = {}
    for app in apps:
        jd = _get_jd_info(app.jd_id)
        label = (
            f"#{app.id} · {jd.get('company', '?') or '?'} — "
            f"{jd.get('position', '') or '未填写岗位'} · "
            f"{STATUS_LABELS.get(app.status, app.status)}"
        )
        options[label] = app.id

    option_labels = list(options)
    selected_id = st.session_state.get("selected_application_id")
    selected_index = (
        list(options.values()).index(selected_id)
        if selected_id in options.values()
        else 0
    )
    selected_label = st.selectbox(
        "选择申请",
        option_labels,
        index=selected_index,
    )
    st.session_state["selected_application_id"] = options[selected_label]
    app = get_application(options[selected_label])

    summary_cols = st.columns(3)
    summary_cols[0].metric("当前状态", STATUS_LABELS.get(app.status, app.status))
    summary_cols[1].metric("下一步截止", app.next_step_due or "未设置")
    summary_cols[2].metric("面试时间", app.interview_at or "未设置")

    from ui.application_detail import render_application_bound_context
    render_application_bound_context(app.id)

    action_col, interview_col = st.columns(2)
    with action_col:
        with st.form(f"next_action_form_{app.id}"):
            st.subheader("下一步行动")
            next_step = st.text_input(
                "行动内容",
                value=app.next_step,
                placeholder="例如：准备系统设计案例",
            )
            existing_due = _parse_datetime(app.next_step_due)
            has_due = st.checkbox("设置截止时间", value=existing_due is not None)
            due_date = st.date_input(
                "截止日期",
                value=existing_due.date() if existing_due else None,
                disabled=not has_due,
            )
            due_time = st.time_input(
                "截止时间",
                value=existing_due.time() if existing_due else time(18, 0),
                disabled=not has_due,
            )
            action_note = st.text_area("行动备注（选填）")
            if st.form_submit_button("保存下一步", use_container_width=True):
                try:
                    due_at = _combine_datetime(due_date, due_time) if has_due else ""
                    set_next_action(app.id, next_step, due_at, action_note)
                    st.success("下一步行动已保存")
                    st.rerun()
                except ProgressError as exc:
                    st.error(str(exc))

    with interview_col:
        with st.form(f"interview_form_{app.id}"):
            st.subheader("面试安排")
            existing_interview = _parse_datetime(app.interview_at)
            has_interview = st.checkbox(
                "已确定面试时间",
                value=existing_interview is not None,
            )
            interview_date = st.date_input(
                "面试日期",
                value=existing_interview.date() if existing_interview else None,
                disabled=not has_interview,
            )
            interview_time = st.time_input(
                "面试时间",
                value=(
                    existing_interview.time()
                    if existing_interview
                    else time(10, 0)
                ),
                disabled=not has_interview,
            )
            interview_note = st.text_area("面试备注（选填）")
            if st.form_submit_button("保存面试安排", use_container_width=True):
                try:
                    interview_at = (
                        _combine_datetime(interview_date, interview_time)
                        if has_interview
                        else ""
                    )
                    schedule_interview(app.id, interview_at, interview_note)
                    st.success("面试安排已保存")
                    st.rerun()
                except ProgressError as exc:
                    st.error(str(exc))

    with st.form(f"application_note_form_{app.id}"):
        st.subheader("添加记录")
        note = st.text_area(
            "记录内容",
            placeholder="记录沟通、面试反馈或需要跟进的事项",
        )
        if st.form_submit_button("添加到时间线"):
            try:
                add_note(app.id, note)
                st.success("记录已添加")
                st.rerun()
            except ProgressError as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("申请时间线")
    events = get_application_timeline(app.id)
    if not events:
        st.info("该申请还没有事件记录。下一次状态或行动更新会出现在这里。")
        return
    event_icons = {
        "created": "🆕",
        "status_changed": "🔄",
        "note_added": "📝",
        "next_action_updated": "✅",
        "next_action_cleared": "➖",
        "interview_scheduled": "🎤",
        "interview_cleared": "➖",
    }
    for event in reversed(events):
        with st.container(border=True):
            st.markdown(
                f"**{event_icons.get(event.event_type, '•')} {event.title}**"
            )
            st.caption(event.occurred_at)
            if event.details:
                st.write(event.details)
            if event.from_status or event.to_status:
                st.caption(
                    f"{STATUS_LABELS.get(event.from_status, event.from_status or '—')}"
                    f" → {STATUS_LABELS.get(event.to_status, event.to_status or '—')}"
                )


def render_application_focus() -> None:
    """Open a selected application directly from a job detail page."""
    if st.button("← 返回申请看板", key="back_to_application_board"):
        st.session_state.pop("selected_application_id", None)
        st.session_state["workbench_view"] = "申请看板"
        st.rerun()
    st.title("📌 申请详情")
    _render_timeline_manager()


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _combine_datetime(date_value, time_value) -> str:
    if date_value is None:
        raise ProgressError("请选择日期")
    return datetime.combine(date_value, time_value).strftime("%Y-%m-%d %H:%M")


def _render_new_application_form() -> None:
    """Form to create a new application."""
    jds = list_jds(limit=50)
    jd_options = {
        f"#{j.id} · {j.company or '?'} — {j.position or '??'}": j.id
        for j in jds
    }
    db = get_db()
    resumes = db.list("resumes", limit=50)
    resume_options = {
        f"#{r['id']} · {r.get('name', '?')} · v{r.get('base_version', 0)}": r["id"]
        for r in resumes
    }

    if not jd_options:
        st.warning("请先至少解析一条 JD")
        return
    if not resume_options:
        st.warning("请先至少上传一份简历")
        return

    selected_jd_label = st.selectbox("选择 JD", list(jd_options.keys()))
    selected_resume_label = st.selectbox("选择简历版本", list(resume_options.keys()))
    notes = st.text_area("备注", placeholder="记录投递渠道、截止日期等...")

    if st.button("创建申请"):
        jd_id = jd_options[selected_jd_label]
        resume_id = resume_options[selected_resume_label]
        app = create_application(jd_id=jd_id, resume_id=resume_id, notes=notes)
        st.success(f"已创建！状态: {STATUS_LABELS.get(app.status, app.status)}")
        st.rerun()


def _get_jd_info(jd_id: int) -> dict:
    """Get JD company/position from DB."""
    try:
        db = get_db()
        row = db.get("job_descriptions", jd_id)
        if row:
            import json
            sj = row.get("structured_json", "{}")
            if isinstance(sj, str):
                sj = json.loads(sj)
            return {"company": sj.get("company", ""), "position": sj.get("position", "")}
    except Exception:
        pass
    return {}


def _get_match_score(match_id: int) -> float | None:
    """Get match score from DB."""
    try:
        db = get_db()
        row = db.get("match_results", match_id)
        if row:
            return row.get("total_score")
    except Exception:
        pass
    return None


def render_add_to_tracker_button() -> None:
    """Render a button in match results to add current match to tracker."""
    match_data = st.session_state.get("match_data")
    if not match_data:
        return

    match = match_data["match_result"]
    jd = st.session_state.get("jd")

    if not jd:
        return

    if st.button("📌 加入求职看板", use_container_width=True):
        try:
            app = create_application(
                jd_id=jd.id,
                resume_id=st.session_state.get("resume").id if st.session_state.get("resume") else 1,
                match_id=match.id,
            )
            st.success(f"已加入看板！状态: 📌 已收藏")
        except ProgressError as e:
            st.error(str(e))
