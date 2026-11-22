"""Three-column Evidence Matcher matrix for the match details page."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import streamlit as st

from src.core.evidence_matcher import (
    EvidenceMatcherError,
    get_evidence_matches,
    get_evidence_reviews,
    get_job_requirements,
    prepare_job_requirements,
    record_evidence_review,
    run_evidence_match,
)
from src.core.evidence_supplements import (
    EvidenceSupplementError,
    confirm_evidence_supplement,
    create_evidence_supplement,
    get_evidence_supplements,
    reject_evidence_supplement,
)


STATUS_PRESENTATION = {
    "proven": ("✅", "已证明", "简历中有直接证据"),
    "partial": ("🟡", "部分匹配", "有相关证据，但尚未完全覆盖要求"),
    "missing": ("🔴", "缺少证据", "当前简历中没有找到支持内容"),
    "uncertain": ("❓", "需要确认", "现有信息不足，需要用户确认"),
    "not_analyzed": ("⚪", "尚未分析", "尚未生成证据判断"),
}

CONTEXT_LABELS = {
    "工作经历": "work",
    "项目经历": "project",
    "教育经历": "education",
    "志愿经历": "volunteering",
    "其他经历": "other",
}


@dataclass
class EvidenceMatrixRow:
    requirement: object
    evidence_match: Optional[object] = None
    reviews: list = field(default_factory=list)
    supplements: list = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.evidence_match.status if self.evidence_match else "not_analyzed"


def build_evidence_matrix_rows(
    requirements: list,
    evidence_matches: list,
    supplements: list,
    reviews_by_evidence_id: Optional[dict[int, list]] = None,
) -> list[EvidenceMatrixRow]:
    """Build a deterministic, presentation-only matrix view model."""
    evidence_by_requirement = {
        item.requirement_id: item for item in evidence_matches
    }
    supplements_by_requirement: dict[int, list] = {}
    for supplement in supplements:
        supplements_by_requirement.setdefault(
            supplement.requirement_id, []
        ).append(supplement)
    review_map = reviews_by_evidence_id or {}

    rows = []
    for requirement in sorted(
        requirements,
        key=lambda item: (item.priority, item.id or 0),
    ):
        evidence_match = evidence_by_requirement.get(requirement.id)
        rows.append(EvidenceMatrixRow(
            requirement=requirement,
            evidence_match=evidence_match,
            reviews=(
                review_map.get(evidence_match.id, [])
                if evidence_match and evidence_match.id
                else []
            ),
            supplements=sorted(
                supplements_by_requirement.get(requirement.id, []),
                key=lambda item: item.id or 0,
            ),
        ))
    return rows


def render_evidence_matrix(
    *,
    match_id: int,
    jd_id: int,
    jd_json: dict,
    resume_json: dict,
    allow_generation: bool = True,
    allow_actions: bool = True,
) -> None:
    """Load and render the evidence matrix without changing score calculation."""
    st.divider()
    st.header("🧭 岗位要求证据矩阵")
    st.caption("逐条查看岗位要求、简历原文证据和需要采取的下一步操作。")

    if not match_id or not jd_id:
        st.warning("当前匹配记录缺少岗位关联，暂时无法生成证据矩阵。")
        return

    requirements = get_job_requirements(jd_id)
    evidence_matches = get_evidence_matches(match_id)
    if not requirements or not evidence_matches:
        st.info("证据矩阵尚未生成。生成过程不会改变现有匹配分数。")
        if allow_generation and st.button(
            "生成证据矩阵",
            key=f"generate_evidence_matrix_{match_id}",
            type="primary",
        ):
            with st.spinner("正在逐条核对岗位要求与简历证据..."):
                try:
                    active_requirements = requirements or prepare_job_requirements(
                        jd_id,
                        jd_json,
                    )
                    run_evidence_match(
                        match_id,
                        jd_id,
                        resume_json,
                        requirements=active_requirements,
                    )
                    st.success("证据矩阵已生成")
                    st.rerun()
                except EvidenceMatcherError as exc:
                    st.error(f"证据矩阵生成失败：{exc}")
        return

    supplements = get_evidence_supplements(match_id)
    reviews_by_evidence_id = {
        item.id: get_evidence_reviews(item.id)
        for item in evidence_matches
        if item.id
    }
    rows = build_evidence_matrix_rows(
        requirements,
        evidence_matches,
        supplements,
        reviews_by_evidence_id,
    )

    counts = {
        status: sum(row.status == status for row in rows)
        for status in ("proven", "partial", "missing", "uncertain")
    }
    summary_cols = st.columns(4)
    for column, status in zip(
        summary_cols,
        ("proven", "partial", "missing", "uncertain"),
    ):
        emoji, label, _ = STATUS_PRESENTATION[status]
        column.metric(f"{emoji} {label}", counts[status])

    header_cols = st.columns([1.25, 1.7, 1.05])
    header_cols[0].markdown("**岗位要求**")
    header_cols[1].markdown("**简历证据与用户补充**")
    header_cols[2].markdown("**判断与下一步**")

    for row in rows:
        _render_matrix_row(row, match_id, allow_actions)


def _render_matrix_row(
    row: EvidenceMatrixRow,
    match_id: int,
    allow_actions: bool,
) -> None:
    requirement = row.requirement
    evidence_match = row.evidence_match
    emoji, label, explanation = STATUS_PRESENTATION.get(
        row.status,
        ("⚪", "未知状态", "该记录包含无法识别的状态"),
    )

    with st.container(border=True):
        requirement_col, evidence_col, action_col = st.columns([1.25, 1.7, 1.05])
        with requirement_col:
            st.markdown(f"**{requirement.text}**")
            st.caption(
                f"{_category_label(requirement.category)} · "
                f"优先级 P{requirement.priority}"
            )

        with evidence_col:
            evidence = evidence_match.evidence_json if evidence_match else []
            if evidence:
                for source in evidence:
                    st.markdown(f"> {source.get('text', '')}")
                    st.caption(_source_caption(source))
            else:
                st.caption("当前简历中没有可展示的来源证据。")

            for supplement in row.supplements:
                status_label = {
                    "draft": "待确认",
                    "confirmed": "已确认",
                    "rejected": "已撤回",
                }.get(supplement.status, supplement.status)
                st.markdown(f"**👤 用户补充 · {status_label}**：{supplement.title}")
                st.caption(supplement.description)

        with action_col:
            st.markdown(f"### {emoji} {label}")
            st.caption(explanation)
            if evidence_match:
                st.caption(f"置信度：{evidence_match.confidence:.0%}（不是录用概率）")
                if evidence_match.recommended_action:
                    st.markdown(f"**建议**：{evidence_match.recommended_action}")
                if evidence_match.user_status:
                    st.info(
                        f"用户记录：{_review_action_label(evidence_match.user_status)}"
                        + (f" · {evidence_match.user_note}" if evidence_match.user_note else "")
                    )
                if allow_actions:
                    _render_review_actions(evidence_match)

            if row.reviews:
                with st.expander(f"查看确认历史（{len(row.reviews)}）"):
                    for review in row.reviews:
                        st.caption(
                            f"{review.created_at} · {_review_action_label(review.action)}"
                            + (f" · {review.note}" if review.note else "")
                        )

            if allow_actions and row.status in {
                "partial", "missing", "uncertain", "not_analyzed"
            }:
                _render_supplement_actions(row, match_id)


def _render_review_actions(evidence_match) -> None:
    confirm_col, reject_col = st.columns(2)
    if confirm_col.button(
        "确认判断",
        key=f"confirm_evidence_{evidence_match.id}",
        use_container_width=True,
    ):
        try:
            record_evidence_review(evidence_match.id, "confirmed")
            st.rerun()
        except EvidenceMatcherError as exc:
            st.error(str(exc))
    if reject_col.button(
        "标记有误",
        key=f"reject_evidence_{evidence_match.id}",
        use_container_width=True,
    ):
        try:
            record_evidence_review(evidence_match.id, "rejected")
            st.rerun()
        except EvidenceMatcherError as exc:
            st.error(str(exc))


def _render_supplement_actions(row: EvidenceMatrixRow, match_id: int) -> None:
    for supplement in row.supplements:
        if supplement.status != "draft":
            continue
        confirm_col, withdraw_col = st.columns(2)
        if confirm_col.button(
            "确认事实",
            key=f"confirm_supplement_{supplement.id}",
            use_container_width=True,
        ):
            try:
                confirm_evidence_supplement(
                    supplement.id,
                    user_attested=True,
                    note="用户在证据矩阵中确认",
                )
                st.rerun()
            except EvidenceSupplementError as exc:
                st.error(str(exc))
        if withdraw_col.button(
            "撤回",
            key=f"reject_supplement_{supplement.id}",
            use_container_width=True,
        ):
            try:
                reject_evidence_supplement(
                    supplement.id,
                    note="用户在证据矩阵中撤回",
                )
                st.rerun()
            except EvidenceSupplementError as exc:
                st.error(str(exc))

    with st.expander("➕ 补充真实经历"):
        with st.form(f"supplement_form_{row.requirement.id}"):
            title = st.text_input("经历标题")
            description = st.text_area(
                "事实描述",
                placeholder="请写清楚你做了什么、使用了什么方法，以及产生了什么结果。",
            )
            context_label = st.selectbox("经历类型", list(CONTEXT_LABELS))
            organization = st.text_input("组织或项目名称（选填）")
            date_cols = st.columns(2)
            start_date = date_cols[0].text_input("开始时间（YYYY或YYYY-MM）")
            end_date = date_cols[1].text_input("结束时间（YYYY或YYYY-MM）")
            submitted = st.form_submit_button("保存为待确认经历")
            if submitted:
                try:
                    create_evidence_supplement(
                        match_id=match_id,
                        requirement_id=row.requirement.id,
                        evidence_match_id=(
                            row.evidence_match.id if row.evidence_match else None
                        ),
                        title=title,
                        description=description,
                        context_type=CONTEXT_LABELS[context_label],
                        organization=organization,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    st.success("补充经历已保存，确认事实后才能参与后续匹配。")
                    st.rerun()
                except EvidenceSupplementError as exc:
                    st.error(str(exc))


def _source_caption(source: dict) -> str:
    index = source.get("bullet_index")
    location = f"第 {index + 1} 条要点" if isinstance(index, int) else "条目标题"
    return (
        f"来源：{source.get('section', '未知章节')} › "
        f"{source.get('entry', '未知条目')} › {location}"
    )


def _category_label(category: str) -> str:
    return {
        "responsibility": "岗位职责",
        "required": "必备要求",
        "preferred": "加分项",
        "education": "学历要求",
        "experience": "经验要求",
    }.get(category, category)


def _review_action_label(action: str) -> str:
    return {
        "confirmed": "已确认",
        "rejected": "已标记有误",
        "corrected": "已纠正",
    }.get(action, action)
