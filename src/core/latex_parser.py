"""
LaTeX resume parser. Extracts structured sections/entries/bullets from .tex files.

Handles common Overleaf resume patterns:
  - \\input{sections/...} references
  - \\section, \\subsection for structure
  - \\begin{itemize} \\item ... \\end{itemize} for bullets
  - Custom environments like \\resumeSubheading, \\resumeItem, etc.
"""

import re
from pathlib import Path
from typing import Optional

from config import RESUME_DIR
from src.utils.file_utils import FileError, collect_tex_files, extract_zip, find_main_tex
from src.utils.logger import logger


class LaTeXParserError(Exception):
    """Raised when LaTeX parsing fails."""


# ── Public API ──────────────────────────────────────

def parse_resume_text(text: str, *, client=None) -> dict:
    """
    Parse a plain-text resume into structured JSON via AI extraction.
    Returns the same schema as parse_tex_files so the match engine works identically.
    Does NOT create a LaTeX directory — latex_path will be empty for text resumes.
    """
    from src.ai.client import AIClientError, get_ai_client

    if not text.strip():
        raise LaTeXParserError("Resume text is empty")

    try:
        parser_client = client or get_ai_client()
        structured = parser_client.extract_resume_from_text(text.strip())
    except AIClientError as e:
        raise LaTeXParserError(f"AI resume extraction failed: {e}") from e

    # Ensure minimum schema compliance
    if "preamble" not in structured:
        structured["preamble"] = {"packages": [], "custom_commands": []}
    if "sections" not in structured:
        structured["sections"] = []
    if "files" not in structured:
        structured["files"] = []

    logger.info(
        "Parsed text resume: %d sections found",
        len(structured.get("sections", [])),
    )
    return structured


def parse_resume_zip(zip_path: Path, resume_name: str) -> tuple[Path, dict]:
    """
    Extract and parse a resume zip file.
    Returns (extracted_dir, structured_resume_dict).
    """
    # Create a unique directory for this resume
    import uuid
    resume_dir = RESUME_DIR / str(uuid.uuid4())[:8]
    resume_dir.mkdir(parents=True, exist_ok=True)

    try:
        extract_zip(zip_path, resume_dir)
    except FileError as e:
        raise LaTeXParserError(f"Failed to extract zip: {e}") from e

    try:
        main_tex = find_main_tex(resume_dir)
        all_files = collect_tex_files(resume_dir)
        structured = parse_tex_files(main_tex, all_files, resume_dir)
    except FileError as e:
        raise LaTeXParserError(f"Failed to parse LaTeX: {e}") from e

    logger.info("Parsed resume: %d sections found", len(structured.get("sections", [])))
    return resume_dir, structured


def parse_tex_files(
    main_tex_path: Path,
    tex_files: dict[str, str],
    base_dir: Path,
) -> dict:
    """
    Parse a LaTeX resume project into structured JSON.

    Args:
        main_tex_path: Path to the main .tex file
        tex_files: {relative_path: content} of all .tex/.cls files
        base_dir: Root directory of the LaTeX project

    Returns:
        {
            "preamble": {"packages": [...], "custom_commands": [...]},
            "sections": [
                {
                    "title": "Experience",
                    "entries": [
                        {
                            "header": "Software Engineer @ Google, 2023-Present",
                            "bullets": ["bullet 1", "bullet 2"]
                        }
                    ]
                }
            ]
        }
    """
    main_content = tex_files.get(main_tex_path.name, "")
    if not main_content:
        main_content = main_tex_path.read_text(encoding="utf-8", errors="ignore")

    # Resolve all \input{} references to build a unified document view
    full_content = _resolve_inputs(main_content, tex_files, base_dir)

    # Extract preamble
    preamble = _extract_preamble(full_content)

    # Extract document body
    body = _extract_body(full_content)

    # Parse sections from body
    sections = _parse_sections(body)

    return {
        "preamble": preamble,
        "sections": sections,
        "files": list(tex_files.keys()),
    }


# ── Input resolution ────────────────────────────────

def _resolve_inputs(content: str, tex_files: dict[str, str], base_dir: Path) -> str:
    """
    Recursively resolve \\input{...} and \\include{...} commands.
    Replaces them with the contents of the referenced file.
    """
    # Pattern matches: \input{sections/experience} or \input{sections/experience.tex}
    pattern = r'\\(?:input|include)\{([^}]+)\}'

    def _replace_input(match):
        filename = match.group(1)
        if not filename.endswith(".tex"):
            filename += ".tex"

        # Try to find the file in tex_files
        for key, val in tex_files.items():
            if key.endswith(filename) or key == filename:
                inner = _resolve_inputs(val, tex_files, base_dir)
                return f"\n% === Begin {filename} ===\n{inner}\n% === End {filename} ===\n"

        logger.warning("Input file not found: %s", filename)
        return match.group(0)

    # Iterate until no more inputs (handle nested inputs)
    prev = None
    while prev != content:
        prev = content
        content = re.sub(pattern, _replace_input, content)

    return content


# ── Preamble extraction ─────────────────────────────

def _extract_preamble(content: str) -> dict:
    """Extract preamble: everything before \\begin{document}."""
    doc_match = re.search(r'\\begin\{document\}', content)
    preamble_text = content[:doc_match.start()] if doc_match else ""

    packages = re.findall(r'\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}', preamble_text)
    custom_commands = re.findall(
        r'\\(?:newcommand|renewcommand|def)\{[^}]*\}',
        preamble_text,
    )

    return {
        "packages": packages,
        "custom_commands": custom_commands,
    }


def _extract_body(content: str) -> str:
    """Extract everything between \\begin{document} and \\end{document}."""
    doc_match = re.search(r'\\begin\{document\}', content)
    end_match = re.search(r'\\end\{document\}', content)
    if not doc_match:
        return content
    start = doc_match.end()
    end = end_match.start() if end_match else len(content)
    return content[start:end]


# ── Section parsing ─────────────────────────────────

def _parse_sections(body: str) -> list[dict]:
    """
    Parse document body into sections.
    Supports: \\section{}, \\subsection{}, and section-like environments.
    """
    sections = []

    # Split by \section{Title} commands
    # Find all section headers and their positions
    sec_pattern = r'\\(?:section|subsection)\{([^}]*)\}'
    sec_matches = list(re.finditer(sec_pattern, body))

    for i, match in enumerate(sec_matches):
        title = match.group(1).strip()
        start = match.end()
        end = sec_matches[i + 1].start() if i + 1 < len(sec_matches) else len(body)
        section_body = body[start:end]

        entries = _parse_entries(section_body)
        if entries:
            sections.append({
                "title": title,
                "entries": entries,
            })

    # Handle implicit sections (content before first section header)
    if not sections:
        entries = _parse_entries(body)
        if entries:
            sections.append({
                "title": "Main",
                "entries": entries,
            })

    return sections


# ── Entry parsing ───────────────────────────────────

def _parse_entries(section_body: str) -> list[dict]:
    """
    Parse entries within a section.
    Entries can be:
      - \\resumeSubheading{...}{...}{...}{...} style (common in Overleaf templates)
      - Paragraph-based entries with bullet lists
      - Simple text blocks
    """
    entries = []

    # Pattern 1: Overleaf-style resume entries
    # \resumeSubheading{Company}{Date}{Role}{Location}
    subheading_pattern = r'\\(?:resumeSubheading|cventry|resumeExperience)\{([^}]*(?:\{[^}]*\}[^}]*)*)\}'
    # Simpler: capture \\resumeSubheading{...}{...}{...}{...} blocks
    sh_matches = list(re.finditer(
        r'\\(resumeSubheading|cventry)\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}',
        section_body,
    ))

    for i, match in enumerate(sh_matches):
        cmd = match.group(1)
        # Build header from the 4 args
        args = [match.group(j).strip() for j in range(2, 6)]
        header = f"{args[0]} — {args[2]}" if args[0] and args[2] else " ".join(a for a in args if a)

        # Find following bullets
        start = match.end()
        end = sh_matches[i + 1].start() if i + 1 < len(sh_matches) else len(section_body)
        block = section_body[start:end]

        bullets = _extract_bullets(block)
        entries.append({
            "header": header,
            "bullets": bullets,
        })

    # Pattern 2: If no subheading matches found, look for itemize blocks
    if not entries:
        # Find all \begin{itemize}...\end{itemize} blocks
        itemize_pattern = r'\\begin\{itemize\}(.*?)\\end\{itemize\}'
        for match in re.finditer(itemize_pattern, section_body, re.DOTALL):
            bullets = _extract_bullets(match.group(0))
            if bullets:
                entries.append({
                    "header": "",
                    "bullets": bullets,
                })

    # Pattern 3: Simple \item[]... or bullet-like paragraphs
    if not entries:
        bullets = _extract_bullets(section_body)
        if bullets:
            entries.append({
                "header": "",
                "bullets": bullets,
            })

    return entries


# ── Bullet extraction ───────────────────────────────

def _extract_bullets(text: str) -> list[str]:
    """
    Extract bullet points from text.
    Handles: \\item, \\resumeItem{...}, \\resumeItemListStart/End blocks.
    """
    bullets = []

    # \resumeItem{content}
    for match in re.finditer(r'\\resumeItem\{((?:[^{}]|\{[^{}]*\})*)\}', text):
        bullets.append(match.group(1).strip())

    # \item[optional] content (the standard LaTeX item)
    if not bullets:
        for match in re.finditer(r'\\item(?:\[[^\]]*\])?\s*(.*?)(?=\\item|\\end|$)', text, re.DOTALL):
            content = match.group(1).strip()
            if content and not content.startswith("\\begin"):
                bullets.append(content)

    # Simple bullet-like content (non-command lines that have substance)
    if not bullets:
        lines = text.strip().split("\n")
        for line in lines:
            clean = line.strip()
            # Skip commands, empty lines, comment-only lines
            if clean and not clean.startswith("\\") and not clean.startswith("%"):
                if len(clean) > 10:  # Minimum length for a meaningful bullet
                    bullets.append(clean)

    return bullets
