"""
Tests for Phase 3: dialogue engine, LaTeX validator, git utils, diff utils.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.latex.validator import ValidationResult, validate_changes


# ── LaTeX Validator ──────────────────────────────────

class TestValidator:
    def test_empty_changes_pass(self):
        result = validate_changes(
            original_files={"main.tex": "content"},
            modified_files={"main.tex": "content"},
            original_structure={"sections": []},
        )
        assert result.passed is True

    def test_preamble_modification_blocked(self):
        original = r"""\documentclass{article}
\usepackage{hyperref}
\begin{document}
\section{Experience}
\item Built something
\end{document}"""

        modified = r"""\documentclass{article}
\usepackage{hyperref}
\usepackage{amsmath}
\begin{document}
\section{Experience}
\item Built something
\end{document}"""

        result = validate_changes(
            original_files={"main.tex": original},
            modified_files={"main.tex": modified},
            original_structure={"sections": [{"title": "Experience", "entries": [{"header": "", "bullets": ["Built something"]}]}]},
        )
        assert not result.passed

    def test_cls_modification_blocked(self):
        result = validate_changes(
            original_files={"resume.cls": "old cls content"},
            modified_files={"resume.cls": "new cls content"},
            original_structure={"sections": []},
        )
        assert not result.passed

    def test_date_removal_blocked(self):
        original = r"\section{Experience}\resumeSubheading{Google}{2023--Present}{SDE}{CA}\begin{itemize}\item Built X\end{itemize}"
        modified = r"\section{Experience}\resumeSubheading{Google}{Present}{SDE}{CA}\begin{itemize}\item Built X\end{itemize}"

        result = validate_changes(
            original_files={"exp.tex": original},
            modified_files={"exp.tex": modified},
            original_structure={
                "sections": [{"title": "Experience", "entries": [{"header": "Google", "bullets": ["Built X"]}]}]
            },
        )
        assert not result.passed

    def test_normal_wording_change_passes(self):
        original = r"""\begin{document}
\section{Experience}
\resumeSubheading{Google}{2023--Present}{SDE}{CA}
\begin{itemize}
\item Used Python for data processing
\end{itemize}
\end{document}"""

        modified = r"""\begin{document}
\section{Experience}
\resumeSubheading{Google}{2023--Present}{SDE}{CA}
\begin{itemize}
\item Built data pipeline with Python processing 500K records daily
\end{itemize}
\end{document}"""

        result = validate_changes(
            original_files={"exp.tex": original},
            modified_files={"exp.tex": modified},
            original_structure={
                "sections": [{"title": "Experience", "entries": [{"header": "Google", "bullets": ["Used Python for data processing"]}]}]
            },
        )
        assert result.passed


# ── Diff Utils ───────────────────────────────────────

class TestDiff:
    def test_generate_diff(self):
        from src.utils.diff_utils import generate_diff
        diff = generate_diff("line1\nline2\n", "line1\nline2 modified\n")
        assert "line2 modified" in diff
        assert "line2" in diff

    def test_no_changes(self):
        from src.utils.diff_utils import generate_diff
        diff = generate_diff("same", "same")
        assert diff == ""


# ── Git Utils ────────────────────────────────────────

class TestGit:
    def test_init_and_commit(self):
        from src.utils.git_utils import commit, init_repo

        with tempfile.TemporaryDirectory(
            dir=Path(__file__).parent.parent,
            ignore_cleanup_errors=True,
        ) as tmp:
            repo_dir = Path(tmp)
            repo = init_repo(repo_dir)
            assert not repo.bare
            repo.close()  # Release file handles

            (repo_dir / "test.tex").write_text("test content")
            commit_hash = commit(repo_dir, "test commit")
            assert commit_hash

    def test_revert(self):
        from src.utils.git_utils import commit, init_repo, revert_last

        with tempfile.TemporaryDirectory(
            dir=Path(__file__).parent.parent,
            ignore_cleanup_errors=True,
        ) as tmp:
            repo_dir = Path(tmp)
            repo = init_repo(repo_dir)
            repo.close()

            (repo_dir / "test.tex").write_text("v1")
            commit(repo_dir, "v1")

            (repo_dir / "test.tex").write_text("v2")
            commit(repo_dir, "v2")

            old = revert_last(repo_dir)
            assert old
            assert (repo_dir / "test.tex").read_text() == "v1"


# ── Dialogue Engine (mock) ───────────────────────────

class TestDialogueEngine:
    def test_resume_context_summary(self):
        from src.core.dialogue_engine import resume_context_summary

        structured = {
            "sections": [
                {
                    "title": "Experience",
                    "entries": [
                        {
                            "header": "SDE @ Google, 2023-Present",
                            "bullets": ["Built APIs with Python", "Led migration to K8s"],
                        }
                    ],
                }
            ]
        }
        summary = resume_context_summary(structured)
        assert "Experience" in summary
        assert "Google" in summary
        assert "Built APIs" in summary

    def test_jd_requirements_summary(self):
        from src.core.dialogue_engine import jd_requirements_summary

        jd = {
            "required_skills": ["Python", "AWS"],
            "preferred_skills": ["K8s"],
            "responsibilities": ["Design systems"],
        }
        summary = jd_requirements_summary(jd)
        assert "Python" in summary
        assert "K8s" in summary
        assert "Design systems" in summary


# ── LaTeX Modifier (mock) ───────────────────────────

class TestLaTeXModifier:
    def test_no_suggestions_raises(self):
        from src.core.latex_modifier import LaTeXModifierError, modify_resume
        with pytest.raises(LaTeXModifierError, match="No suggestions"):
            modify_resume(Path("."), [], [])

    def test_missing_dir_raises(self):
        from src.core.latex_modifier import LaTeXModifierError, modify_resume
        with pytest.raises(LaTeXModifierError, match="not found"):
            modify_resume(Path("/nonexistent/path"), [{"original": "x", "suggested": "y"}])
