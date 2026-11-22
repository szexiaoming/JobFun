"""
LaTeX compiler: wraps pdflatex/xelatex for PDF generation.
Auto-detects Chinese characters and switches to xelatex.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.utils.logger import logger


class CompilerError(Exception):
    """Raised when LaTeX compilation fails."""


def compile_to_pdf(
    tex_dir: Path,
    main_file: str = "",
    output_dir: Optional[Path] = None,
    timeout: int = 60,
) -> Path:
    """
    Compile a LaTeX project to PDF.

    Args:
        tex_dir: Directory containing the LaTeX project
        main_file: Main .tex filename (auto-detected if empty)
        output_dir: Where to write the PDF (default: tex_dir)
        timeout: Compilation timeout in seconds

    Returns:
        Path to the generated PDF file

    Raises:
        CompilerError: If compilation fails
    """
    tex_dir = Path(tex_dir).resolve()

    # Auto-detect main file if not specified
    if not main_file:
        main_path = _find_main_tex(tex_dir)
    else:
        main_path = tex_dir / main_file
        if not main_path.exists():
            # Fallback to auto-detect
            main_path = _find_main_tex(tex_dir)
            logger.info("main_file '%s' not found, auto-detected: %s", main_file, main_path.name)

    main_file = main_path.name

    output_dir = Path(output_dir or tex_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Detect if we need xelatex (Chinese characters)
    use_xelatex = _needs_xelatex(main_path, tex_dir)
    engine = "xelatex" if use_xelatex else "pdflatex"
    logger.info("Compiling with %s: %s", engine, main_path)

    # Run compilation (twice for references)
    for run in (1, 2):
        try:
            result = subprocess.run(
                [
                    engine,
                    "-interaction=nonstopmode",
                    "-output-directory", str(output_dir),
                    main_path.name,
                ],
                cwd=str(tex_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise CompilerError(
                f"{engine} compilation timed out after {timeout}s"
            )

        if run == 1 and result.returncode != 0:
            # On first run, non-zero can be "Rerun to get references"
            # Only fail if it's a hard error
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            if _is_hard_error(stdout + stderr):
                raise CompilerError(
                    _extract_error_message(stdout, stderr, engine)
                )

    # Find the generated PDF
    pdf_path = output_dir / main_path.with_suffix(".pdf").name
    if not pdf_path.exists():
        # Search for any .pdf in output
        pdfs = list(output_dir.glob("*.pdf"))
        if pdfs:
            pdf_path = pdfs[0]
        else:
            raise CompilerError(
                f"PDF not generated. {engine} output:\n"
                + (result.stdout[-500:] if result.stdout else "No output")
            )

    # Detect page count from log output
    pages = _detect_page_count(result.stdout if run == 2 else "")

    logger.info("PDF generated: %s (%.1f KB, %d page%s)",
                pdf_path.name, pdf_path.stat().st_size / 1024,
                pages, "s" if pages != 1 else "")
    return pdf_path


def check_compiler() -> dict:
    """Check which LaTeX compilers are available."""
    result = {"pdflatex": False, "xelatex": False}

    for engine in ("pdflatex", "xelatex"):
        try:
            subprocess.run(
                [engine, "--version"],
                capture_output=True, timeout=5,
            )
            result[engine] = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return result


def get_install_instructions() -> str:
    """Return OS-appropriate LaTeX installation instructions."""
    import platform
    system = platform.system()
    if system == "Windows":
        return (
            "请安装 MiKTeX：https://miktex.org/download\n"
            "安装后确保 pdflatex 在 PATH 中"
        )
    elif system == "Darwin":
        return "brew install --cask mactex"
    else:
        return "sudo apt-get install texlive-latex-base texlive-xetex"


# ── Helpers ──────────────────────────────────────────

def _find_main_tex(base_dir: Path) -> Path:
    """
    Auto-detect the main .tex file in a LaTeX project.
    Checks: main.tex, any .tex with \\documentclass, or the only .tex file.
    """
    # Direct match
    main = base_dir / "main.tex"
    if main.exists():
        return main

    # Search for .tex containing \documentclass
    for tex in base_dir.rglob("*.tex"):
        try:
            content = tex.read_text(encoding="utf-8", errors="ignore")
            if r"\documentclass" in content:
                return tex
        except Exception:
            pass

    # Fallback: any .tex file
    tex_files = list(base_dir.rglob("*.tex"))
    if tex_files:
        return tex_files[0]

    raise CompilerError(f"No .tex file found in {base_dir}")


def get_page_count(pdf_path: Path) -> int:
    """Read page count from a PDF file (simple header parsing)."""
    try:
        with open(pdf_path, "rb") as f:
            content = f.read().decode("latin-1", errors="ignore")
        # Count PDF page objects: /Type /Page (not /Pages)
        import re
        return len(re.findall(r'/Type\s*/Page[^s]', content))
    except Exception:
        return 0


def _detect_page_count(stdout: str) -> int:
    """Detect page count from LaTeX output (e.g. [1] [2])."""
    import re
    pages = re.findall(r'\[(\d+)\]', stdout)
    if pages:
        return int(pages[-1])
    return 1


def _needs_xelatex(main_path: Path, tex_dir: Path) -> bool:
    """Check if the document contains Chinese characters (needs xelatex)."""
    chinese_pattern = re.compile(r'[一-鿿㐀-䶿]')
    for tex_file in tex_dir.rglob("*.tex"):
        try:
            content = tex_file.read_text(encoding="utf-8", errors="ignore")
            if chinese_pattern.search(content):
                return True
        except Exception:
            pass
    return False


def _is_hard_error(output: str) -> bool:
    """Check if the LaTeX output indicates a hard error vs. warnings."""
    # "Emergency stop" indicates a hard error
    if "Emergency stop" in output:
        return True
    # Missing \begin{document} is hard
    if "Missing \\begin{document}" in output:
        return True
    # Undefined control sequence is usually hard
    undef_count = output.count("Undefined control sequence")
    if undef_count > 0:
        return True
    return False


def _extract_error_message(stdout: str, stderr: str, engine: str) -> str:
    """Extract the most useful error line from LaTeX output."""
    lines = (stdout + "\n" + stderr).split("\n")
    errors = []

    for i, line in enumerate(lines):
        if line.startswith("!"):
            errors.append(line)
            # Also capture the next line (context)
            if i + 1 < len(lines):
                errors.append(lines[i + 1])

    if errors:
        return f"{engine} compilation failed:\n" + "\n".join(errors[:10])
    return f"{engine} compilation failed (unknown error)"
