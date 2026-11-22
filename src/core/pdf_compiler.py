"""
PDF Compiler orchestrator: compile LaTeX → if fail → AI fix → recompile.
"""

from pathlib import Path
from typing import Optional

from config import get_active_model
from src.ai.client import AIClientError, get_ai_client
from src.latex.compiler import (
    CompilerError,
    check_compiler,
    compile_to_pdf,
    get_install_instructions,
)
from src.latex.error_parser import format_for_ai, parse_compile_log
from src.utils.file_utils import collect_tex_files
from src.utils.logger import logger


class PDFCompilerError(Exception):
    """Raised when PDF generation ultimately fails."""


def generate_pdf(
    tex_dir: Path,
    main_file: str = "",
    output_dir: Optional[Path] = None,
    auto_fix: bool = True,
    max_fix_attempts: int = 2,
) -> dict:
    """
    Generate PDF from LaTeX source, with optional AI auto-fix.

    Args:
        tex_dir: Directory containing LaTeX project
        main_file: Main .tex filename
        output_dir: Where to write PDF
        auto_fix: Try to fix errors with AI
        max_fix_attempts: Maximum AI fix retries

    Returns:
        {
            "success": bool,
            "pdf_path": Path or None,
            "compiler_available": bool,
            "attempts": int (number of compile attempts),
            "error": str or None,
        }
    """
    tex_dir = Path(tex_dir).resolve()

    # Check compiler availability
    compilers = check_compiler()
    has_compiler = compilers["pdflatex"] or compilers["xelatex"]
    if not has_compiler:
        return {
            "success": False,
            "pdf_path": None,
            "compiler_available": False,
            "attempts": 0,
            "error": (
                "LaTeX compiler not found.\n"
                + get_install_instructions()
            ),
        }

    attempt = 0

    while attempt <= max_fix_attempts:
        attempt += 1

        try:
            pdf_path = compile_to_pdf(
                tex_dir=tex_dir,
                main_file=main_file,
                output_dir=output_dir,
            )

            if attempt > 1:
                logger.info("PDF generated after %d fix attempt(s)", attempt - 1)

            return {
                "success": True,
                "pdf_path": pdf_path,
                "compiler_available": True,
                "attempts": attempt,
                "error": None,
            }

        except CompilerError as e:
            error_msg = str(e)
            logger.warning("Compilation attempt %d failed: %s", attempt, error_msg[:100])

            if not auto_fix or attempt > max_fix_attempts:
                return {
                    "success": False,
                    "pdf_path": None,
                    "compiler_available": True,
                    "attempts": attempt,
                    "error": error_msg,
                }

            # Try AI fix
            logger.info("Attempting AI fix (attempt %d)...", attempt)
            try:
                fixed = _ai_fix_errors(tex_dir, error_msg)
                if not fixed:
                    logger.warning("AI fix returned no changes")
                    continue
                logger.info("AI fix applied, retrying compilation...")
            except Exception as fix_err:
                logger.warning("AI fix failed: %s", fix_err)
                # Continue to next attempt anyway

    return {
        "success": False,
        "pdf_path": None,
        "compiler_available": True,
        "attempts": attempt,
        "error": "Max fix attempts exceeded",
    }


def generate_pdf_safe(
    tex_dir: Path,
    main_file: str = "main.tex",
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Safe PDF generation: compile, no auto-fix.
    Falls back gracefully if compiler is missing.
    """
    return generate_pdf(
        tex_dir=tex_dir,
        main_file=main_file,
        output_dir=output_dir,
        auto_fix=False,
    )


def _ai_fix_errors(tex_dir: Path, compile_error: str) -> bool:
    """
    Use AI to fix LaTeX compilation errors.
    Returns True if fixes were applied.
    """
    from src.ai.prompts.latex_fix import SYSTEM_LATEX_FIX

    tex_files = collect_tex_files(tex_dir)

    # Parse errors for structured info
    errors = parse_compile_log(compile_error, "")
    formatted = format_for_ai(errors, tex_files)

    client = get_ai_client()
    raw = client._call(
        model=get_active_model("structured"),
        system=SYSTEM_LATEX_FIX,
        user_text=formatted,
        temperature=0.1,
    )

    modified = raw.get("modified_files", {})
    if not modified:
        return False

    # Write fixed files
    for fname, content in modified.items():
        fpath = tex_dir / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        logger.info("AI-fixed: %s", fname)

    return True
