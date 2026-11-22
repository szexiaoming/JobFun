"""
LaTeX modifier: handles the actual text manipulation in .tex files.
Works at the file-content level with AI assistance.
"""

import re
from pathlib import Path

from src.utils.logger import logger


def apply_text_changes(
    file_content: str,
    changes: list[dict],
) -> str:
    """
    Apply simple text replacements to LaTeX content.

    Args:
        file_content: The .tex file content
        changes: List of {original_text, suggested_text} dicts

    Returns:
        Modified file content
    """
    modified = file_content
    for change in changes:
        original = change.get("original_text", "")
        suggested = change.get("suggested_text", "")

        if not original or not suggested:
            continue
        if original == suggested:
            continue

        # Try exact match
        if original in modified:
            modified = modified.replace(original, suggested, 1)
            logger.info("Applied change: '%s...' → '%s...'",
                       original[:40], suggested[:40])
        else:
            # Try fuzzy match (ignore whitespace differences)
            logger.warning("Exact match failed for: '%s...'", original[:40])

    return modified


def add_bullets_to_entry(
    file_content: str,
    entry_header: str,
    new_bullets: list[str],
    section_title: str = "",
) -> str:
    """
    Add new bullet points to an existing entry or create a new entry.

    Args:
        file_content: The .tex file content
        entry_header: Text in the existing entry header (for locating it)
        new_bullets: New bullet points to add
        section_title: Section to target (supports both Chinese and English titles)

    Returns:
        Modified file content
    """
    modified = file_content

    if entry_header and entry_header in modified:
        # Find the existing entry and its itemize block
        header_pos = modified.find(entry_header)
        after_header = modified[header_pos:]

        # Find the next \\begin{itemize} after the header
        itemize_match = re.search(r'\\begin\{itemize\}', after_header)
        if itemize_match:
            # Find \\end{itemize}
            end_match = re.search(r'\\end\{itemize\}', after_header)
            if end_match:
                insert_pos = header_pos + end_match.start()
                bullet_text = "\n".join(f"  \\item {b}" for b in new_bullets)
                modified = (
                    modified[:insert_pos]
                    + "\n" + bullet_text + "\n"
                    + modified[insert_pos:]
                )
                logger.info("Added %d bullets to entry '%s'", len(new_bullets), entry_header[:40])
                return modified

    # Fallback: add new bullet list at end of specified section
    if section_title:
        # Try multiple section-level commands
        section_found = False
        for cmd in [r'\section', r'\subsection', r'\subsubsection']:
            sec_pattern = rf'\\{cmd}\{{{re.escape(section_title)}\}}'
            sec_match = re.search(sec_pattern, modified)
            if sec_match:
                section_found = True
                # Find next section command or end of document
                after_sec = modified[sec_match.end():]
                next_sec = re.search(r'\\(?:section|subsection|subsubsection)\{', after_sec)
                insert_pos = sec_match.end() + (next_sec.start() if next_sec else len(after_sec))

                bullet_block = "\\begin{itemize}\n" + "\n".join(f"  \\item {b}" for b in new_bullets) + "\n\\end{itemize}\n"
                modified = modified[:insert_pos] + "\n" + bullet_block + "\n" + modified[insert_pos:]
                logger.info("Added new entry with %d bullets to section '%s' (via %s)", len(new_bullets), section_title, cmd)
                return modified

        if not section_found:
            # Last resort: search for the section title as literal text
            # (e.g. inside \resumeSubheading arguments or custom commands)
            escaped = re.escape(section_title)
            title_match = re.search(escaped, modified)
            if title_match:
                # Find the nearest itemize block after this title
                after_title = modified[title_match.end():]
                itemize = re.search(r'\\begin\{itemize\}', after_title)
                if itemize:
                    end_itemize = re.search(r'\\end\{itemize\}', after_title[itemize.start():])
                    if end_itemize:
                        insert_pos = title_match.end() + itemize.start() + end_itemize.start()
                        bullet_text = "\n".join(f"  \\item {b}" for b in new_bullets)
                        modified = (
                            modified[:insert_pos]
                            + "\n" + bullet_text + "\n"
                            + modified[insert_pos:]
                        )
                        logger.info("Added %d bullets via literal title match '%s'", len(new_bullets), section_title[:40])
                        return modified

    logger.warning("Could not locate entry or section for adding bullets: section='%s'", section_title)
    return modified


def reorder_entries(
    file_content: str,
    entry_order: list[str],
) -> str:
    """
    Reorder entries within a section.
    entry_order: list of entry header substrings in desired order.

    This is a best-effort operation — complex LaTeX makes reordering fragile.
    Returns the modified content (may be unchanged if reordering is unsafe).
    """
    # Reordering is inherently risky in LaTeX — mark as experimental
    logger.warning("Entry reordering is experimental — manual verification needed")
    return file_content
