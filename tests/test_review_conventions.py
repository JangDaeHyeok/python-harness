"""ConventionLoader 단위 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from harness.review.conventions import CodeConvention, ConventionLoader

if TYPE_CHECKING:
    from pathlib import Path


VALID_YAML = """\
conventions:
  - id: type-hints-required
    description: "모든 public 함수에 타입 힌트를 추가한다."
    category: type-safety
    severity: error
    tags: [typing, mypy]

  - id: no-print-in-harness
    description: "harness/ 내부에서 print() 금지."
    category: maintainability
    severity: warning
    tags: [logging, debug]

  - id: shell-safe-exec
    description: "셸 명령은 안전 유틸을 통해서만 실행한다."
    category: security
    severity: error
    tags: [security, shell]
"""

INVALID_YAML = "{ this: is: not: valid: yaml: [}"

EMPTY_YAML = "conventions: []"

NOT_DICT_YAML = "- item1\n- item2\n"


def make_project_with_convention(tmp_path: Path, content: str) -> Path:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "code-convention.yaml").write_text(content, encoding="utf-8")
    return tmp_path


class TestCodeConvention:
    def test_creation(self) -> None:
        c = CodeConvention(id="test", description="desc")
        assert c.id == "test"
        assert c.description == "desc"
        assert c.tags == []
        assert c.severity == "warning"
        assert c.category == "general"

    def test_creation_with_all_fields(self) -> None:
        c = CodeConvention(
            id="x",
            description="d",
            tags=["a", "b"],
            severity="error",
            category="security",
        )
        assert c.tags == ["a", "b"]
        assert c.severity == "error"


class TestConventionLoader:
    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, VALID_YAML)
        loader = ConventionLoader(project)
        conventions = loader.load()
        assert len(conventions) == 3

    def test_load_convention_fields(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, VALID_YAML)
        loader = ConventionLoader(project)
        first = loader.load()[0]
        assert first.id == "type-hints-required"
        assert first.category == "type-safety"
        assert first.severity == "error"
        assert "typing" in first.tags

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        loader = ConventionLoader(tmp_path)
        conventions = loader.load()
        assert conventions == []

    def test_load_invalid_yaml_returns_empty(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, INVALID_YAML)
        loader = ConventionLoader(project)
        conventions = loader.load()
        assert conventions == []

    def test_load_empty_conventions_returns_empty(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, EMPTY_YAML)
        loader = ConventionLoader(project)
        assert loader.load() == []

    def test_load_not_dict_returns_empty(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, NOT_DICT_YAML)
        loader = ConventionLoader(project)
        assert loader.load() == []

    def test_load_caches_result(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, VALID_YAML)
        loader = ConventionLoader(project)
        first = loader.load()
        second = loader.load()
        assert first is second  # same object (cached)

    def test_filter_by_tags_match(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, VALID_YAML)
        loader = ConventionLoader(project)
        results = loader.filter_by_tags(["security"])
        assert len(results) == 1
        assert results[0].id == "shell-safe-exec"

    def test_filter_by_tags_no_match(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, VALID_YAML)
        loader = ConventionLoader(project)
        results = loader.filter_by_tags(["nonexistent-tag"])
        assert results == []

    def test_filter_by_tags_multiple(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, VALID_YAML)
        loader = ConventionLoader(project)
        results = loader.filter_by_tags(["typing", "security"])
        ids = [r.id for r in results]
        assert "type-hints-required" in ids
        assert "shell-safe-exec" in ids

    def test_filter_by_category(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, VALID_YAML)
        loader = ConventionLoader(project)
        results = loader.filter_by_category("security")
        assert len(results) == 1
        assert results[0].id == "shell-safe-exec"

    def test_filter_by_category_no_match(self, tmp_path: Path) -> None:
        project = make_project_with_convention(tmp_path, VALID_YAML)
        loader = ConventionLoader(project)
        assert loader.filter_by_category("nonexistent") == []

    @pytest.mark.parametrize("category", ["type-safety", "maintainability", "security"])
    def test_filter_by_category_parametrize(self, tmp_path: Path, category: str) -> None:
        project = make_project_with_convention(tmp_path, VALID_YAML)
        loader = ConventionLoader(project)
        results = loader.filter_by_category(category)
        assert len(results) >= 1
        assert all(r.category == category for r in results)
