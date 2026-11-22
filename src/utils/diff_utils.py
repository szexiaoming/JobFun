"""
Unified diff generation for showing LaTeX changes.
"""

import difflib
from pathlib import Path


def generate_diff(original: str, modified: str, filename: str = "resume.tex") -> str:
    """
    Generate a unified diff string between original and modified text.
    """
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    )
    return "".join(diff)


def generate_file_diff(orig_path: Path, mod_path: Path) -> str:
    """Generate diff between two files."""
    orig = orig_path.read_text(encoding="utf-8", errors="ignore")
    mod = mod_path.read_text(encoding="utf-8", errors="ignore")
    return generate_diff(orig, mod, orig_path.name)


def diff_stats(original: str, modified: str) -> dict:
    """Count additions, deletions, and unchanged lines."""
    orig_lines = original.splitlines()
    mod_lines = modified.splitlines()

    differ = list(difflib.Differ().compare(orig_lines, mod_lines))
    added = sum(1 for d in differ if d.startswith("+ "))
    removed = sum(1 for d in differ if d.startswith("- "))
    unchanged = sum(1 for d in differ if d.startswith("  "))

    return {
        "lines_added": added,
        "lines_removed": removed,
        "lines_unchanged": unchanged,
        "total_changes": added + removed,
    }
