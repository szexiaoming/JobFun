"""Read-only job catalog and job detail views."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import streamlit as st

from src.core.progress_manager import STATUS_LABELS
from src.db.sqlite_client import Database, get_db
from ui.empty_states import render_empty_state
from ui.match import SCORE_DISCLAIMER


@dataclass
class JobCatalogItem:
    id: int
    company: str
    position: str
    raw_text: str
    structured_json: dict
    source_type: str
    created_at: str
    latest_match: dict | None = None
    match_count: int = 0
    application_statuses: list[str] = field(default_factory=list)
    applications: list[dict] = field(default_factory=list)

    @property
    def application_count(self) -> int:
        return len(self.application_statuses)


def build_job_catalog(
    job_rows: list[dict],
    match_rows: list[dict],
    application_rows: list[dict],
) -> list[JobCatalogItem]:
    """Join job records to their latest match and application summaries."""
    latest_match_by_jd: dict[int, dict] = {}
    match_count_by_jd: dict[int, int] = {}
    for match in match_rows:
        jd_id = match.get("jd_id")
        if jd_id:
            match_count_by_jd[jd_id] = match_count_by_jd.get(jd_id, 0) + 1
        current = latest_match_by_jd.get(jd_id)
        if jd_id and (current is None or match.get("id", 0) > current.get("id", 0)):
            latest_match_by_jd[jd_id] = match

    statuses_by_jd: dict[int, list[str]] = {}
    applications_by_jd: dict[int, list[dict]] = {}
    for application in sorted(application_rows, key=lambda row: row.get("id", 0)):
        statuses_by_jd.setdefault(application.get("jd_id"), []).append(
            application.get("status", "saved")
        )
        applications_by_jd.setdefault(application.get("jd_id"), []).append(application)

    items = []
    for row in job_rows:
        structured = _json_object(row.get("structured_json"))
        items.append(JobCatalogItem(
            id=row["id"],
            company=(row.get("company") or structured.get("company") or "未填写公司"),
            position=(row.get("position") or structured.get("position") or "未填写岗位"),
            raw_text=row.get("raw_text", ""),
            structured_json=structured,
            source_type=row.get("source_type", "text"),
            created_at=row.get("created_at", ""),
            latest_match=latest_match_by_jd.get(row["id"]),
            match_count=match_count_by_jd.get(row["id"], 0),
            application_statuses=statuses_by_jd.get(row["id"], []),
            applications=applications_by_jd.get(row["id"], []),
        ))
    return sorted(items, key=lambda item: item.id, reverse=True)


def filter_job_catalog(
    items: list[JobCatalogItem],
    query: str = "",
    scope: str = "全部",
) -> list[JobCatalogItem]:
    """Filter catalog cards without changing stored job records."""
    normalized_query = query.casefold().strip()
    filtered = []
    for item in items:
        if normalized_query and normalized_query not in (
            f"{item.company} {item.position} {item.raw_text}".casefold()
        ):
            continue
        if scope == "有匹配" and item.latest_match is None:
            continue
        if scope == "未匹配" and item.latest_match is not None:
            continue
        if scope == "有申请" and not item.application_statuses:
            continue
        filtered.append(item)
    return filtered


def load_job_catalog(db: Database | None = None) -> list[JobCatalogItem]:
    database = db or get_db()
    return build_job_catalog(
        database.list("job_descriptions", limit=500),
        database.list("match_results", limit=1000),
        database.list("applications", limit=1000),
    )


def render_jobs_page() -> None:
    """Render the job list or the selected job's read-only detail page."""
    selected_id = st.session_state.get("selected_job_id")
    catalog = load_job_catalog()
    if selected_id:
        selected = next((item for item in catalog if item.id == selected_id), None)
        if selected:
            _render_job_detail(selected)
            return
        st.session_state.pop("selected_job_id", None)

    _render_job_list(catalog)


def _render_job_list(catalog: list[JobCatalogItem]) -> None:
    st.title("💼 岗位")
    st.caption("集中查看已导入岗位、最近一次匹配结果和申请关联。")

    if not catalog:
        render_empty_state(
            "jobs",
            instance_key="catalog",
            action_label="前往工作台导入岗位",
            target_page="workbench",
            target_state={"workbench_view": "开始分析"},
        )
        return

    filter_col, scope_col = st.columns([2, 1])
    query = filter_col.text_input(
        "搜索岗位",
        placeholder="搜索公司、岗位名称或 JD 内容",
    )
    scope = scope_col.selectbox("筛选", ["全部", "有匹配", "未匹配", "有申请"])
    visible_items = filter_job_catalog(catalog, query, scope)
    st.caption(f"共 {len(visible_items)} 个岗位")

    if not visible_items:
        render_empty_state(
            "search_results",
            instance_key="job_filters",
            show_demo=False,
        )
        return

    for item in visible_items:
        with st.container(border=True):
            main_col, match_col, application_col, action_col = st.columns(
                [2.5, 1, 1, 0.8]
            )
            with main_col:
                st.markdown(f"**{item.company} — {item.position}**")
                st.caption(
                    f"导入时间：{item.created_at or '未知'} · "
                    f"来源：{_source_label(item.source_type)}"
                )
            with match_col:
                if item.latest_match:
                    st.metric("最近匹配", f"{item.latest_match.get('total_score', 0):.0f}%")
                else:
                    st.caption("尚未匹配")
            with application_col:
                st.metric("申请记录", item.application_count)
            with action_col:
                if st.button(
                    "查看详情",
                    key=f"open_job_{item.id}",
                    use_container_width=True,
                ):
                    st.session_state["selected_job_id"] = item.id
                    st.rerun()


def _render_job_detail(item: JobCatalogItem) -> None:
    if st.button("← 返回岗位列表", key="back_to_job_list"):
        st.session_state.pop("selected_job_id", None)
        st.rerun()

    st.title(f"{item.company} — {item.position}")
    st.caption(
        f"岗位 #{item.id} · 导入时间：{item.created_at or '未知'} · "
        f"来源：{_source_label(item.source_type)}"
    )

    summary_cols = st.columns(3)
    summary_cols[0].metric("匹配记录", item.match_count)
    summary_cols[1].metric("申请记录", item.application_count)
    summary_cols[2].metric(
        "最近匹配",
        f"{item.latest_match.get('total_score', 0):.0f}%" if item.latest_match else "—",
    )

    if item.application_statuses:
        labels = [STATUS_LABELS.get(status, status) for status in item.application_statuses]
        st.info("申请状态：" + "、".join(labels))
        with st.expander(f"查看关联申请（{item.application_count}）", expanded=False):
            for application in item.applications:
                row_col, action_col = st.columns([3, 1])
                with row_col:
                    st.markdown(
                        f"**申请 #{application['id']}** · "
                        f"{STATUS_LABELS.get(application.get('status', 'saved'), application.get('status', 'saved'))}"
                    )
                    if application.get("next_step"):
                        st.caption(
                            f"下一步：{application['next_step']}"
                            + (
                                f" · {application['next_step_due']}"
                                if application.get("next_step_due")
                                else ""
                            )
                        )
                with action_col:
                    if st.button(
                        "打开申请",
                        key=f"open_application_{application['id']}",
                        use_container_width=True,
                    ):
                        st.session_state["selected_application_id"] = application["id"]
                        st.session_state["page"] = "workbench"
                        st.session_state["workbench_view"] = "申请详情"
                        st.rerun()

    with st.expander("查看岗位描述", expanded=not bool(item.latest_match)):
        if item.raw_text:
            st.text(item.raw_text)
        else:
            st.caption("该岗位没有保存原始 JD 文本。")

    if not item.latest_match:
        st.info("该岗位还没有匹配结果。请前往工作台选择简历并开始分析。")
        if st.button("前往工作台分析", type="primary"):
            _go_to_workbench()
        return

    st.divider()
    st.subheader("最近一次匹配")
    st.caption(f"ℹ️ {SCORE_DISCLAIMER}")
    match = item.latest_match
    score_cols = st.columns(6)
    score_fields = (
        ("总匹配", "total_score"),
        ("技能", "skill_score"),
        ("经验", "experience_score"),
        ("学历", "education_score"),
        ("软技能", "soft_skill_score"),
        ("文化", "culture_score"),
    )
    for column, (label, field_name) in zip(score_cols, score_fields):
        column.metric(label, f"{match.get(field_name, 0):.0f}%")

    resume_json = _load_resume_json(match.get("resume_id", 0))
    if resume_json:
        from ui.evidence_matrix import render_evidence_matrix
        render_evidence_matrix(
            match_id=match["id"],
            jd_id=item.id,
            jd_json=item.structured_json,
            resume_json=resume_json,
            allow_generation=False,
            allow_actions=False,
        )
    else:
        st.warning("该匹配所关联的简历版本无法读取，暂时不能显示证据矩阵。")


def _load_resume_json(resume_id: int) -> dict:
    row = get_db().get("resumes", resume_id) if resume_id else None
    return _json_object(row.get("structured_json")) if row else {}


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _source_label(source_type: str) -> str:
    return {"text": "文本", "image": "图片", "pdf": "PDF"}.get(
        source_type,
        source_type or "未知",
    )


def _go_to_workbench() -> None:
    st.session_state["page"] = "workbench"
    st.session_state["workbench_view"] = "开始分析"
    st.rerun()
