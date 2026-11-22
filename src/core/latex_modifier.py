"""
LaTeX modification orchestrator.
Takes user-approved suggestions → Git backup → AI edit → validate → diff.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from src.ai.client import AIClientError, get_ai_client
from src.ai.prompts.latex_edit import build_latex_edit_message
from src.latex.validator import ValidationResult, quick_check, validate_changes
from src.utils.diff_utils import generate_diff
from src.utils.file_utils import collect_tex_files
from src.utils.git_utils import GitError, commit, init_repo, revert_last
from src.utils.logger import logger


class LaTeXModifierError(Exception):
    """Raised when LaTeX modification fails."""


def modify_resume(
    resume_dir: Path,
    suggestions: list[dict],
    pending_additions: list[dict] = None,
    structured_resume: dict = None,
    jd_json: dict = None,
    dry_run: bool = False,
) -> dict:
    """
    Modify LaTeX resume based on accepted suggestions and pending additions.

    Process:
      1. Git commit (backup)
      2. Build AI prompt with suggestions + additions
      3. AI modifies .tex files
      4. Validate changes
      5. If validation fails → revert
      6. Generate diff
      7. Return results

    Args:
        resume_dir: Path to the resume LaTeX directory
        suggestions: List of accepted Suggestion objects or dicts
        pending_additions: List of {bullets, suggested_section} dicts from dialogue
        structured_resume: Original parsed resume structure
        jd_json: JD context for the AI
        dry_run: If True, only show what would change (no file writes)

    Returns:
        {
            "success": bool,
            "diff": str (unified diff),
            "commit_hash": str,
            "validation": ValidationResult,
            "modified_files": {filename: new_content},
            "error": str (if any)
        }
    """
    if not suggestions and not pending_additions:
        raise LaTeXModifierError("No suggestions or additions to apply")

    resume_dir = Path(resume_dir)
    if not resume_dir.exists():
        raise LaTeXModifierError(f"Resume directory not found: {resume_dir}")

    logger.info("Modifying resume: %s, suggestions=%d, additions=%d",
                resume_dir, len(suggestions), len(pending_additions or []))

    # ── Step 1: Git backup ──────────────────────────
    try:
        init_repo(resume_dir)
        backup_hash = commit(resume_dir, "backup: pre-modification snapshot")
    except GitError as e:
        raise LaTeXModifierError(f"Git backup failed: {e}") from e

    # ── Step 2: Read current files ──────────────────
    original_files = collect_tex_files(resume_dir)

    # ── Step 3: Apply modifications ─────────────────
    # Strategy: direct text replacement for wording/keyword changes,
    #   then AI for additions and unmatched changes.
    modified_files = _apply_modifications(
        original_files, suggestions, pending_additions,
        structured_resume, resume_dir,
    )

    if not modified_files:
        raise LaTeXModifierError("No modifications could be applied")

    # ── Step 4: Validate ────────────────────────────
    validation = validate_changes(
        original_files, modified_files, structured_resume or {}
    )

    if not validation.passed:
        logger.error("Validation failed, reverting...")
        try:
            revert_last(resume_dir)
        except GitError:
            pass

        return {
            "success": False,
            "diff": "",
            "commit_hash": backup_hash,
            "validation": validation,
            "modified_files": {},
            "error": f"Safety validation failed: {'; '.join(validation.violations)}",
        }

    # ── Step 5: Write files (unless dry run) ────────
    if not dry_run:
        for filename, content in modified_files.items():
            file_path = resume_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            logger.info("Written: %s", filename)

        # Commit after modification
        mod_hash = commit(
            resume_dir,
            f"modify: {len(suggestions)} suggestions + {len(pending_additions or [])} additions"
        )
    else:
        mod_hash = "dry-run"

    # ── Step 6: Generate diff ───────────────────────
    full_diff = ""
    for filename in sorted(set(list(original_files.keys()) + list(modified_files.keys()))):
        orig = original_files.get(filename, "")
        mod = modified_files.get(filename, "")
        if orig != mod:
            full_diff += generate_diff(orig, mod, filename) + "\n"

    logger.info("Modification complete: %d files changed", len(modified_files))

    return {
        "success": True,
        "diff": full_diff,
        "commit_hash": mod_hash,
        "backup_hash": backup_hash,
        "validation": validation,
        "modified_files": modified_files,
        "error": "",
    }


def rollback_modification(resume_dir: Path) -> str:
    """Rollback the last modification."""
    try:
        return revert_last(resume_dir)
    except GitError as e:
        raise LaTeXModifierError(f"Rollback failed: {e}") from e


def get_modification_history(resume_dir: Path) -> list[dict]:
    """Get modification history from Git."""
    from src.utils.git_utils import get_history
    return get_history(resume_dir)


def _apply_modifications(
    original_files: dict[str, str],
    suggestions: list[dict],
    pending_additions: list[dict],
    structured_resume: dict,
    resume_dir: Path,
) -> dict[str, str]:
    """
    Apply modifications to LaTeX files.
    Strategy:
      1. Direct text replacement for wording/keyword suggestions
      2. Direct bullet addition for pending_additions
      3. AI fallback for unmatched/changes that couldn't be applied directly
    """
    from src.latex.modifier import add_bullets_to_entry, apply_text_changes

    modified = dict(original_files)
    applied = 0
    unmatched = []

    # Step 1: Direct text replacement for wording/keyword changes
    for s in _normalize_suggestions(suggestions):
        original = s.get("original_text", "")
        suggested = s.get("suggested_text", "")
        if not original or not suggested or original == suggested:
            continue

        # Try to find and replace in each tex file
        found = False
        for fname in list(modified.keys()):
            if fname.endswith(".tex") and original in modified[fname]:
                modified[fname] = modified[fname].replace(original, suggested, 1)
                found = True
                applied += 1
                logger.info("Direct replace in %s: '%s...'", fname, original[:40])
                break

        if not found:
            unmatched.append(s)

    # Step 2: Add new bullets from dialogue
    if pending_additions:
        for add in pending_additions:
            bullets = add.get("bullets", [])
            section = add.get("suggested_section", "Experience")
            if bullets:
                # Try each tex file — add_bullets_to_entry will handle flexible matching
                applied_this = False
                for fname, content in modified.items():
                    if not fname.endswith(".tex"):
                        continue
                    result = add_bullets_to_entry(
                        content, "", bullets, section
                    )
                    if result != content:
                        modified[fname] = result
                        applied += 1
                        applied_this = True
                        break
                if not applied_this:
                    logger.warning(
                        "Could not add bullets for skill '%s' to section '%s'",
                        add.get("missing_skill", "?"), section,
                    )

    # Step 3: AI fallback for unmatched suggestions
    if unmatched:
        logger.info("%d suggestions unmatched, trying AI modification...", len(unmatched))
        try:
            ai_modified = _ai_modify_fallback(
                modified, unmatched, structured_resume
            )
            if ai_modified:
                modified = ai_modified
                applied += len(unmatched)
        except Exception as e:
            logger.warning("AI modification fallback failed: %s", e)

    logger.info("Modifications applied: %d direct, %d unmatched → AI",
                applied - (len(unmatched) if unmatched else 0),
                len(unmatched))

    return modified


def _ai_modify_fallback(
    tex_files: dict[str, str],
    unmatched_suggestions: list[dict],
    structured_resume: dict = None,
) -> dict[str, str]:
    """AI fallback for modifications that couldn't be applied directly."""
    import json
    client = get_ai_client()

    message = build_latex_edit_message(
        original_files=json.dumps(
            {k: v for k, v in tex_files.items() if k.endswith(".tex")},
            ensure_ascii=False, indent=2,
        ),
        suggestions=json.dumps(unmatched_suggestions, ensure_ascii=False, indent=2),
        additions="[]",
        jd_context="",
    )

    from config import get_active_model

    raw = client._call(
        model=get_active_model("structured"),
        system=message["system"],
        user_text=message["user"],
        temperature=0.2,
        max_tokens=4096,
    )

    if isinstance(raw, dict):
        # Try modified_files key first
        if "modified_files" in raw:
            return {**tex_files, **raw["modified_files"]}
        # Try direct filename keys
        tex_keys = [k for k in raw if k.endswith(".tex")]
        if tex_keys:
            return {**tex_files, **{k: raw[k] for k in tex_keys}}

    return {}


def _normalize_suggestions(suggestions: list) -> list[dict]:
    """Normalize suggestions to dict format."""
    result = []
    for s in suggestions:
        if hasattr(s, "__dataclass_fields__"):
            result.append({
                "category": s.category,
                "original_text": s.original_text,
                "suggested_text": s.suggested_text,
                "rationale": s.rationale,
            })
        elif isinstance(s, dict):
            result.append(s)
    return result
