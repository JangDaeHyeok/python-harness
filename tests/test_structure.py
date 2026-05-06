"""구조 분석 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from pathlib import Path

from harness.sensors.computational.structure_test import StructureAnalyzer


class TestStructureAnalyzer:
    def _setup_project(self, tmp_path: Path, rules: list[dict[str, object]]) -> StructureAnalyzer:
        config = {"rules": rules}
        (tmp_path / "harness_structure.yaml").write_text(
            yaml.dump(config, allow_unicode=True)
        )
        return StructureAnalyzer(str(tmp_path))

    def test_required_files_pass(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Hello")
        analyzer = self._setup_project(tmp_path, [
            {"name": "req", "type": "required_files", "files": ["README.md"]},
        ])
        result = analyzer.analyze()
        assert result.passed

    def test_required_files_fail(self, tmp_path: Path) -> None:
        analyzer = self._setup_project(tmp_path, [
            {"name": "req", "type": "required_files", "files": ["MISSING.md"]},
        ])
        result = analyzer.analyze()
        assert not result.passed
        assert any(v.rule_name == "req" for v in result.violations)

    def test_dependency_direction_violation(self, tmp_path: Path) -> None:
        sensor_dir = tmp_path / "sensors"
        sensor_dir.mkdir()
        (sensor_dir / "bad_sensor.py").write_text("from agents import something\n")

        analyzer = self._setup_project(tmp_path, [
            {
                "name": "dep_dir",
                "type": "dependency_direction",
                "source": "sensors",
                "forbidden_imports": ["agents"],
            },
        ])
        result = analyzer.analyze()
        assert not result.passed

    def test_dependency_direction_clean(self, tmp_path: Path) -> None:
        sensor_dir = tmp_path / "sensors"
        sensor_dir.mkdir()
        (sensor_dir / "clean_sensor.py").write_text("import json\n")

        analyzer = self._setup_project(tmp_path, [
            {
                "name": "dep_dir",
                "type": "dependency_direction",
                "source": "sensors",
                "forbidden_imports": ["agents"],
            },
        ])
        result = analyzer.analyze()
        assert result.passed

    def test_naming_convention_violation(self, tmp_path: Path) -> None:
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "BadName.py").write_text("x = 1\n")

        analyzer = self._setup_project(tmp_path, [
            {
                "name": "naming",
                "type": "naming_convention",
                "directory": "models",
                "pattern": r"^[a-z_]+\.py$",
            },
        ])
        result = analyzer.analyze()
        assert len(result.violations) > 0

    def test_forbidden_pattern(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "debug.py").write_text("print('debug')\n")

        analyzer = self._setup_project(tmp_path, [
            {
                "name": "no_print",
                "type": "forbidden_pattern",
                "pattern": r"print\(",
                "directories": ["src"],
                "message": "print() 금지",
                "severity": "warning",
            },
        ])
        result = analyzer.analyze()
        assert len(result.violations) > 0
        assert result.violations[0].severity == "warning"

    def test_adr_loading(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "0001-test.md").write_text(
            "---\nstatus: accepted\ndate: 2026-01-01\nenforced_by: []\n---\n"
            "# ADR-0001: Test Decision\n\n## Context\nSome context.\n\n## Decision\nWe decided X.\n\n## Consequences\nSome consequences.\n"
        )
        (tmp_path / "harness_structure.yaml").write_text("rules: []\n")

        analyzer = StructureAnalyzer(str(tmp_path))
        assert len(analyzer.adrs) == 1
        assert analyzer.adrs[0].status == "accepted"
        assert "Test Decision" in analyzer.adrs[0].title

    def test_adr_summary(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "0001-arch.md").write_text(
            "---\nstatus: accepted\ndate: 2026-01-01\nenforced_by: []\n---\n"
            "# Use microservices\n\n## Decision\nAdopt microservices.\n"
        )
        (tmp_path / "harness_structure.yaml").write_text("rules: []\n")

        analyzer = StructureAnalyzer(str(tmp_path))
        summary = analyzer.get_adr_summary()
        assert "microservices" in summary.lower() or "0001" in summary

    def test_no_config_file(self, tmp_path: Path) -> None:
        analyzer = StructureAnalyzer(str(tmp_path))
        result = analyzer.analyze()
        assert result.passed
