"""
Parse LaTeX compilation errors into structured form for AI fixing.
"""

import re
from dataclasses import dataclass, field


@dataclass
class LaTeXError:
    file: str = ""
    line: int = 0
    message: str = ""
    context: str = ""
    error_type: str = "unknown"  # undefined_cmd, missing_env, syntax, etc.


def parse_compile_log(stdout: str, stderr: str) -> list[LaTeXError]:
    """
    Parse LaTeX compilation output into structured errors.

    Handles common error patterns:
      ! Undefined control sequence.
      ! Missing \begin{document}.
      ! LaTeX Error: ...
      l.123 ...context line...
    """
    errors = []
    combined = (stdout or "") + "\n" + (stderr or "")
    lines = combined.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]

        # Error line starts with "!"
        if line.startswith("!"):
            err = LaTeXError()
            err.message = line[1:].strip()

            # Classify error type
            msg_lower = err.message.lower()
            if "undefined control sequence" in msg_lower:
                err.error_type = "undefined_cmd"
            elif "missing" in msg_lower and r"\begin{document}" in msg_lower:
                err.error_type = "missing_document"
            elif "missing" in msg_lower:
                err.error_type = "missing_env"
            elif "file" in msg_lower and "not found" in msg_lower:
                err.error_type = "missing_file"
            elif "environment" in msg_lower:
                err.error_type = "env_mismatch"
            elif "runaway" in msg_lower:
                err.error_type = "runaway_arg"

            # Next lines may contain context (l.123)
            for j in range(i + 1, min(i + 5, len(lines))):
                ctx = lines[j]
                # File and line: "l.123" or "(file.tex" pattern
                file_match = re.search(r'\(([^)]+\.tex)', ctx)
                if file_match:
                    err.file = file_match.group(1)
                line_match = re.search(r'l\.(\d+)', ctx)
                if line_match:
                    err.line = int(line_match.group(1))
                if ctx.strip() and not ctx.startswith("?"):
                    if not err.context:
                        err.context = ctx.strip()

            errors.append(err)
            i += 1
        else:
            i += 1

    return errors


def format_for_ai(errors: list[LaTeXError], tex_files: dict[str, str]) -> str:
    """
    Format parsed errors + source files into a prompt-friendly string
    that an AI can use to fix the LaTeX.
    """
    parts = []

    parts.append("## Compilation Errors Found\n")
    for e in errors:
        parts.append(f"- **{e.error_type}** (line {e.line} in {e.file}): {e.message}")
        if e.context:
            parts.append(f"  Context: `{e.context}`")
    parts.append("")

    if errors:
        parts.append("## Relevant Files\n")
        for fname, content in tex_files.items():
            if fname.endswith(".tex"):
                parts.append(f"### {fname}")
                parts.append("```latex")
                parts.append(content)
                parts.append("```")
                parts.append("")

    parts.append(
        "Fix ALL compilation errors while preserving the document's content and structure. "
        "Return a JSON object: {\"modified_files\": {\"filename.tex\": \"fixed content\"}}"
    )

    return "\n".join(parts)
