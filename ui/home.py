"""
Home page: Resume upload + JD input + trigger analysis.
"""

import io
from pathlib import Path

import streamlit as st

from config import (
    ALLOWED_JD_IMAGE_EXTENSIONS,
    ALLOWED_RESUME_EXTENSIONS,
    MAX_UPLOAD_SIZE_MB,
    UPLOAD_DIR,
    get_provider_display_name,
    supports_vision,
)
from src.core.jd_parser import JDParserError, list_jds, parse_jd_image, parse_jd_text
from src.core.latex_parser import LaTeXParserError, parse_resume_text, parse_resume_zip
from src.db.models import JobDescription, Resume
from src.db.sqlite_client import get_db
from src.utils.file_utils import save_uploaded_file, validate_extension, validate_file_size


def render_resume_section() -> None:
    """Resume upload section with text paste and zip upload tabs."""
    st.header("📄 步骤 1：上传简历")

    tab_text, tab_zip = st.tabs(["📝 文本粘贴", "📦 ZIP 上传"])

    # ── Text paste tab ──
    with tab_text:
        _render_text_resume_tab()

    # ── ZIP upload tab ──
    with tab_zip:
        _render_zip_resume_tab()

    # ── Shared: loaded status ──
    col1, col2 = st.columns([2, 1])
    with col1:
        pass
    with col2:
        if st.session_state.get("resume"):
            resume = st.session_state["resume"]
            source_label = "文本" if resume.latex_path == "" else "LaTeX"
            st.info(f"**已加载**：{resume.name}\n\n来源：{source_label} · v{resume.base_version}")
        else:
            st.info("尚未上传简历")

    if st.session_state.get("resume_json"):
        with st.expander("📋 查看解析结果"):
            st.json(st.session_state["resume_json"], expanded=False)


def _render_text_resume_tab() -> None:
    """Tab: paste resume text or upload .txt/.pdf file."""
    st.caption("直接粘贴简历文本，或上传 txt/pdf 文件，AI 会自动提取结构")

    resume_text = st.text_area(
        "粘贴简历内容",
        height=220,
        placeholder="将简历的文字内容粘贴到这里...\n\n示例格式：\n\nEducation\n• Master of CS, Stanford University, 2023\n\nExperience\n• Software Engineer at Google, 2023-Present\n  - Built scalable APIs handling 1M+ requests/day",
        key="resume_text_input",
    )

    col_file, _ = st.columns([1, 2])
    with col_file:
        text_file = st.file_uploader(
            "或上传文件（txt / pdf）",
            type=["txt", "pdf"],
            key="resume_text_uploader",
            help="上传纯文本或 PDF 简历，AI 会自动提取结构",
        )

    if st.button("📤 解析简历（文本）", use_container_width=True, key="parse_resume_text"):
        _handle_text_resume(resume_text, text_file)


def _render_zip_resume_tab() -> None:
    """Tab: upload Overleaf LaTeX zip."""
    st.caption("上传 Overleaf 项目的 zip 压缩包（包含 main.tex、cls 文件和 sections 目录）")

    uploaded = st.file_uploader(
        "上传 Overleaf 简历（zip 压缩包）",
        type=["zip"],
        key="resume_uploader",
        help="将 Overleaf 项目打包为 zip，包含 main.tex、cls 文件和 sections 目录",
    )

    if uploaded and st.button("📤 解析简历（ZIP）", use_container_width=True):
        try:
            validate_extension(Path(uploaded.name), ALLOWED_RESUME_EXTENSIONS)
            zip_path = save_uploaded_file(uploaded, UPLOAD_DIR)
            validate_file_size(zip_path)

            resume_dir, structured = parse_resume_zip(zip_path, uploaded.name)

            # Persist to DB
            db = get_db()
            resume = Resume(
                name=Path(uploaded.name).stem,
                latex_path=str(resume_dir),
                structured_json=structured,
            )
            resume_id = db.insert("resumes", resume)
            resume.id = resume_id

            st.session_state["resume"] = resume
            st.session_state["resume_json"] = structured
            st.success(f"✅ 简历解析成功！{len(structured['sections'])} 个 section")

        except (JDParserError, LaTeXParserError, FileNotFoundError) as e:
            st.error(f"❌ {e}")
        except Exception as e:
            st.error(f"❌ 解析失败：{e}")


def _handle_text_resume(resume_text: str, text_file) -> None:
    """Parse text resume (from paste or file) and store in session state."""
    # Determine the source text
    if text_file is not None:
        # File upload takes priority
        try:
            # Check file size (Streamlit uploaded file, use .size attribute)
            size_mb = text_file.size / (1024 * 1024)
            if size_mb > MAX_UPLOAD_SIZE_MB:
                st.error(f"文件过大：{size_mb:.1f}MB（最大 {MAX_UPLOAD_SIZE_MB}MB）")
                return

            if text_file.name.lower().endswith(".pdf"):
                _parse_pdf_resume(text_file)
                return
            else:
                # .txt file
                text = text_file.read().decode("utf-8", errors="ignore")
                name = Path(text_file.name).stem
        except Exception as e:
            st.error(f"❌ 读取文件失败：{e}")
            return
    elif resume_text.strip():
        text = resume_text.strip()
        name = "文本简历"
    else:
        st.warning("请先粘贴简历文本或上传文件")
        return

    if not text.strip():
        st.warning("简历内容为空")
        return

    try:
        with st.spinner("AI 正在解析简历结构..."):
            structured = parse_resume_text(text)

        # Persist to DB
        db = get_db()
        resume = Resume(
            name=name,
            latex_path="",  # No LaTeX source for text resumes
            structured_json=structured,
        )
        resume_id = db.insert("resumes", resume)
        resume.id = resume_id

        st.session_state["resume"] = resume
        st.session_state["resume_json"] = structured
        st.success(f"✅ 简历解析成功！{len(structured.get('sections', []))} 个 section")

    except LaTeXParserError as e:
        st.error(f"❌ {e}")
    except Exception as e:
        st.error(f"❌ 解析失败：{e}")


def _parse_pdf_resume(pdf_file) -> None:
    """Extract text from a PDF resume file, then parse with AI."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        st.error("❌ 需要安装 PyPDF2：`pip install PyPDF2`")
        return

    try:
        reader = PdfReader(pdf_file)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        text = "\n\n".join(text_parts)

        if not text.strip():
            st.error("❌ PDF 中未提取到文字（可能是扫描版图片 PDF，请尝试粘贴文字）")
            return

        name = Path(pdf_file.name).stem

        with st.spinner("AI 正在解析简历结构..."):
            structured = parse_resume_text(text)

        db = get_db()
        resume = Resume(
            name=name,
            latex_path="",
            structured_json=structured,
        )
        resume_id = db.insert("resumes", resume)
        resume.id = resume_id

        st.session_state["resume"] = resume
        st.session_state["resume_json"] = structured
        st.success(f"✅ 简历解析成功！{len(structured.get('sections', []))} 个 section")

    except LaTeXParserError as e:
        st.error(f"❌ {e}")
    except Exception as e:
        st.error(f"❌ PDF 解析失败：{e}")


def render_jd_section() -> None:
    """JD input section with tabbed text/image inputs."""
    st.header("📋 步骤 2：输入职位描述（JD）")
    st.caption("支持文本粘贴、图片截图、或 PDF 上传")

    tab_text, tab_image = st.tabs(["📝 文本粘贴", "🖼️ 图片上传"])

    # ── Text tab ──
    with tab_text:
        jd_text = st.text_area(
            "粘贴 JD 文本",
            height=200,
            placeholder="将职位描述的文字内容粘贴到这里...",
            key="jd_text_input",
        )
        if st.button("🔍 解析 JD（文本）", use_container_width=True, key="parse_text"):
            _handle_text_jd(jd_text)

    # ── Image tab ──
    with tab_image:
        if not supports_vision():
            st.warning(
                f"⚠️ 当前 {get_provider_display_name()} 配置不支持图片识别。"
                "请切换到「文本粘贴」Tab 输入 JD，"
                "或设置 AI_PROVIDER=anthropic 启用视觉能力。"
            )
        image_file = st.file_uploader(
            "上传 JD 截图或照片",
            type=["png", "jpg", "jpeg", "webp"],
            key="jd_image_uploader",
            help="支持截图或拍照；需要当前 AI 配置具备视觉能力",
        )
        if image_file and st.button("🔍 解析 JD（图片）", use_container_width=True, key="parse_image"):
            _handle_image_jd(image_file)


def _handle_text_jd(jd_text: str) -> None:
    """Parse text JD and store in session state."""
    if not jd_text.strip():
        st.warning("请先粘贴 JD 文本")
        return
    try:
        with st.spinner(f"{get_provider_display_name()} 正在解析 JD..."):
            jd = parse_jd_text(jd_text)
        st.session_state["jd"] = jd
        st.session_state["jd_json"] = jd.structured_json
        st.success(f"✅ 解析完成：{jd.company} — {jd.position}")
    except JDParserError as e:
        st.error(f"❌ {e}")


def _handle_image_jd(image_file) -> None:
    """Parse image JD and store in session state."""
    try:
        image_data = image_file.read()
        with st.spinner(f"{get_provider_display_name()} 正在识别并解析 JD 截图..."):
            jd = parse_jd_image(image_data, image_file.name)
        st.session_state["jd"] = jd
        st.session_state["jd_json"] = jd.structured_json
        st.success(f"✅ 解析完成：{jd.company} — {jd.position}")
    except JDParserError as e:
        st.error(f"❌ {e}")


def render_jd_preview() -> None:
    """Show parsed JD preview."""
    if not st.session_state.get("jd_json"):
        return

    jd = st.session_state["jd"]
    jd_json = st.session_state["jd_json"]

    with st.expander("📋 查看解析的 JD 结构", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("公司", jd_json.get("company") or "—")
            st.metric("级别", jd_json.get("level") or "—")
        with col2:
            st.metric("职位", jd_json.get("position") or "—")
            st.metric("经验要求", f"{jd_json.get('years_experience')} 年" if jd_json.get("years_experience") else "—")
        with col3:
            st.metric("团队", jd_json.get("team") or "—")
            st.metric("学历", jd_json.get("education") or "—")

        st.write("**必须技能**：", ", ".join(jd_json.get("required_skills", [])) or "—")
        st.write("**加分技能**：", ", ".join(jd_json.get("preferred_skills", [])) or "—")


def render_action_button() -> None:
    """The main action button that triggers match analysis."""
    st.divider()

    ready = st.session_state.get("resume") and st.session_state.get("jd")
    if not ready:
        st.warning("⚠️ 请先上传简历并输入 JD，然后才能开始分析")
        return

    st.header("🚀 步骤 3：开始分析")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🔍 开始匹配分析", use_container_width=True, type="primary"):
            st.session_state["run_match"] = True
            st.rerun()
