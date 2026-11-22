"""Stable source identifiers for structured resume sections and bullets."""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Optional


def assign_source_ids(
    resume_json: dict,
    previous_resume_json: Optional[dict] = None,
) -> dict:
    """Return a copy of a resume with stable source IDs attached.

    Exact title/header/text matches retain their previous IDs. When wording is
    edited, the source at the same structural index inherits the previous ID.
    This gives version reconciliation a deterministic fallback without changing
    the user's resume content.
    """
    current = copy.deepcopy(resume_json) if isinstance(resume_json, dict) else {}
    previous = (
        copy.deepcopy(previous_resume_json)
        if isinstance(previous_resume_json, dict)
        else {}
    )

    current_sections = current.get("sections", [])
    previous_sections = previous.get("sections", [])
    if not isinstance(current_sections, list):
        current_sections = []
        current["sections"] = current_sections
    if not isinstance(previous_sections, list):
        previous_sections = []

    section_matches = _reconcile_nodes(current_sections, previous_sections, "title")
    duplicate_counts: dict[str, int] = {}
    for section_index, section in enumerate(current_sections):
        if not isinstance(section, dict):
            continue
        previous_index = section_matches.get(section_index)
        previous_section = (
            previous_sections[previous_index]
            if previous_index is not None
            else None
        )
        normalized_title = _normalized(section.get("title", ""))
        duplicate_index = duplicate_counts.get(normalized_title, 0)
        duplicate_counts[normalized_title] = duplicate_index + 1

        section_id = _existing_or_new_id(
            _preferred_id_source(previous_section, section),
            "source_id",
            "section",
            normalized_title,
            str(duplicate_index),
        )
        section["source_id"] = section_id
        _assign_entry_ids(section, previous_section or {}, section_id)

    return current


def find_source_by_id(resume_json: dict, source_id: str) -> Optional[dict]:
    """Find a section, entry, or bullet by source ID."""
    for section in resume_json.get("sections", []):
        if not isinstance(section, dict):
            continue
        if section.get("source_id") == source_id:
            return {"kind": "section", "node": section}
        for entry in section.get("entries", []):
            if not isinstance(entry, dict):
                continue
            if entry.get("source_id") == source_id:
                return {"kind": "entry", "section": section, "node": entry}
            for index, bullet in enumerate(entry.get("bullets", [])):
                if isinstance(bullet, dict) and bullet.get("source_id") == source_id:
                    return {
                        "kind": "bullet",
                        "section": section,
                        "entry": entry,
                        "index": index,
                        "node": bullet,
                    }
    return None


def bullet_text(bullet) -> str:
    """Read text from legacy string bullets or source-aware bullet objects."""
    if isinstance(bullet, dict):
        return str(bullet.get("text", ""))
    return str(bullet or "")


def _assign_entry_ids(section: dict, previous_section: dict, section_id: str) -> None:
    entries = section.get("entries", [])
    previous_entries = previous_section.get("entries", [])
    if not isinstance(entries, list):
        entries = []
        section["entries"] = entries
    if not isinstance(previous_entries, list):
        previous_entries = []

    entry_matches = _reconcile_nodes(entries, previous_entries, "header")
    duplicate_counts: dict[str, int] = {}
    for entry_index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        previous_index = entry_matches.get(entry_index)
        previous_entry = (
            previous_entries[previous_index]
            if previous_index is not None
            else None
        )
        normalized_header = _normalized(entry.get("header", ""))
        duplicate_index = duplicate_counts.get(normalized_header, 0)
        duplicate_counts[normalized_header] = duplicate_index + 1

        entry_id = _existing_or_new_id(
            _preferred_id_source(previous_entry, entry),
            "source_id",
            "entry",
            section_id,
            normalized_header,
            str(duplicate_index),
        )
        entry["source_id"] = entry_id
        _assign_bullet_ids(entry, previous_entry or {}, entry_id)


def _assign_bullet_ids(entry: dict, previous_entry: dict, entry_id: str) -> None:
    bullets = entry.get("bullets", [])
    previous_bullets = previous_entry.get("bullets", [])
    if not isinstance(bullets, list):
        bullets = []
    if not isinstance(previous_bullets, list):
        previous_bullets = []

    previous_nodes = [_bullet_node(item) for item in previous_bullets]
    current_nodes = [_bullet_node(item) for item in bullets]
    bullet_matches = _reconcile_nodes(current_nodes, previous_nodes, "text")
    duplicate_counts: dict[str, int] = {}
    source_aware_bullets: list[dict] = []

    for index, node in enumerate(current_nodes):
        text = node["text"]
        normalized_text = _normalized(text)
        duplicate_index = duplicate_counts.get(normalized_text, 0)
        duplicate_counts[normalized_text] = duplicate_index + 1

        previous_index = bullet_matches.get(index)
        previous_node = previous_nodes[previous_index] if previous_index is not None else {}

        node["source_id"] = _existing_or_new_id(
            _preferred_id_source(previous_node, node),
            "source_id",
            "bullet",
            entry_id,
            normalized_text,
            str(duplicate_index),
        )
        source_aware_bullets.append(node)

    entry["bullets"] = source_aware_bullets


def _reconcile_nodes(
    current_nodes: list,
    previous_nodes: list,
    key: str,
) -> dict[int, int]:
    """Match exact content first, then use same-index fallback for edits."""
    matches: dict[int, int] = {}
    used_previous: set[int] = set()

    for current_index, current in enumerate(current_nodes):
        if not isinstance(current, dict):
            continue
        current_value = _normalized(current.get(key, ""))
        for previous_index, previous in enumerate(previous_nodes):
            if (
                previous_index not in used_previous
                and isinstance(previous, dict)
                and _normalized(previous.get(key, "")) == current_value
            ):
                matches[current_index] = previous_index
                used_previous.add(previous_index)
                break

    for current_index, current in enumerate(current_nodes):
        if (
            current_index not in matches
            and isinstance(current, dict)
            and current_index < len(previous_nodes)
            and current_index not in used_previous
            and isinstance(previous_nodes[current_index], dict)
        ):
            matches[current_index] = current_index
            used_previous.add(current_index)

    return matches


def _bullet_node(bullet) -> dict:
    if isinstance(bullet, dict):
        node = copy.deepcopy(bullet)
        node["text"] = str(node.get("text", ""))
        return node
    return {"text": str(bullet or "")}


def _preferred_id_source(previous: Optional[dict], current: dict) -> dict:
    if isinstance(previous, dict) and previous.get("source_id"):
        return previous
    return current


def _existing_or_new_id(previous: Optional[dict], field: str, kind: str, *parts: str) -> str:
    if isinstance(previous, dict) and previous.get(field):
        return str(previous[field])
    digest = hashlib.sha256("|".join((kind, *parts)).encode("utf-8")).hexdigest()[:16]
    return f"{kind[:3]}_{digest}"


def _normalized(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()
