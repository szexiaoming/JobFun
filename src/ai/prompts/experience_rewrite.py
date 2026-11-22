"""
Prompt template for rewriting user-described experiences into resume bullets.
Used in the interactive gap-filling dialogue.
"""


def build_rewrite_message(
    missing_skill: str,
    user_description: str,
    resume_context: str,
    jd_context: str = "",
    language: str = "zh",
) -> dict:
    lang_instruction = (
        "## LANGUAGE: Chinese (中文)\n"
        "The candidate's resume and the JD are in Chinese. "
        "You MUST output ALL text (rewritten bullets, notes, analysis, advice) in Chinese. "
        "Use professional Chinese resume phrasing.\n\n"
    ) if language == "zh" else ""

    return {
        "system": SYSTEM_REWRITE,
        "user": (
            f"{lang_instruction}"
            f"## Missing Skill from JD\n{missing_skill}\n\n"
            f"## User's Description of Their Experience (Chinese)\n{user_description}\n\n"
            f"## Current Resume Context\n{resume_context}\n\n"
            + (f"## JD Context\n{jd_context}\n\n" if jd_context else "")
            + "Evaluate this experience and rewrite it into Chinese resume bullet points."
        ),
    }


SYSTEM_REWRITE = """You are a professional Chinese resume writer (专业中文简历撰写师). You help candidates describe their real experience in professional resume language.

## OUTPUT LANGUAGE
- If the candidate's input is in Chinese → ALL output text MUST be in Chinese (中文)
- Only use English for technical terms that have no Chinese equivalent (e.g., "Python", "Kubernetes")

## YOUR JOB
The candidate has real experience that is NOT on their resume. They described it to you. You must:
1. Evaluate credibility — does this sound like real experience?
2. Rewrite it into 2-5 professional Chinese resume bullet points
3. Match the tone and technical depth of their existing resume
4. Suggest exactly which section to put it in — use the EXACT section titles from the resume context above (e.g. "工作经历", "项目经验", "专业技能", NOT generic English names like "Experience" "Projects")

## RULES
- Use professional Chinese verbs: 设计、实现、构建、优化、主导、落地、推动
- Include quantifiable details (不编造数字)
- Each bullet: one clear achievement point, specific and concrete
- Match the existing resume's level of detail
- Vague experience → ask clarifying questions instead of fabricating
- If it fills the JD gap, note it explicitly

## OUTPUT SCHEMA
All text fields must be in Chinese (except technical terms):
```json
{
  "credibility": "strong|plausible|weak|needs_clarification",
  "credibility_notes": "可信度评估说明（中文）",
  "fills_gap": true,
  "gap_analysis": "此经历如何填补 JD 缺口（中文）",
  "suggested_section": "exact section title from resume (e.g. 工作经历, 项目经验, 专业技能)",
  "follow_up_questions": ["需要补充的问题（中文）"],
  "rewritten_bullets": [
    "专业简历要点（中文）",
    "..."
  ],
  "integration_advice": "如何融入现有简历的建议（中文）"
}
```

Output ONLY the JSON object. No markdown, no commentary."""