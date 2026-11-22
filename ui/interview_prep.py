"""
Interview preparation page. Generate and display interview questions.
"""

import streamlit as st

from config import (
    get_provider_display_name,
    get_transcription_runtime_label,
    is_transcription_configured,
)
from src.core.audio_transcription import (
    AudioTranscriptionError,
    remove_interview_audio,
    save_interview_audio,
    transcribe_interview_audio,
)
from src.core.interview_follow_up import (
    MAX_FOLLOW_UPS_PER_ATTEMPT,
    FollowUpQuestion,
    InterviewFollowUpError,
    generate_follow_up,
    get_follow_ups,
)
from src.core.interview_generator import InterviewError, InterviewPrep, generate_questions, get_saved_questions
from src.core.interview_insights import (
    AttemptProgress,
    get_interview_insights,
    get_question_progress,
)
from src.core.interview_practice import (
    RUBRIC_DIMENSIONS,
    InterviewEvaluation,
    InterviewPracticeError,
    evaluate_text_answer,
)
from src.db.sqlite_client import get_db
from ui.empty_states import render_empty_state


CATEGORY_LABELS = {
    "technical": "🔧 技术基础",
    "project_deep_dive": "📂 项目追问",
    "behavioral": "🏢 行为面试",
    "english": "🇬🇧 英文面试",
    "system_design": "🧠 系统设计",
}

DIFFICULTY_COLORS = {
    "easy": "green",
    "medium": "orange",
    "hard": "red",
}

INTERVIEW_MOBILE_CSS = """
<style>
@media (max-width: 768px) {
    [data-testid="stMainBlockContainer"] {
        padding: 0.75rem 0.65rem 3rem;
    }
    [data-testid="stHorizontalBlock"] {
        flex-direction: column;
        gap: 0.5rem;
    }
    [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }
    .stButton > button,
    [data-testid="stFileUploaderDropzone"] button {
        min-height: 44px;
        width: 100%;
    }
    textarea,
    input,
    button {
        font-size: 16px !important;
    }
    textarea {
        min-height: 150px !important;
    }
    [data-testid="stMetric"] {
        padding: 0.65rem 0.75rem;
        border: 1px solid rgba(128, 128, 128, 0.22);
        border-radius: 0.5rem;
    }
    [data-testid="stExpander"] details summary {
        min-height: 44px;
        align-items: center;
    }
    [data-testid="stMarkdownContainer"],
    [data-testid="stCaptionContainer"] {
        overflow-wrap: anywhere;
        word-break: break-word;
    }
    [data-testid="stAudioInput"] {
        width: 100%;
    }
}
</style>
"""


def render_interview_page() -> None:
    """Main interview preparation page."""
    st.markdown(INTERVIEW_MOBILE_CSS, unsafe_allow_html=True)
    st.title("🎯 面试准备")

    match_data = st.session_state.get("match_data")
    jd_json = st.session_state.get("jd_json", {})
    resume_json = st.session_state.get("resume_json", {})

    if not jd_json or not resume_json:
        render_empty_state(
            "interviews",
            instance_key="missing_context",
            action_label="前往工作台开始分析",
            target_page="workbench",
            target_state={"workbench_view": "开始分析"},
        )
        return

    match_id = match_data["match_result"].id if match_data else 0

    # Check for saved questions
    saved = get_saved_questions(match_id) if match_id else {}

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**公司**：{jd_json.get('company', '—')} | **职位**：{jd_json.get('position', '—')}")
    with col2:
        category_filter = st.selectbox(
            "题型筛选",
            ["all", "technical", "project_deep_dive", "behavioral", "english", "system_design"],
            format_func=lambda c: "全部" if c == "all" else CATEGORY_LABELS.get(c, c),
        )
    application_id = _render_application_selector(match_id)
    _render_practice_insights(match_id, application_id)

    # Generate button
    if st.button("🤖 生成面试题", use_container_width=True, type="primary"):
        with st.spinner(
            f"{get_provider_display_name()} 正在分析 JD + 简历，生成针对性面试题..."
        ):
            try:
                prep = generate_questions(
                    jd_json, resume_json, match_id=match_id,
                    category=category_filter, save_to_db=True,
                )
                st.session_state["interview_prep"] = prep
            except InterviewError as e:
                st.error(f"❌ {e}")

    # Display
    prep = st.session_state.get("interview_prep")
    if prep:
        _render_interview_focus(prep)
        _render_questions(prep, category_filter, application_id)
    elif saved:
        st.info("已加载历史面试题")
        _render_saved_questions(saved, category_filter, application_id)
    else:
        render_empty_state(
            "interviews",
            instance_key="questions",
            show_demo=True,
        )


def _render_interview_focus(prep: InterviewPrep) -> None:
    """Show interview focus summary."""
    if prep.interview_focus:
        with st.container(border=True):
            st.markdown(f"**🎯 面试重点**：{prep.interview_focus}")


def _render_questions(
    prep: InterviewPrep,
    filter_cat: str = "all",
    application_id: int = 0,
) -> None:
    """Render categorized questions."""
    categories = prep.categories

    for cat_name, questions in categories.items():
        if filter_cat != "all" and cat_name != filter_cat:
            continue
        if not questions:
            continue

        label = CATEGORY_LABELS.get(cat_name, cat_name)
        with st.expander(f"{label}（{len(questions)} 题）", expanded=(filter_cat != "all")):
            for i, q in enumerate(questions):
                _render_question_card(q, i, application_id)


def _render_saved_questions(
    categorized: dict,
    filter_cat: str = "all",
    application_id: int = 0,
) -> None:
    """Render saved questions from DB."""
    for cat_name, questions in categorized.items():
        if filter_cat != "all" and cat_name != filter_cat:
            continue
        if not questions:
            continue

        label = CATEGORY_LABELS.get(cat_name, cat_name)
        with st.expander(f"{label}（{len(questions)} 题）"):
            for i, q in enumerate(questions):
                _render_question_card(q, i, application_id)


def _render_question_card(question: dict, index: int, application_id: int) -> None:
    """Render one question and its written-answer practice controls."""
    diff = question.get("difficulty", "medium")
    color = DIFFICULTY_COLORS.get(diff, "orange")
    question_id = int(question.get("id", 0) or 0)

    with st.container(border=True):
        st.markdown(
            f"**{index + 1}.** :{color}[{diff.upper()}] "
            f"{question.get('question', '')}"
        )
        if question.get("tip"):
            st.caption(f"💡 _{question.get('tip')}_")
        if not question_id:
            st.caption("保存题目后即可进行文字练习。")
            return

        st.markdown("**✍️ 文字作答与固定 Rubric 评价**")
        _render_rubric_help()
        evaluation_key = f"interview_evaluation_{question_id}_{application_id}"
        _render_answer_input(
            question_id,
            application_id,
            key_prefix=f"interview_{question_id}_{application_id}",
            evaluation_key=evaluation_key,
            text_height=180,
            text_button_label="提交并评价",
        )

        progress = get_question_progress(
            question_id,
            application_id=application_id,
        )
        latest = st.session_state.get(
            evaluation_key
        )
        if latest is None and progress:
            latest = progress[0].evaluation
        if latest:
            _render_evaluation(latest, allow_follow_up=True)
        if progress:
            if st.checkbox(
                f"查看历史尝试（{len(progress)} 次）",
                key=f"show_interview_history_{question_id}_{application_id}",
            ):
                _render_attempt_history(progress)


def _render_answer_input(
    question_id: int,
    application_id: int,
    *,
    key_prefix: str,
    evaluation_key: str,
    text_height: int,
    text_button_label: str,
) -> None:
    """Render text or voice input and save only an explicitly confirmed answer."""
    mode = st.radio(
        "回答方式",
        ["文字", "语音"],
        horizontal=True,
        key=f"{key_prefix}_mode",
        label_visibility="collapsed",
    )
    if mode == "文字":
        answer = st.text_area(
            "你的回答",
            key=f"{key_prefix}_text",
            height=text_height,
            placeholder="输入完整回答。系统会按固定 Rubric 评价。",
        )
        if st.button(
            text_button_label,
            key=f"{key_prefix}_evaluate_text",
            type="primary",
        ):
            try:
                with st.spinner("正在按照固定 Rubric 评价回答..."):
                    evaluation = evaluate_text_answer(
                        question_id,
                        answer,
                        application_id=application_id,
                    )
                st.session_state[evaluation_key] = evaluation
                st.success("回答已保存并完成评价。")
            except InterviewPracticeError as exc:
                st.error(f"无法评价回答：{exc}")
        return

    _render_voice_answer_input(
        question_id,
        application_id,
        key_prefix=key_prefix,
        evaluation_key=evaluation_key,
        text_height=text_height,
    )


def _render_voice_answer_input(
    question_id: int,
    application_id: int,
    *,
    key_prefix: str,
    evaluation_key: str,
    text_height: int,
) -> None:
    st.caption(
        f"转写服务：{get_transcription_runtime_label()}。"
        "音频最多 10 MB；浏览器 WAV 录音最长 5 分钟。"
    )
    if not is_transcription_configured():
        st.warning("尚未配置 OPENAI_API_KEY，配置后才能转写音频。")

    recorded = st.audio_input(
        "录制回答",
        sample_rate=16000,
        key=f"{key_prefix}_recorded",
    )
    uploaded = st.file_uploader(
        "或上传音频",
        type=["flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm"],
        key=f"{key_prefix}_uploaded",
    )
    selected = recorded or uploaded
    if recorded is not None and uploaded is not None:
        st.info("同时提供录音和上传文件时，优先使用刚录制的音频。")
    if uploaded is not None and recorded is None:
        if uploaded.type:
            st.audio(uploaded.getvalue(), format=uploaded.type)
        else:
            st.audio(uploaded.getvalue())

    draft_key = f"{key_prefix}_voice_draft"
    transcript_key = f"{key_prefix}_transcript"
    if selected is not None and st.button(
        "转写音频",
        key=f"{key_prefix}_transcribe",
        disabled=not is_transcription_configured(),
    ):
        audio_bytes = selected.getvalue()
        try:
            with st.spinner("正在转写音频，转写结果不会自动提交评价..."):
                result = transcribe_interview_audio(
                    audio_bytes,
                    selected.name,
                    selected.type or "",
                )
            st.session_state[draft_key] = {
                "audio_bytes": audio_bytes,
                "filename": result.filename,
                "content_type": result.content_type,
                "duration_seconds": result.duration_seconds,
            }
            st.session_state[transcript_key] = result.text
            st.success("转写完成，请检查并修改后再确认。")
        except AudioTranscriptionError as exc:
            st.error(f"无法转写音频：{exc}")

    draft = st.session_state.get(draft_key)
    if not draft:
        st.caption("录音或选择文件后，点击“转写音频”生成可编辑草稿。")
        return

    if draft.get("duration_seconds") is not None:
        st.caption(
            f"当前草稿：{draft['filename']} · "
            f"{draft['duration_seconds']:.1f} 秒"
        )
    else:
        st.caption(f"当前草稿：{draft['filename']}")
    transcript = st.text_area(
        "检查并修改转写内容",
        key=transcript_key,
        height=text_height,
    )
    confirmed = st.checkbox(
        "我已检查转写内容，并确认它准确表达了我的回答",
        key=f"{key_prefix}_confirmed",
    )
    retain_audio = st.checkbox(
        "同时保留原始音频（默认只保存确认后的文字）",
        key=f"{key_prefix}_retain_audio",
    )
    if st.button(
        "确认转写并评价",
        key=f"{key_prefix}_evaluate_voice",
        type="primary",
        disabled=not confirmed,
    ):
        saved_path = None
        try:
            if retain_audio:
                saved_path = save_interview_audio(
                    draft["audio_bytes"],
                    draft["filename"],
                    question_id,
                )
            with st.spinner("正在评价已确认的语音转写..."):
                evaluation = evaluate_text_answer(
                    question_id,
                    transcript,
                    application_id=application_id,
                    audio_path=str(saved_path or ""),
                    transcript=transcript,
                )
            st.session_state[evaluation_key] = evaluation
            st.success(
                "已保存确认后的转写并完成评价。"
                + ("原始音频也已保留。" if saved_path else "原始音频未保存。")
            )
        except (AudioTranscriptionError, InterviewPracticeError) as exc:
            if saved_path is not None:
                try:
                    remove_interview_audio(saved_path)
                except AudioTranscriptionError:
                    pass
            st.error(f"无法评价语音回答：{exc}")


def _render_rubric_help() -> None:
    labels = "、".join(item["label"] for item in RUBRIC_DIMENSIONS.values())
    st.caption(
        f"固定维度：{labels}；每项 0–5 分，3 分代表达到基本要求。"
        "选择关联申请后，真实性会与该申请保存的历史简历版本核验。"
    )


def _render_evaluation(
    evaluation: InterviewEvaluation,
    *,
    allow_follow_up: bool,
) -> None:
    st.markdown(f"#### 最新评价 · 综合 {evaluation.overall_score:.2f}/5")
    columns = st.columns(4)
    for column, (dimension, item) in zip(columns, RUBRIC_DIMENSIONS.items()):
        column.metric(item["label"], f"{evaluation.scores[dimension]}/5")

    feedback = evaluation.feedback
    if feedback.get("summary"):
        st.info(feedback["summary"])
    left, right = st.columns(2)
    with left:
        st.markdown("**做得好的地方**")
        for item in feedback.get("strengths", []):
            st.markdown(f"- {item}")
    with right:
        st.markdown("**下一步改进**")
        for item in feedback.get("improvements", []):
            st.markdown(f"- {item}")
    if feedback.get("next_practice"):
        st.markdown(f"**下次练习：** {feedback['next_practice']}")
    _render_evidence_feedback(evaluation)
    st.caption(f"保存于 {evaluation.created_at}")
    if allow_follow_up:
        _render_follow_up_section(evaluation)


def _render_follow_up_section(evaluation: InterviewEvaluation) -> None:
    """Generate, display, and answer follow-ups for one saved attempt."""
    st.markdown("**针对性追问**")
    follow_ups = get_follow_ups(evaluation.attempt_id)
    if len(follow_ups) < MAX_FOLLOW_UPS_PER_ATTEMPT:
        if st.button(
            "生成一个追问",
            key=f"generate_follow_up_{evaluation.attempt_id}",
        ):
            try:
                with st.spinner("正在根据当前回答、评价和证据生成追问..."):
                    created = generate_follow_up(evaluation.attempt_id)
                follow_ups.append(created)
                st.success("已生成针对性追问。")
            except InterviewFollowUpError as exc:
                st.error(f"无法生成追问：{exc}")
    else:
        st.caption(f"本次回答已达到最多 {MAX_FOLLOW_UPS_PER_ATTEMPT} 个追问。")

    if not follow_ups:
        st.caption("追问不会自动生成；你可以在查看评价后主动创建。")
        return
    for index, follow_up in enumerate(follow_ups, start=1):
        _render_follow_up_answer(follow_up, evaluation.application_id, index)


def _render_follow_up_answer(
    follow_up: FollowUpQuestion,
    application_id: int,
    index: int,
) -> None:
    label = RUBRIC_DIMENSIONS.get(
        follow_up.target_dimension,
        {"label": follow_up.target_dimension},
    )["label"]
    with st.container(border=True):
        st.markdown(f"**追问 {index} · 针对{label}**")
        st.markdown(follow_up.question)
        st.caption(f"追问原因：{follow_up.rationale}")
        evaluation_key = f"follow_up_evaluation_{follow_up.id}_{application_id}"
        _render_answer_input(
            follow_up.question_id,
            application_id,
            key_prefix=f"follow_up_{follow_up.id}_{application_id}",
            evaluation_key=evaluation_key,
            text_height=140,
            text_button_label="提交追问回答并评价",
        )

        progress = get_question_progress(
            follow_up.question_id,
            application_id=application_id,
        )
        latest = st.session_state.get(
            evaluation_key
        )
        if latest is None and progress:
            latest = progress[0].evaluation
        if latest:
            _render_evaluation(latest, allow_follow_up=False)
        if progress and st.checkbox(
            f"查看追问历史（{len(progress)} 次）",
            key=f"show_follow_up_history_{follow_up.id}_{application_id}",
        ):
            _render_attempt_history(progress)


def _render_practice_insights(match_id: int, application_id: int) -> None:
    """Show aggregate progress and deterministic practice recommendations."""
    if not match_id:
        return
    insights = get_interview_insights(
        match_id,
        application_id=application_id,
    )
    with st.expander("📈 练习进度与薄弱项", expanded=bool(insights.attempt_count)):
        if not insights.attempt_count:
            st.caption("完成第一次回答后，这里会显示历史变化和建议复练内容。")
            return

        summary_columns = st.columns(4)
        summary_columns[0].metric("回答次数", insights.attempt_count)
        summary_columns[1].metric("练习题数", insights.practiced_question_count)
        summary_columns[2].metric("主问题回答", insights.main_attempt_count)
        summary_columns[3].metric("追问回答", insights.follow_up_attempt_count)

        st.markdown(f"**综合平均：{insights.overall_average:.2f}/5**")
        dimension_columns = st.columns(4)
        for column, (dimension, item) in zip(
            dimension_columns,
            RUBRIC_DIMENSIONS.items(),
        ):
            delta = None
            if insights.comparison_count:
                delta = f"{insights.dimension_changes[dimension]:+.2f}"
            column.metric(
                item["label"],
                f"{insights.dimension_averages[dimension]:.2f}/5",
                delta=delta,
            )
        if insights.comparison_count:
            st.caption(
                f"变化值来自 {insights.comparison_count} 道重复练习题："
                "比较每道题最新一次与上一次，再按维度取平均。"
            )

        if insights.weak_dimensions:
            labels = "、".join(
                RUBRIC_DIMENSIONS[dimension]["label"]
                for dimension in insights.weak_dimensions
            )
            st.warning(f"当前薄弱维度：{labels}（平均分低于 3.5）")
        else:
            st.success("当前没有平均分低于 3.5 的评价维度。")

        if insights.category_averages:
            category_summary = " · ".join(
                f"{CATEGORY_LABELS.get(category, category)} {score:.2f}/5"
                for category, score in insights.category_averages.items()
            )
            st.markdown(f"**题型平均：** {category_summary}")
        if insights.weak_categories:
            labels = "、".join(
                CATEGORY_LABELS.get(category, category)
                for category in insights.weak_categories
            )
            st.caption(f"建议重点练习题型：{labels}")

        if insights.recommendations:
            st.markdown("**建议复练**")
            for recommendation in insights.recommendations:
                dimension_label = RUBRIC_DIMENSIONS[
                    recommendation.weakest_dimension
                ]["label"]
                with st.container(border=True):
                    st.markdown(recommendation.question)
                    st.caption(
                        f"{CATEGORY_LABELS.get(recommendation.category, recommendation.category)} · "
                        f"最新 {recommendation.latest_score:.2f}/5 · "
                        f"已练 {recommendation.attempt_count} 次 · "
                        f"最低维度：{dimension_label}"
                    )
                    if recommendation.next_practice:
                        st.markdown(f"下一次练习：{recommendation.next_practice}")


def _render_attempt_history(progress: list[AttemptProgress]) -> None:
    """Render same-question attempts and score changes, newest first."""
    st.markdown("**历史尝试**")
    for item in progress:
        evaluation = item.evaluation
        change = "首次尝试"
        if item.overall_delta is not None:
            change = f"相比上次 {item.overall_delta:+.2f}"
        with st.container(border=True):
            answer_type = "语音转写" if evaluation.transcript else "文字回答"
            st.markdown(
                f"**第 {item.attempt_number} 次 · {answer_type} · "
                f"{evaluation.overall_score:.2f}/5**"
            )
            st.caption(f"{change} · {evaluation.created_at}")
            dimension_text = " · ".join(
                _format_history_dimension(item, dimension)
                for dimension in RUBRIC_DIMENSIONS
            )
            st.caption(dimension_text)
            st.markdown("**回答**")
            st.write(evaluation.answer_text)
            summary = evaluation.feedback.get("summary", "")
            if summary:
                st.markdown(f"评价：{summary}")


def _format_history_dimension(item: AttemptProgress, dimension: str) -> str:
    label = RUBRIC_DIMENSIONS[dimension]["label"]
    score = item.evaluation.scores[dimension]
    delta = item.score_deltas[dimension]
    suffix = "" if delta is None else f" ({delta:+d})"
    return f"{label} {score}/5{suffix}"


def _render_application_selector(match_id: int) -> int:
    """Select the application whose immutable resume version grounds feedback."""
    if not match_id:
        return 0
    db = get_db()
    applications = sorted(
        db.find_by("applications", "match_id", match_id),
        key=lambda item: int(item.get("id", 0)),
        reverse=True,
    )
    if not applications:
        st.info("当前匹配尚未保存为申请；仍可练习，但评价不会引用简历证据。")
        return 0

    labels = {}
    for application in applications:
        resume = db.get("resumes", application.get("resume_id", 0))
        resume_label = "简历不可读取"
        if resume:
            version = resume.get("base_version", 0)
            resume_label = f"{resume.get('name') or '未命名简历'} · v{version}"
        labels[application["id"]] = (
            f"申请 #{application['id']} · {application.get('status', 'saved')} · "
            f"{resume_label}"
        )

    preferred = int(st.session_state.get("selected_application_id", 0) or 0)
    options = [application["id"] for application in applications]
    index = options.index(preferred) if preferred in options else 0
    selected = st.selectbox(
        "评价所依据的申请与历史简历",
        options,
        index=index,
        format_func=lambda item: labels[item],
        key=f"interview_application_{match_id}",
    )
    st.caption("证据核验只使用该申请保存的简历版本，不会切换到当前或最新简历。")
    return int(selected)


def _render_evidence_feedback(evaluation: InterviewEvaluation) -> None:
    citations = evaluation.feedback.get("evidence_citations", [])
    unsupported = evaluation.feedback.get("unsupported_claims", [])
    evidence_context = evaluation.feedback.get("evidence_context", {})
    if evaluation.application_id == 0:
        st.caption("本次练习未关联申请，因此没有执行历史简历证据核验。")
        return

    st.markdown("**历史简历证据核验**")
    if evidence_context and not evidence_context.get("source_count"):
        st.warning("绑定的历史简历没有可定位的经历条目，本次无法执行证据核验。")
        return
    if not citations and not unsupported:
        st.caption("本次回答没有需要引用或标记的经历事实。")
        return

    st.caption(
        f"找到 {len(citations)} 条简历证据引用，"
        f"{len(unsupported)} 条待核实声明。"
    )
    if not st.checkbox(
        "展开证据详情",
        key=f"show_evidence_details_{evaluation.attempt_id}",
    ):
        return
    for citation in citations:
        support_label = "支持" if citation.get("support_level") == "supported" else "部分支持"
        with st.container(border=True):
            st.markdown(f"**{support_label}：** “{citation.get('claim', '')}”")
            st.caption(
                f"简历 #{citation.get('resume_id', '—')} · "
                f"{citation.get('section', '未命名章节')} / "
                f"{citation.get('entry', '未命名经历')} / "
                f"第 {_display_bullet_number(citation.get('bullet_index'))} 条"
            )
            st.markdown(f"> {citation.get('text', '')}")
            st.caption(citation.get("note", ""))
    for item in unsupported:
        st.warning(
            f"简历中未找到充分依据：“{item.get('claim', '')}”\n\n"
            f"{item.get('reason', '')}"
        )


def _display_bullet_number(value) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return "—"
    return str(value + 1)


def render_interview_button() -> None:
    """Render a button in match results to go to interview prep."""
    st.markdown("---")
    st.subheader("🎯 面试准备")

    if st.button("🤖 生成面试题", use_container_width=True, key="btn_gen_interview"):
        st.session_state["go_interview"] = True
        st.rerun()
