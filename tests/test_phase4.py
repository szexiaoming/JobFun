"""
Tests for Phase 4: PDF compiler, error parser, compiler detection.
"""

from pathlib import Path

from src.latex.compiler import (
    _is_hard_error,
    _needs_xelatex,
    check_compiler,
)
from src.latex.error_parser import LaTeXError, parse_compile_log


class TestCompilerDetection:
    def test_check_compiler(self):
        result = check_compiler()
        assert isinstance(result, dict)
        assert "pdflatex" in result
        assert "xelatex" in result
        # On this machine, both should be available (MiKTeX installed)
        assert result["pdflatex"] or result["xelatex"], \
            "Expected at least one LaTeX compiler"


class TestHardErrorDetection:
    def test_emergency_stop(self):
        assert _is_hard_error("Emergency stop") is True

    def test_missing_document(self):
        assert _is_hard_error(r"Missing \begin{document}") is True

    def test_undefined_control(self):
        assert _is_hard_error("Undefined control sequence \\foo") is True

    def test_warnings_are_not_hard(self):
        assert _is_hard_error("Overfull \\hbox") is False
        assert _is_hard_error("Underfull \\vbox") is False


class TestXeLaTeXDetection:
    def test_chinese_detected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tex = Path(tmp) / "test.tex"
            tex.write_text("你好世界\n\\section{Introduction}", encoding="utf-8")
            assert _needs_xelatex(tex, Path(tmp)) is True

    def test_english_no_xelatex(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tex = Path(tmp) / "test.tex"
            tex.write_text("Hello World\n\\section{Introduction}", encoding="utf-8")
            assert _needs_xelatex(tex, Path(tmp)) is False


class TestErrorParser:
    def test_parse_undefined_control(self):
        log = r"""
! Undefined control sequence.
l.42 \resumeItem{Built pipeline with
                      Kafka}
"""
        errors = parse_compile_log(log, "")
        assert len(errors) >= 1
        assert errors[0].error_type == "undefined_cmd"

    def test_parse_emergency_stop(self):
        log = r"""
! Emergency stop.
<*> main.tex

*** (job aborted)
"""
        errors = parse_compile_log(log, "")
        assert len(errors) >= 1

    def test_empty_log(self):
        errors = parse_compile_log("", "")
        assert errors == []

    def test_multiple_errors(self):
        log = r"""
! Undefined control sequence.
l.10 \badcmd

! Missing \begin{document}.
l.1 \section{Hello}
"""
        errors = parse_compile_log(log, "")
        assert len(errors) == 2
        assert errors[0].error_type == "undefined_cmd"
        assert errors[1].error_type == "missing_document"
