"""
Prompt template for AI-powered LaTeX modification.
The AI receives the full .tex content + suggestions and must output modified files.
"""


def build_latex_edit_message(
    original_files: str,
    suggestions: str,
    additions: str,
    jd_context: str = "",
) -> dict:
    return {
        "system": SYSTEM_LATEX_EDIT,
        "user": (
            f"## Current LaTeX Files\n```\n{original_files}\n```\n\n"
            f"## Modifications to Apply\n{suggestions}\n\n"
            + (f"## New Bullet Points to Add\n{additions}\n\n" if additions.strip() not in ("[]", "") else "")
            + (f"## JD Context\n{jd_context}\n\n" if jd_context else "")
            + "Apply ONLY these modifications. Output the complete modified files as a JSON object."
        ),
    }


SYSTEM_LATEX_EDIT = """You are a precise LaTeX editor. Your task is to apply specific text modifications to LaTeX resume files.

## CRITICAL RULES — NEVER VIOLATE

### What you CAN do:
1. Replace exact text snippets with the suggested improved versions
2. Add new \\item bullet points to existing \\begin{itemize}...\\end{itemize} blocks
3. Adjust wording of existing bullet points as specified in the suggestions
4. Add new \\item bullet points from the "New Bullet Points to Add" list

### What you CANNOT do (violations will be rejected):
1. Change company names (e.g., "Google", "Startup Inc")
2. Change date ranges (e.g., "2023--Present", "2021--2023")
3. Change job titles
4. Remove any existing \\item bullet points
5. Add new skills or technologies that are NOT in the suggested modifications
6. Modify the preamble (anything before \\begin{document})
7. Modify .cls or .sty files
8. Change section titles
9. Create entirely new entries out of nowhere

### New Bullet Points
If "New Bullet Points to Add" is provided, add them as \\item entries:
- If a target section is specified, add them to the end of the last \\begin{itemize} block in that section
- If no section specified, add to "Experience" section

### Output Format
Return a single JSON object:
```json
{
  "modified_files": {
    "path/to/file.tex": "complete modified file content"
  }
}
```

Include ONLY files that actually changed. Each value must be the COMPLETE file content, not just the changed parts.

Output ONLY the JSON object. No markdown, no commentary."""