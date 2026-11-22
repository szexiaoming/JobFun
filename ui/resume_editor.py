"""
Resume editor UI: select suggestions, preview diff, confirm/reject, rollback.
"""

from pathlib import Path

import streamlit as st

from config import DATA_DIR
from src.core.latex_modifier import (
    LaTeXModifierError,
    get_modification_history,
    modify_resume,
    rollback_modification,
)
from src.core.pdf_compiler import PDFCompilerError, generate_pdf
from src.utils.diff_utils import diff_stats
from src.utils.logger import logger


def render_editor_section() -> None:
    """Render the resume editing section with suggestion selection and diff preview."""

    match_data = st.session_state.get("match_data")
    resume = st.session_state.get("resume")
    resume_json = st.session_state.get("resume_json")
    jd_json = st.session_state.get("jd_json")

    if not match_data or not resume:
        return

    suggestions = match_data.get("suggestions", [])
    accepted = st.session_state.get("accepted_suggestions", [])
    pending_additions = st.session_state.get("pending_additions", [])

    if not accepted and not pending_additions:
        return

    st.divider()

    accept_count = len(accepted)
    add_count = len(pending_additions)
    total = accept_count + add_count

    if total == 0:
        return

    title = f"✏️ 修改简历（{total} 条待执行）"
    st.header(title)

    # ── Accepted suggestion changes ──
    if accepted:
        st.success(f"✅ 已采纳 {accept_count} 条建议")
        for i, item in enumerate(accepted):
            with st.container(border=True):
                edited_mark = "✏️ 已编辑" if item.get("edited") else ""
                st.caption(f"**建议 {i+1}** {edited_mark}")
                st.markdown(f"原文: _{item['original'][:100]}_")
                st.markdown(f"修改为: **{item['suggested'][:150]}**")
                if st.button("🗑️ 移除", key=f"rm_acc_{i}"):
                    st.session_state["accepted_suggestions"].pop(i)
                    st.rerun()
        st.divider()

    # ── Pending additions (from dialogue) ──
    if pending_additions:
        with st.expander(f"📝 补充经历（{add_count} 条）", expanded=True):
            for i, add in enumerate(pending_additions):
                with st.container(border=True):
                    st.markdown(f"**目标技能**：`{add['missing_skill']}`")
                    for b in add["bullets"]:
                        st.markdown(f"- {b}")
                    st.caption(f"📁 {add['suggested_section']}")
                    if st.button("🗑️ 移除此条", key=f"rm_add_{i}"):
                        st.session_state["pending_additions"].pop(i)
                        st.rerun()
        st.divider()

    # ── Preview ──
    if st.session_state.get("resume_json"):
        from ui.components import render_preview_panel
        all_changes = accepted + pending_additions
        with st.expander("📄 预览修改效果", expanded=False):
            render_preview_panel(st.session_state["resume_json"], all_changes)

    # ── Action buttons ──
    can_execute = bool(accepted or pending_additions)
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔍 预览 Diff", use_container_width=True,
                     type="primary", disabled=not can_execute):
            with st.spinner("AI 正在生成修改预览..."):
                _run_modification(
                    resume, accepted, pending_additions,
                    resume_json, jd_json, dry_run=True,
                )

    with col2:
        if st.button("✅ 确认修改", use_container_width=True,
                     disabled=not can_execute):
            with st.spinner("正在修改 + 验证..."):
                _run_modification(
                    resume, accepted, pending_additions,
                    resume_json, jd_json, dry_run=False,
                )

    with col3:
        if st.button("↩ 回滚", use_container_width=True, key="btn_rollback"):
            try:
                old_hash = rollback_modification(Path(resume.latex_path))
                st.success(f"已回滚 {old_hash}")
                # Clear accepted list on rollback
                st.session_state["accepted_suggestions"] = []
                st.rerun()
            except LaTeXModifierError as e:
                st.error(str(e))

    # ── Show diff ──
    if "modification_result" in st.session_state:
        _render_modification_result()

    # ── History ──
    if resume.latex_path:
        history = get_modification_history(Path(resume.latex_path))
        if history:
            with st.expander(f"📜 修改历史（{len(history)} 条）"):
                for h in history:
                    st.markdown(f"`{h['hash']}` **{h['message']}** — {h['date']}")


def _run_modification(
    resume, suggestions, additions,
    resume_json, jd_json, dry_run: bool,
) -> None:
    """Execute or preview a modification."""
    try:
        result = modify_resume(
            resume_dir=Path(resume.latex_path),
            suggestions=suggestions,
            pending_additions=additions,
            structured_resume=resume_json,
            jd_json=jd_json,
            dry_run=dry_run,
        )
        st.session_state["modification_result"] = result

        if dry_run:
            st.session_state["modification_result"]["dry_run"] = True

        if result["success"]:
            st.success("✅ 修改成功！")
        else:
            st.error(f"❌ {result.get('error', '修改失败')}")
    except LaTeXModifierError as e:
        st.error(f"❌ {e}")


def _render_modification_result() -> None:
    """Render the modification diff and actions."""
    result = st.session_state["modification_result"]

    st.divider()
    is_dry = result.get("dry_run", False)
    st.subheader("🔍 修改预览" if is_dry else "✅ 修改结果")

    # Validation
    validation = result.get("validation")
    if validation:
        if not validation.passed:
            for v in validation.violations:
                st.error(f"🚫 {v}")
        for w in validation.warnings:
            st.warning(f"⚠️ {w}")

    # Diff
    diff_text = result.get("diff", "")
    if diff_text:
        stats = diff_stats("", "")  # placeholder
        st.code(diff_text, language="diff", line_numbers=True)
    else:
        st.info("无内容变更")

    # Commit info
    if result.get("commit_hash"):
        st.caption(f"Commit: `{result['commit_hash']}`")

    # Actions after modification
    if result["success"] and not is_dry:
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📊 重新评估匹配度", use_container_width=True,
                         type="primary", key="btn_reevaluate"):
                _reevaluate_after_modification()
                st.rerun()
        with col2:
            if st.button("📥 下载 LaTeX", use_container_width=True,
                         key="btn_download_latex2"):
                _prepare_download()
        with col3:
            _render_pdf_section()

        # Show before/after comparison if re-evaluated
        if "after_match_data" in st.session_state:
            st.divider()
            _render_before_after_comparison()


def _render_pdf_section() -> None:
    """Render the PDF generation button and result."""
    resume = st.session_state.get("resume")
    if not resume:
        return

    st.subheader("📄 生成 PDF")

    if st.button("🔨 编译 PDF", use_container_width=True, key="compile_pdf"):
        with st.spinner("正在编译 LaTeX → PDF ..."):
            output_dir = DATA_DIR / "outputs"
            output_dir.mkdir(parents=True, exist_ok=True)

            try:
                result = generate_pdf(
                    tex_dir=Path(resume.latex_path),
                    output_dir=output_dir,
                    auto_fix=True,
                )

                if result["success"]:
                    st.session_state["pdf_result"] = result
                    st.success(f"✅ PDF 生成成功！({result['attempts']} 次编译)")
                else:
                    if not result["compiler_available"]:
                        st.warning(result["error"])
                    else:
                        st.error(f"编译失败：{result.get('error', '')[:300]}")
                        st.info("请检查 LaTeX 源码后重试")

            except PDFCompilerError as e:
                st.error(f"❌ {e}")

    # Show download if PDF was generated
    pdf_result = st.session_state.get("pdf_result")
    if pdf_result and pdf_result["success"]:
        pdf_path = pdf_result["pdf_path"]
        if pdf_path and pdf_path.exists():
            from src.latex.compiler import get_page_count
            pages = get_page_count(pdf_path)
            page_note = f"· {pages} 页"
            if pages > 1:
                page_note += " ⚠️（建议压缩为一页）"

            with open(pdf_path, "rb") as f:
                pdf_data = f.read()
            st.download_button(
                label=f"📥 下载 PDF ({pdf_path.stat().st_size / 1024:.0f} KB {page_note})",
                data=pdf_data,
                file_name=pdf_path.name,
                mime="application/pdf",
                use_container_width=True,
            )


def _prepare_download() -> None:
    """Prepare LaTeX source for download — Overleaf-compatible zip."""
    import zipfile
    import io
    from pathlib import Path

    resume = st.session_state.get("resume")
    if not resume:
        return

    buf = io.BytesIO()
    resume_dir = Path(resume.latex_path)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(resume_dir.rglob("*")):
            # Skip .git directory and its contents
            if ".git" in f.parts:
                continue
            if not f.is_file():
                continue
            # Skip LaTeX auxiliary files
            if f.suffix.lower() in (".aux", ".log", ".out", ".toc", ".bbl", ".blg", ".synctex"):
                continue
            arcname = f.relative_to(resume_dir)
            zf.write(f, arcname)

    st.download_button(
        label="📥 下载 LaTeX 源码包",
        data=buf.getvalue(),
        file_name=f"{resume.name}_modified.zip",
        mime="application/zip",
        key="btn_download_latex",
    )


def _reevaluate_after_modification() -> None:
    """Re-parse modified LaTeX and re-run match analysis."""
    from pathlib import Path
    from src.core.latex_parser import parse_resume_zip
    from src.core.match_engine import run_match

    resume = st.session_state.get("resume")
    jd_json = st.session_state.get("jd_json")
    old_match = st.session_state.get("match_data")

    if not resume or not jd_json:
        st.error("缺少简历或 JD 数据")
        return

    # Save old score for comparison
    old_score = old_match["match_result"].total_score if old_match else None

    # Re-parse modified LaTeX
    resume_dir = Path(resume.latex_path)
    from src.core.latex_parser import parse_tex_files
    from src.utils.file_utils import collect_tex_files, find_main_tex

    try:
        main_tex = find_main_tex(resume_dir)
        all_files = collect_tex_files(resume_dir)
        new_resume_json = parse_tex_files(main_tex, all_files, resume_dir)
    except Exception as e:
        st.error(f"重新解析简历失败：{e}")
        return

    # Update session with new resume structure
    st.session_state["resume_json"] = new_resume_json
    resume.structured_json = new_resume_json

    # Re-run match
    with st.spinner("🤖 正在重新评估修改后的简历..."):
        try:
            jd = st.session_state.get("jd")
            new_match = run_match(
                resume,
                jd_json,
                new_resume_json,
                jd_id=getattr(jd, "id", 0) or 0,
            )
            new_match["old_total_score"] = old_score
            st.session_state["after_match_data"] = new_match
            st.session_state["match_data"] = new_match  # Update current
        except Exception as e:
            st.error(f"重新评估失败：{e}")


def _render_before_after_comparison() -> None:
    """Show before/after match score comparison."""
    after = st.session_state.get("after_match_data")
    if not after:
        return

    old_score = after.get("old_total_score")
    new_score = after["match_result"].total_score

    st.subheader("📊 修改前后对比")

    col1, col2, col3 = st.columns([2, 1, 2])

    with col1:
        st.metric("修改前匹配度", f"{old_score:.0f}%" if old_score else "—")

    with col3:
        if old_score is not None:
            delta = new_score - old_score
            st.metric(
                "修改后匹配度",
                f"{new_score:.0f}%",
                delta=f"{delta:+.0f}%",
                delta_color="normal" if delta >= 0 else "inverse",
            )
        else:
            st.metric("修改后匹配度", f"{new_score:.0f}%")

    # Score breakdown comparison
    if old_score is not None:
        st.caption("**各维度对比**")
        dims = [
            ("技能匹配", "skill_score"),
            ("经验匹配", "experience_score"),
            ("学历匹配", "education_score"),
            ("软技能", "soft_skill_score"),
            ("文化匹配", "culture_score"),
        ]
        cols = st.columns(5)
        for col, (label, key) in zip(cols, dims):
            # We don't have per-dimension old scores stored separately,
            # so just show the new ones
            new_val = getattr(after["match_result"], key, 0)
            with col:
                st.metric(label, f"{new_val:.0f}%")
