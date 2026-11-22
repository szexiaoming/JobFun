"""Primary information architecture for JobFun."""

from __future__ import annotations

import streamlit as st


PRIMARY_NAV_ITEMS = (
    ("workbench", "🏠 工作台"),
    ("jobs", "💼 岗位"),
    ("interview", "🎯 面试"),
    ("profile", "👤 个人档案"),
)

LEGACY_PAGE_ALIASES = {
    "home": "workbench",
    "tracker": "workbench",
    "editor": "profile",
    "resumes": "profile",
}


def normalize_page(page: str) -> str:
    """Map old session routes into the four-item information architecture."""
    normalized = LEGACY_PAGE_ALIASES.get(page, page)
    valid_pages = {item[0] for item in PRIMARY_NAV_ITEMS} | {"agent"}
    return normalized if normalized in valid_pages else "workbench"


def render_primary_navigation() -> None:
    """Render exactly four first-level navigation controls."""
    current = normalize_page(st.session_state.get("page", "workbench"))
    st.session_state["page"] = current
    columns = st.columns(len(PRIMARY_NAV_ITEMS))
    for column, (page, label) in zip(columns, PRIMARY_NAV_ITEMS):
        with column:
            if st.button(
                label,
                use_container_width=True,
                type="primary" if current == page else "secondary",
                key=f"nav_{page}",
            ):
                st.session_state["page"] = page
                st.rerun()
