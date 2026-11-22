"""
Handler functions for agent tools.

IMPORTANT DESIGN DECISION:
    The agent does NOT do fragmented analysis (skill-by-skill, entry-by-entry).
    Instead, it uses the existing comprehensive pipeline (match_engine.run_match)
    which does ONE high-quality LLM call with full context.

    The agent's value-add is:
    1. Interactive gap investigation (asking the user about potential hidden experience)
    2. Self-verification of suggestions (safety check)
    3. Controlled modification execution (with Git backup + validation)
    4. Natural dialogue flow around the analysis results
"""

import json
from pathlib import Path
from typing import Any

from src.utils.logger import logger


# ═══════════════════════════════════════════════════════
# Core Analysis Tool (uses existing comprehensive pipeline)
# ═══════════════════════════════════════════════════════


def run_comprehensive_analysis(
    jd_json: dict = None,
    resume_json: dict = None,
    resume_dir: str = "",
    resume_id: int = 0,
    jd_text: str = "",
    jd_source_type: str = "text",
    jd_id: int = 0,
) -> dict:
    """
    Run the comprehensive match analysis using the existing pipeline.

    This is THE primary analysis tool. It calls match_engine.run_match()
    which does a single, context-rich LLM call producing:
    - 6-dimension scores (total, skill, experience, education, soft_skill, culture)
    - matched_skills, missing_skills, risks
    - suggestions list with category, priority, original_text, suggested_text, rationale
    - summary

    This ensures analysis quality matches the original pipeline exactly.
    """
    from src.core.jd_parser import parse_jd_text
    from src.core.latex_parser import parse_resume_text
    from src.core.match_engine import run_match
    from src.db.models import JobDescription, Resume
    from src.db.sqlite_client import get_db, row_to_model

    try:
        # ── Step 1: Parse JD if needed ──
        if not jd_json and jd_text:
            logger.info("Agent: parsing JD from text...")
            if jd_source_type == "text":
                jd = parse_jd_text(jd_text)
                jd_json = jd.structured_json
                jd_id = jd.id or 0
            else:
                return {
                    "success": False,
                    "error": f"JD parsing for source_type={jd_source_type} requires text input",
                }

        if not jd_json:
            return {
                "success": False,
                "error": "没有 JD 数据。请先输入 JD。",
            }

        # ── Step 2: Parse resume if needed ──
        if not resume_json and resume_dir:
            logger.info("Agent: parsing resume from %s...", resume_dir)
            from src.utils.file_utils import collect_tex_files

            resume_path = Path(resume_dir)
            if resume_path.exists():
                tex_files = collect_tex_files(resume_path)
                main_tex = ""
                # Find main.tex or the largest .tex file
                for fname, content in tex_files.items():
                    if "main" in fname.lower() or len(content) > len(main_tex):
                        main_tex = content
                if main_tex:
                    resume_json = parse_resume_text(main_tex)
                else:
                    return {"success": False, "error": f"在 {resume_dir} 中没有找到 .tex 文件"}
            else:
                return {"success": False, "error": f"简历目录不存在: {resume_dir}"}

        if not resume_json:
            return {
                "success": False,
                "error": "没有简历数据。请先上传简历。",
            }

        # ── Step 3: Create a Resume DB record (or use existing) ──
        db = get_db()
        resume_row = db.get("resumes", resume_id) if resume_id else None
        if resume_row:
            resume = row_to_model(resume_row, Resume)
            resume.structured_json = resume_json
        else:
            resume = Resume(
                name="agent-loaded",
                latex_path=resume_dir,
                structured_json=resume_json,
            )
            resume.id = db.insert("resumes", resume)

        if not jd_id:
            jd = JobDescription(
                company=jd_json.get("company", ""),
                position=jd_json.get("position", ""),
                raw_text=jd_text,
                source_type=jd_source_type,
                structured_json=jd_json,
            )
            jd_id = db.insert("job_descriptions", jd)

        # ── Step 4: Run the comprehensive match ──
        logger.info("Agent: running comprehensive match analysis...")
        result = run_match(resume, jd_json, resume_json, jd_id=jd_id)

        match = result.get("match_result")
        suggestions = result.get("suggestions", [])

        # ── Step 5: Format for agent consumption ──
        return {
            "success": True,
            "match_result": {
                "total_score": match.total_score if match else 0,
                "skill_score": match.skill_score if match else 0,
                "experience_score": match.experience_score if match else 0,
                "education_score": match.education_score if match else 0,
                "soft_skill_score": match.soft_skill_score if match else 0,
                "culture_score": match.culture_score if match else 0,
                "matched_skills": result.get("matched_skills", []),
                "missing_skills": result.get("missing_skills", []),
                "risks": result.get("risks", []),
                "summary": result.get("summary", ""),
            },
            "suggestions": [
                {
                    "category": s.category,
                    "priority": s.priority,
                    "original_text": s.original_text,
                    "suggested_text": s.suggested_text,
                    "rationale": s.rationale,
                }
                for s in suggestions
            ],
            "suggestion_count": len(suggestions),
            "analysis_quality": "comprehensive",  # Marker that this used the full pipeline
        }

    except Exception as e:
        logger.error("Comprehensive analysis failed: %s", e)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Parsing Tools (for when data isn't provided upfront)
# ═══════════════════════════════════════════════════════


def parse_job_description(source_type: str, content: str) -> dict:
    """Parse JD text into structured JSON using the existing JD parser."""
    from src.ai.client import get_ai_client

    try:
        client = get_ai_client()
        if source_type == "text":
            jd = client.extract_jd_from_text(content)
        elif source_type == "pdf":
            jd = client.extract_jd_from_text(content)
        else:
            return {"success": False, "error": f"不支持的 JD 类型: {source_type}"}

        return {
            "success": True,
            "jd": jd,
            "company": jd.get("company", "?"),
            "position": jd.get("position", "?"),
            "skills_required": len(jd.get("required_skills", [])),
            "skills_preferred": len(jd.get("preferred_skills", [])),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def parse_resume(resume_dir: str) -> dict:
    """Parse LaTeX resume from directory using the existing parser."""
    from src.core.latex_parser import parse_resume_text
    from src.utils.file_utils import collect_tex_files

    try:
        resume_path = Path(resume_dir)
        if not resume_path.exists():
            return {"success": False, "error": f"简历目录不存在: {resume_dir}"}

        tex_files = collect_tex_files(resume_path)
        main_tex = ""
        for fname, content in tex_files.items():
            if "main" in fname.lower() or len(content) > len(main_tex):
                main_tex = content

        if not main_tex:
            return {"success": False, "error": "没有找到 .tex 文件"}

        result = parse_resume_text(main_tex)

        sections_summary = []
        for section in result.get("sections", []):
            title = section.get("title", "Untitled")
            entries = section.get("entries", [])
            sections_summary.append({
                "title": title,
                "entry_count": len(entries),
                "entry_headers": [e.get("header", "")[:80] for e in entries],
            })

        return {
            "success": True,
            "resume": result,
            "summary": {
                "section_count": len(result.get("sections", [])),
                "sections": sections_summary,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Interactive Tools
# ═══════════════════════════════════════════════════════


def ask_user_clarification(question: str, context: str, options: list = None) -> dict:
    """
    Ask the user a clarifying question.

    Used when the comprehensive analysis finds a gap, and the agent
    suspects the candidate might have unlisted experience.
    """
    return {
        "success": True,
        "needs_user_response": True,
        "question": question,
        "context": context,
        "options": options or [],
    }


def investigate_gap(
    missing_skill: str,
    resume_context: str = "",
    jd_requirement: str = "",
) -> dict:
    """
    Analyze a specific skill gap from the comprehensive match results.

    Unlike the old approach, this works WITH the comprehensive analysis
    results, not instead of them. It digs deeper into a specific gap
    that was already identified.
    """
    from config import get_active_model
    from src.ai.client import get_ai_client

    try:
        client = get_ai_client()
        prompt = f"""基于以下信息，深入分析"{missing_skill}"这项技能的差距，并判断候选人是否可能有未体现的相关经验。

## JD 要求
{jd_requirement or "详见 JD 原文"}

## 简历中相关内容
{resume_context or "简历中未明确提及该技能"}

## 分析任务
1. 判断这是否是硬性要求（没有就一票否决）还是加分项；
2. 候选人是否有相邻/可迁移的技能（例如：JD 要求 K8s，简历有 Docker + 容器化经验）；
3. 如果候选人可能有但没写，生成一个自然的问题来确认；
4. 给出弥补这个差距的具体策略。

请以 JSON 格式输出（用中文）：
{{"is_hard_requirement": true/false, "transferable_skills": ["可迁移的技能"],
 "should_ask_user": true/false, "suggested_question": "向用户确认的问题",
 "gap_strategy": "弥补策略", "severity": "critical|moderate|minor"}}"""

        raw = client._call(
            model=get_active_model("evaluation"),
            system="你是一个技能差距分析专家。用中文输出。",
            user_text=prompt,
            temperature=0.2,
            max_tokens=2048,
        )
        return {"success": True, "gap_analysis": raw}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Suggestion & Validation Tools
# ═══════════════════════════════════════════════════════


def generate_suggestion(
    category: str,
    gap_description: str,
    resume_context: str,
    jd_context: str,
) -> dict:
    """Generate a single resume modification suggestion."""
    from config import get_active_model
    from src.ai.client import get_ai_client

    if category not in ("keyword", "wording", "structure", "highlight", "de_emphasize", "quantify"):
        return {"success": False, "error": f"无效的类别: {category}"}

    try:
        client = get_ai_client()
        prompt = f"""请生成一条具体的简历修改建议。

## 类别：{category}
## 差距：{gap_description}
## 简历原文：{resume_context}
## JD 要求：{jd_context}

⚠️ 绝不编造经历。只优化表达。

输出 JSON（用中文）：
{{"category": "{category}", "priority": 1-5, "original_text": "简历原文",
 "suggested_text": "修改后文本", "rationale": "修改理由"}}"""

        raw = client._call(
            model=get_active_model("structured"),
            system="你是简历优化专家。绝不编造经历。用中文输出。",
            user_text=prompt,
            temperature=0.3,
            max_tokens=2048,
        )
        return {"success": True, "suggestion": raw}
    except Exception as e:
        return {"success": False, "error": str(e)}


def validate_suggestion(suggestion: dict, original_resume: str) -> dict:
    """Safety-check a suggestion."""
    from config import get_active_model
    from src.ai.client import get_ai_client

    try:
        client = get_ai_client()
        original = suggestion.get("original_text", "")
        suggested = suggestion.get("suggested_text", "")

        prompt = f"""安全审查这条简历修改建议：

## 原文：{original}
## 改为：{suggested}
## 完整简历：{original_resume[:3000]}

检查：编造经历？改公司名？改日期？注入新技能？

输出 JSON（用中文）：
{{"is_safe": true/false, "violations": [], "warnings": [],
 "fabrication_risk": "none|low|high", "recommendation": "approve|reject|modify"}}"""

        raw = client._call(
            model=get_active_model("evaluation"),
            system="你是简历安全审查员。严格但公正。用中文输出。",
            user_text=prompt,
            temperature=0.1,
            max_tokens=1024,
        )
        return {"success": True, "validation": raw}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Execution Tools
# ═══════════════════════════════════════════════════════


def apply_modifications(suggestions: list, resume_dir: str) -> dict:
    """Apply approved suggestions to LaTeX files with Git backup."""
    from src.core.latex_modifier import modify_resume
    from src.utils.git_utils import init_repo

    try:
        resume_path = Path(resume_dir)
        if not resume_path.exists():
            return {"success": False, "error": f"目录不存在: {resume_dir}"}

        init_repo(resume_path)
        result = modify_resume(
            resume_dir=resume_path,
            suggestions=suggestions,
            pending_additions=None,
            dry_run=False,
        )

        if result.get("success"):
            return {
                "success": True,
                "commit_hash": result.get("commit_hash", ""),
                "diff_preview": result.get("diff", "")[:2000],
                "files_modified": list(result.get("modified_files", {}).keys()),
                "summary": f"已应用 {len(suggestions)} 条修改",
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "未知错误"),
                "validation_failures": result.get("validation", {}).get("violations", []),
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def validate_changes(resume_dir: str) -> dict:
    """Post-modification safety validation."""
    from src.latex.validator import validate_changes as latex_validate
    from src.utils.file_utils import collect_tex_files

    try:
        resume_path = Path(resume_dir)
        tex_files = collect_tex_files(resume_path)
        validation = latex_validate(
            original_files=tex_files,
            modified_files=tex_files,
            original_structure={},
        )
        return {
            "success": True,
            "passed": validation.passed,
            "violations": validation.violations,
            "warnings": validation.warnings,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Interview Prep Tool
# ═══════════════════════════════════════════════════════


def generate_interview_questions(category: str = "all", focus_areas: list = None) -> dict:
    """Generate targeted interview prep questions."""
    from config import get_active_model
    from src.ai.client import get_ai_client

    try:
        client = get_ai_client()
        focus_text = "\n".join(f"- {a}" for a in (focus_areas or [])) if focus_areas else "综合"

        prompt = f"""请生成面试准备问题。

## 类别：{category}
## 重点方向：{focus_text}

输出 JSON（用中文）：
{{"interview_focus": "重点描述", "categories": {{
  "{category if category != 'all' else 'technical'}": [
    {{"question": "问题", "difficulty": "easy|medium|hard", "tip": "回答要点"}}
  ]
}}}}"""

        raw = client._call(
            model=get_active_model("structured"),
            system="你是面试准备专家。用中文生成。",
            user_text=prompt,
            temperature=0.5,
            max_tokens=4096,
        )
        return {"success": True, "questions": raw}
    except Exception as e:
        return {"success": False, "error": str(e)}
