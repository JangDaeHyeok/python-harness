"""고정 구조 게이트 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from harness.context.structure_gate import check_structure, format_structure_violation
from scripts.auto_pr_pipeline import enforce_structure_gate as enforce_auto_pr_structure_gate
from scripts.create_pr_body import enforce_structure_gate as enforce_pr_body_structure_gate
from scripts.run_harness import enforce_structure_gate as enforce_harness_structure_gate

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def make_valid_project(root: Path, package: str = "app") -> None:
    """테스트용 고정 구조 프로젝트를 만든다."""
    (root / "docs" / "adr").mkdir(parents=True)
    (root / "docs" / "adr" / "0001-test.md").write_text("# ADR\n", encoding="utf-8")
    (root / "docs" / "code-convention.yaml").write_text("rules: []\n", encoding="utf-8")
    (root / "harness_structure.yaml").write_text("rules: []\n", encoding="utf-8")
    (root / ".harness").mkdir()
    (root / ".harness" / "project-policy.yaml").write_text(
        f"project:\n  name: test\n  package: {package}\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "scripts").mkdir()
    (root / package).mkdir()


@pytest.mark.parametrize(
    ("remove_path", "expected"),
    [
        ("docs", "docs/"),
        ("docs/adr", "docs/adr/"),
        ("docs/code-convention.yaml", "docs/code-convention.yaml"),
        ("harness_structure.yaml", "harness_structure.yaml"),
        (".harness/project-policy.yaml", ".harness/project-policy.yaml"),
        ("tests", "tests/"),
        ("scripts", "scripts/"),
        ("app", "app/"),
    ],
)
def test_check_structure_reports_missing_required_paths(
    tmp_path: Path,
    remove_path: str,
    expected: str,
) -> None:
    make_valid_project(tmp_path)
    target = tmp_path / remove_path
    if target.is_dir():
        for child in sorted(target.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            else:
                child.rmdir()
        target.rmdir()
    else:
        target.unlink()

    report = check_structure(tmp_path)

    assert report.ok is False
    assert expected in report.missing
    assert report.suggestions == ["harness-init --migrate"]


def test_check_structure_requires_at_least_one_adr_markdown(tmp_path: Path) -> None:
    make_valid_project(tmp_path)
    (tmp_path / "docs" / "adr" / "0001-test.md").unlink()

    report = check_structure(tmp_path)

    assert report.ok is False
    assert "docs/adr/*.md" in report.missing


def test_check_structure_ok_when_all_required_paths_exist(tmp_path: Path) -> None:
    make_valid_project(tmp_path)

    report = check_structure(tmp_path)

    assert report.ok is True
    assert report.missing == []
    assert report.suggestions == []


def test_check_structure_rejects_src_layout_when_root_package_missing(
    tmp_path: Path,
) -> None:
    make_valid_project(tmp_path)
    (tmp_path / "app").rmdir()
    src_package = tmp_path / "src" / "app"
    src_package.mkdir(parents=True)
    (src_package / "__init__.py").write_text("", encoding="utf-8")

    report = check_structure(tmp_path)

    assert report.ok is False
    assert "app/" in report.missing


def test_check_structure_accepts_src_layout_when_policy_declares_source_root(
    tmp_path: Path,
) -> None:
    make_valid_project(tmp_path)
    (tmp_path / "app").rmdir()
    src_package = tmp_path / "src" / "app"
    src_package.mkdir(parents=True)
    (src_package / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / ".harness" / "project-policy.yaml").write_text(
        "project:\n  name: test\n  package: app\n  source_root: src\n",
        encoding="utf-8",
    )

    report = check_structure(tmp_path)

    assert report.ok is True, report.missing


def test_format_structure_violation_is_korean_user_facing(tmp_path: Path) -> None:
    report = check_structure(tmp_path)

    message = format_structure_violation(report)

    assert message.startswith("[STRUCTURE VIOLATION] 하네스 구조를 따르지 않는 프로젝트입니다.")
    assert "누락:\n  - docs/" in message
    assert "조치:\n  harness-init --migrate" in message
    assert "상세 정책: docs/adr/0010-structure-enforcement.md" in message


@pytest.mark.parametrize(
    "enforce",
    [
        enforce_harness_structure_gate,
        enforce_auto_pr_structure_gate,
        enforce_pr_body_structure_gate,
    ],
)
def test_entrypoint_gate_rejects_empty_project(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    enforce: Callable[[Path], None],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        enforce(tmp_path)

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "[STRUCTURE VIOLATION]" in captured.err
    assert "harness-init --migrate" in captured.err
