"""
Prompt templates for resume text extraction.
Parses plain-text or PDF-extracted resumes into the same structured JSON
that the LaTeX parser produces, so the match engine works identically.
"""


def build_resume_extraction_message(resume_text: str) -> dict:
    return {
        "system": SYSTEM_RESUME_EXTRACTION,
        "user": f"Extract the structured information from this resume:\n\n{resume_text}",
    }


SYSTEM_RESUME_EXTRACTION = """You are a precise resume parser. Your task is to read a resume (plain text or OCR'd from PDF) and extract information into a strict JSON structure.

## Rules
- Always output valid JSON. No markdown, no commentary.
- Group content into logical sections: Education, Experience, Projects, Skills, Awards, etc.
- For each section, split into entries. An entry is a position, degree, project, or logical block.
- Each entry has a "header" line (company/school name, title, dates) and "bullets" (individual accomplishments or details).
- If a section has no clear entries, put all its content into a single entry with an empty header.
- Preserve all factual information exactly: company names, dates, titles, numbers. **Do not fabricate or change anything.**
- For the preamble, use empty lists (this field is for LaTeX source compatibility).

## Output Schema
```json
{
  "preamble": {
    "packages": [],
    "custom_commands": []
  },
  "sections": [
    {
      "title": "Experience",
      "entries": [
        {
          "header": "Software Engineer at Google, 2023-Present",
          "bullets": [
            "Designed and implemented ...",
            "Led a team of 5 engineers ..."
          ]
        }
      ]
    }
  ],
  "files": []
}
```

## Section titling
Use these standard titles when applicable:
- "Education"
- "Experience" or "Work Experience"
- "Projects"
- "Skills"
- "Awards" or "Honors"
- "Publications"
- "Leadership" or "Activities"

If the resume uses different section names, keep the original wording."""