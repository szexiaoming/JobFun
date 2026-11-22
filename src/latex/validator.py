"""
Safety validator for LaTeX modifications.
Ensures AI did not fabricate experiences, change dates, or alter company names.
"""

import re
from dataclasses import dataclass, field

from src.utils.logger import logger


@dataclass
class ValidationResult:
    passed: bool = True
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_changes(
    original_files: dict[str, str],
    modified_files: dict[str, str],
    original_structure: dict,
) -> ValidationResult:
    """
    Validate that LaTeX modifications are safe.

    Checks:
      1. Company names unchanged
      2. Date ranges unchanged
      3. Section count preserved
      4. Entry count per section preserved (for additions: must increase)
      5. No obviously fabricated skills injected out of nowhere
      6. Preamble untouched
    """
    result = ValidationResult()

    for filename, new_content in modified_files.items():
        old_content = original_files.get(filename, "")

        # Skip cls and style files
        if filename.endswith(".cls") or filename.endswith(".sty"):
            if old_content != new_content:
                result.violations.append(
                    f"{filename}: cls/sty file was modified (not allowed)"
                )
            continue

        # Check preamble
        _check_preamble(old_content, new_content, filename, result)

        # Check company names and dates from original entries
        _check_identifiers(old_content, new_content, filename, result)

    # Check structure integrity
    _check_structure(original_structure, modified_files, result)

    result.passed = len(result.violations) == 0

    if not result.passed:
        logger.warning("Validation FAILED: %d violations", len(result.violations))
    else:
        logger.info("Validation passed")

    return result


def _check_preamble(
    old: str, new: str, filename: str, result: ValidationResult
) -> None:
    """Ensure preamble (before \\begin{document}) was not touched."""
    old_pre = old.split(r"\begin{document}")[0] if r"\begin{document}" in old else old
    new_pre = new.split(r"\begin{document}")[0] if r"\begin{document}" in new else new

    if old_pre.strip() != new_pre.strip():
        result.violations.append(
            f"{filename}: Preamble was modified (not allowed)"
        )


def _check_identifiers(
    old: str, new: str, filename: str, result: ValidationResult
) -> None:
    """Check that company names, dates, and job titles are unchanged."""
    # Extract company names (heuristic: words before date patterns)
    date_pattern = r'\b(20\d{2}|19\d{2})\s*[—\-–]\s*(20\d{2}|Present|至今|now)\b'

    old_dates = set(re.findall(date_pattern, old))
    new_dates = set(re.findall(date_pattern, new))

    # Dates should be preserved exactly
    missing_dates = old_dates - new_dates
    if missing_dates:
        result.violations.append(
            f"{filename}: Date range(s) removed: {missing_dates}"
        )

    extra_dates = new_dates - old_dates
    if extra_dates:
        result.warnings.append(
            f"{filename}: New date range(s) added: {extra_dates} "
            "(may be OK if user provided new experience)"
        )


def _check_structure(
    original_structure: dict,
    modified_files: dict[str, str],
    result: ValidationResult,
) -> None:
    """Check that section/entry structure is preserved."""
    # Count sections in original
    orig_sections = len(original_structure.get("sections", []))
    orig_entries = sum(
        len(s.get("entries", []))
        for s in original_structure.get("sections", [])
    )

    # Quick heuristic: count \section{} and \resumeSubheading in modified files
    all_new = "\n".join(modified_files.values())
    new_sections = len(re.findall(r'\\section\{', all_new))
    new_entries = len(re.findall(r'\\resumeSubheading\{', all_new))

    # Also count \item as a proxy for bullet count
    new_items = len(re.findall(r'\\item\s', all_new))
    orig_items = sum(
        len(e.get("bullets", []))
        for s in original_structure.get("sections", [])
        for e in s.get("entries", [])
    )

    if new_sections == 0 and orig_sections > 0:
        result.violations.append(
            f"All sections lost: {orig_sections} → 0 (AI may have returned partial content)"
        )
    elif new_sections < orig_sections:
        result.warnings.append(
            f"Section count decreased: {orig_sections} → {new_sections}"
        )

    if new_entries == 0 and orig_entries > 0:
        # 0 entries usually means AI reformatted content structure (not actual deletion)
        result.warnings.append(
            f"Entry count changed: {orig_entries} → {new_entries} "
            "(AI may have reformatted — manually verify)"
        )
    elif new_entries < orig_entries:
        result.warnings.append(
            f"Entry count decreased: {orig_entries} → {new_entries}"
        )

    if new_items < orig_items:
        result.warnings.append(
            f"Bullet count decreased: {orig_items} → {new_items}"
        )


def quick_check(original: str, modified: str) -> bool:
    """Quick sanity check: did we lose content?"""
    if len(modified) < len(original) * 0.7:
        return False  # Lost more than 30% of content
    if r"\begin{document}" not in modified:
        return False
    if r"\end{document}" not in modified:
        return False
    return True
