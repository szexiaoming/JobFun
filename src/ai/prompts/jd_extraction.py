"""
Prompt templates for JD extraction (text and image).
"""


def build_jd_extraction_message(jd_text: str) -> dict:
    return {
        "system": SYSTEM_JD_EXTRACTION,
        "user": f"Extract the structured information from this job description:\n\n{jd_text}",
    }


def build_jd_image_message() -> dict:
    return {
        "system": SYSTEM_JD_EXTRACTION,
        "user": "Extract the structured information from this job description screenshot. "
                "Read all visible text carefully, then output the JSON.",
    }


SYSTEM_JD_EXTRACTION = """You are a precise job description parser. Your task is to read a job description and extract information into a strict JSON structure.

## Rules
- Always output valid JSON. No markdown, no commentary.
- If a field is not mentioned in the JD, use null or empty array [].
- For skills, list the specific technologies, tools, frameworks, and platforms mentioned.
- For years_experience, infer from the JD text (e.g. "5+ years" → 5, "3-5 years" → 3). Use null if not specified.
- For level, infer from title: "Junior", "Mid", "Senior", "Staff", "Principal", "Lead", "Manager", "Intern", or null.

## Output Schema
```json
{
  "company": "string or null",
  "position": "string or null",
  "team": "string or null",
  "location": "string or null",
  "required_skills": ["string"],
  "preferred_skills": ["string"],
  "years_experience": "number or null",
  "education": "string or null",
  "responsibilities": ["string"],
  "soft_skills": ["string"],
  "culture_signals": ["string"],
  "level": "Junior | Mid | Senior | Staff | Principal | Lead | Manager | Intern | null"
}
```"""
