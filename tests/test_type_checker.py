"""타입 체커 센서 테스트."""

from __future__ import annotations

from harness.sensors.computational.type_checker import TypeCheckerSensor, TypeIssue


class TestTypeCheckerSensor:
    def test_parse_mypy_line_error(self) -> None:
        sensor = TypeCheckerSensor("/tmp")
        issue = sensor._parse_line("foo.py:10: error: Incompatible types [assignment]")
        assert issue is not None
        assert issue.file == "foo.py"
        assert issue.line == 10
        assert issue.severity == "error"
        assert issue.error_code == "assignment"
        assert "Incompatible types" in issue.message

    def test_parse_mypy_line_warning(self) -> None:
        sensor = TypeCheckerSensor("/tmp")
        issue = sensor._parse_line("bar.py:5: warning: Unused import [unused-import]")
        assert issue is not None
        assert issue.severity == "warning"

    def test_parse_mypy_line_note(self) -> None:
        sensor = TypeCheckerSensor("/tmp")
        issue = sensor._parse_line("baz.py:1: note: See docs")
        assert issue is not None
        assert issue.severity == "note"

    def test_parse_mypy_line_invalid(self) -> None:
        sensor = TypeCheckerSensor("/tmp")
        assert sensor._parse_line("not a mypy line") is None
        assert sensor._parse_line("") is None

    def test_build_summary_no_issues(self) -> None:
        sensor = TypeCheckerSensor("/tmp")
        summary = sensor._build_summary([], True)
        assert "통과" in summary

    def test_build_summary_with_errors(self) -> None:
        sensor = TypeCheckerSensor("/tmp")
        issues = [
            TypeIssue("a.py", 1, "error", "bad type", "assignment"),
            TypeIssue("b.py", 2, "error", "missing", "attr-defined"),
        ]
        summary = sensor._build_summary(issues, False)
        assert "실패" in summary
        assert "2개 에러" in summary
