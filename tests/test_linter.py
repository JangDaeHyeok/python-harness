"""린터 센서 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness.sensors.computational.linter import LinterSensor

if TYPE_CHECKING:
    from pathlib import Path


class TestLinterSensor:
    def test_run_ruff_clean_project(self, tmp_path: Path) -> None:
        (tmp_path / "clean.py").write_text('x = 1\n')
        sensor = LinterSensor(str(tmp_path))
        result = sensor.run_ruff()
        assert result.summary_for_llm  # 항상 요약이 존재

    def test_custom_forbidden_import(self, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text("import os\nfrom os import path\n")

        sensor = LinterSensor(str(tmp_path), custom_rules=[
            {
                "type": "forbidden_import",
                "pattern": r"import os",
                "allowed_dirs": ["scripts/"],
                "message": "os 모듈은 scripts/ 에서만 사용 가능",
            }
        ])
        result = sensor.run_custom_rules()
        assert not result.passed
        assert result.total_errors > 0
        assert any("os 모듈" in i.message for i in result.issues)

    def test_custom_forbidden_import_allowed_dir(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "ok.py").write_text("import os\n")

        sensor = LinterSensor(str(tmp_path), custom_rules=[
            {
                "type": "forbidden_import",
                "pattern": r"import os",
                "allowed_dirs": ["scripts/"],
                "message": "os 모듈은 scripts/ 에서만 사용 가능",
            }
        ])
        result = sensor.run_custom_rules()
        assert result.passed

    def test_custom_file_location(self, tmp_path: Path) -> None:
        (tmp_path / "wrong_place.py").write_text("class MyAPI:\n    pass\n")

        sensor = LinterSensor(str(tmp_path), custom_rules=[
            {
                "type": "file_location",
                "pattern": r"class \w+API",
                "required_dir": "api/",
                "message": "API 클래스는 api/ 디렉터리에 위치해야 합니다",
            }
        ])
        result = sensor.run_custom_rules()
        assert not result.passed

    def test_run_all_combines_results(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("x = 1\n")
        sensor = LinterSensor(str(tmp_path), custom_rules=[])
        result = sensor.run_all()
        assert result.summary_for_llm

    def test_build_summary_no_issues(self) -> None:
        sensor = LinterSensor("/tmp")
        summary = sensor._build_summary([])
        assert "통과" in summary

    def test_parse_ruff_json_empty(self) -> None:
        sensor = LinterSensor("/tmp")
        result = sensor._parse_ruff_json("[]")
        assert result.passed
        assert result.total_errors == 0
