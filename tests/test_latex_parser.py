"""
Tests for LaTeX parser.
"""

from pathlib import Path

import pytest

from src.core.latex_parser import (
    LaTeXParserError,
    _extract_body,
    _extract_bullets,
    _extract_preamble,
    _parse_entries,
    _parse_sections,
    _resolve_inputs,
    parse_tex_files,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestPreambleExtraction:
    def test_extract_preamble(self):
        content = r"""
\documentclass{resume}
\usepackage[utf8]{inputenc}
\usepackage{hyperref}
\begin{document}
Hello
\end{document}
"""
        preamble = _extract_preamble(content)
        assert "hyperref" in preamble["packages"]
        assert "inputenc" in preamble["packages"]

    def test_no_preamble(self):
        content = r"\begin{document}Hello\end{document}"
        preamble = _extract_preamble(content)
        assert preamble["packages"] == []


class TestBodyExtraction:
    def test_extract_body(self):
        content = r"\begin{document}Hello World\end{document}"
        body = _extract_body(content)
        assert "Hello World" in body
        assert r"\begin{document}" not in body

    def test_no_document_env(self):
        content = "Just some text"
        body = _extract_body(content)
        assert body == content


class TestBulletExtraction:
    def test_extract_item_bullets(self):
        text = r"""
\begin{itemize}
  \item First bullet
  \item Second bullet
\end{itemize}
"""
        bullets = _extract_bullets(text)
        assert len(bullets) >= 2

    def test_extract_resumeitem(self):
        text = r"\resumeItem{Built data pipeline with Python}"
        bullets = _extract_bullets(text)
        assert len(bullets) == 1
        assert "Python" in bullets[0]

    def test_empty_text(self):
        bullets = _extract_bullets("")
        assert bullets == []


class TestSectionParsing:
    def test_parse_sections_with_section_cmd(self):
        body = r"""
\section{Experience}
\begin{itemize}
  \item Did something
\end{itemize}
\section{Education}
\begin{itemize}
  \item Studied CS
\end{itemize}
"""
        sections = _parse_sections(body)
        assert len(sections) >= 2
        titles = [s["title"] for s in sections]
        assert "Experience" in titles
        assert "Education" in titles


class TestEntryParsing:
    def test_parse_resume_subheading(self):
        body = r"""
\resumeSubheading{Google}{2023--Present}{Software Engineer}{Mountain View, CA}
\begin{itemize}
  \item Built pipeline
\end{itemize}
"""
        entries = _parse_entries(body)
        assert len(entries) == 1
        assert "Google" in entries[0]["header"]
        assert len(entries[0]["bullets"]) >= 1


class TestInputResolution:
    def test_resolve_inputs(self):
        content = r"\input{sections/experience}"
        tex_files = {"sections/experience.tex": r"\section{Experience}\item Built X"}
        resolved = _resolve_inputs(content, tex_files, Path("."))
        assert "Built X" in resolved

    def test_resolve_nested_inputs(self):
        content = r"\input{outer}"
        tex_files = {
            "outer.tex": r"\input{inner} some text",
            "inner.tex": "Inner content",
        }
        resolved = _resolve_inputs(content, tex_files, Path("."))
        assert "Inner content" in resolved


class TestFullParse:
    def test_parse_sample_resume(self):
        main_tex = FIXTURES / "sample_resume" / "main.tex"
        assert main_tex.exists()

        content = main_tex.read_text(encoding="utf-8")
        tex_files = {"main.tex": content}

        result = parse_tex_files(main_tex, tex_files, FIXTURES / "sample_resume")
        assert "sections" in result
        assert len(result["sections"]) >= 2

        titles = {s["title"] for s in result["sections"]}
        assert "Experience" in titles

        # Check bullets were extracted
        all_bullets = []
        for section in result["sections"]:
            for entry in section.get("entries", []):
                all_bullets.extend(entry.get("bullets", []))
        assert len(all_bullets) >= 4  # At least 4 bullets across all sections
