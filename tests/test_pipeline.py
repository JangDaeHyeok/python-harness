"""파이프라인 통합 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from pathlib import Path

from harness.pipeline.harness_pipeline import HarnessPipeline


class TestHarnessPipeline:
    def test_run_all_on_empty_project(self, tmp_path: Path) -> None:
        (tmp_path / "harness_structure.yaml").write_text("rules: []\n")
        pipeline = HarnessPipeline(str(tmp_path))
        result = pipeline.run_all()
        assert result.summary_for_llm
        assert result.lint is not None
        assert result.type_check is not None
        assert result.structure is not None
        assert result.tests is not None

    def test_run_fast(self, tmp_path: Path) -> None:
        (tmp_path / "clean.py").write_text("x: int = 1\n")
        pipeline = HarnessPipeline(str(tmp_path))
        result = pipeline.run_fast()
        assert result.summary_for_llm
        assert result.lint is not None
        assert result.type_check is not None

    def test_pipeline_with_structure_violation(self, tmp_path: Path) -> None:
        config = {"rules": [
            {"name": "req", "type": "required_files", "files": ["MISSING.md"]},
        ]}
        (tmp_path / "harness_structure.yaml").write_text(
            yaml.dump(config, allow_unicode=True)
        )
        pipeline = HarnessPipeline(str(tmp_path))
        result = pipeline.run_all()
        assert result.structure is not None
        assert not result.structure.passed
