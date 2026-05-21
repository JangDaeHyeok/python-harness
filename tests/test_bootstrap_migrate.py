"""기존 Python 프로젝트 마이그레이션 부트스트랩 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from harness.bootstrap.initializer import BootstrapInitializer, TargetKind, relative_path_for
from harness.sensors.computational.structure_test import StructureAnalyzer

if TYPE_CHECKING:
    from pathlib import Path


def _write_package(root: Path, name: str) -> None:
    package_dir = root / name
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")


def _write_src_package(root: Path, name: str) -> None:
    package_dir = root / "src" / name
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")


def _assert_migration_gate_passes(root: Path) -> None:
    result = StructureAnalyzer(str(root)).analyze()
    assert result.passed, result.summary_for_llm


def test_migrate_empty_directory_rejects_without_package_candidate(
    tmp_path: Path,
) -> None:
    initializer = BootstrapInitializer(project_dir=tmp_path, offline=True)

    with pytest.raises(ValueError, match="패키지 후보를 찾지 못했습니다"):
        initializer.migrate_existing()


def test_migrate_src_layout_rejects_with_clear_error(tmp_path: Path) -> None:
    _write_src_package(tmp_path, "billing")

    initializer = BootstrapInitializer(project_dir=tmp_path, offline=True)

    with pytest.raises(ValueError, match=r"src/ 레이아웃은 .* 제외"):
        initializer.migrate_existing()


def test_migrate_single_package_auto_adopts_and_creates_required_files(
    tmp_path: Path,
) -> None:
    _write_package(tmp_path, "billing")

    initializer = BootstrapInitializer(
        project_dir=tmp_path,
        prompt="사내 청구 자동화",
        offline=True,
    )
    result = initializer.migrate_existing()

    assert "[MIGRATE] 패키지 자동 채택: billing" in result.messages
    assert (tmp_path / "docs/adr/0001-initial-architecture.md").exists()
    assert (tmp_path / "docs/code-convention.yaml").exists()
    assert (tmp_path / "harness_structure.yaml").exists()
    assert (tmp_path / ".harness/project-policy.yaml").exists()
    assert (tmp_path / "tests").is_dir()
    assert (tmp_path / "scripts").is_dir()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "README.md").exists()
    assert not (tmp_path / ".claude/skills").exists()

    policy = yaml.safe_load(
        (tmp_path / relative_path_for(TargetKind.POLICY)).read_text(encoding="utf-8")
    )
    assert policy["project"]["package"] == "billing"

    structure = yaml.safe_load((tmp_path / "harness_structure.yaml").read_text())
    no_print = next(rule for rule in structure["rules"] if rule["name"] == "no_print_debug")
    assert no_print["directories"] == ["billing"]
    _assert_migration_gate_passes(tmp_path)


def test_migrate_existing_0001_adr_is_required_by_generated_structure(
    tmp_path: Path,
) -> None:
    _write_package(tmp_path, "billing")
    adr_path = tmp_path / "docs/adr/0001-existing-decision.md"
    adr_path.parent.mkdir(parents=True)
    adr_path.write_text("# Existing ADR\n", encoding="utf-8")

    initializer = BootstrapInitializer(project_dir=tmp_path, offline=True)
    initializer.migrate_existing()

    assert not (tmp_path / "docs/adr/0001-initial-architecture.md").exists()
    structure = yaml.safe_load((tmp_path / "harness_structure.yaml").read_text())
    required = next(
        rule for rule in structure["rules"] if rule["name"] == "required_harness_files"
    )
    assert "docs/adr/0001-existing-decision.md" in required["files"]
    assert "docs/adr/0001-initial-architecture.md" not in required["files"]
    _assert_migration_gate_passes(tmp_path)


def test_migrate_multiple_packages_rejects_without_policy(tmp_path: Path) -> None:
    _write_package(tmp_path, "billing")
    _write_package(tmp_path, "payments")

    initializer = BootstrapInitializer(project_dir=tmp_path, offline=True)

    with pytest.raises(ValueError, match="패키지 후보가 여러 개입니다"):
        initializer.migrate_existing()


def test_migrate_multiple_packages_uses_policy_package(tmp_path: Path) -> None:
    _write_package(tmp_path, "billing")
    _write_package(tmp_path, "payments")
    policy_path = tmp_path / ".harness/project-policy.yaml"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        "project:\n  name: demo\n  package: payments\npolicies: {}\n",
        encoding="utf-8",
    )

    initializer = BootstrapInitializer(project_dir=tmp_path, offline=True)
    result = initializer.migrate_existing()

    assert "[MIGRATE] 패키지 자동 채택: payments" in result.messages
    assert policy_path.read_text(encoding="utf-8").startswith("project:\n")
    structure = yaml.safe_load((tmp_path / "harness_structure.yaml").read_text())
    no_print = next(rule for rule in structure["rules"] if rule["name"] == "no_print_debug")
    assert no_print["directories"] == ["payments"]
    _assert_migration_gate_passes(tmp_path)


def test_migrate_normalizes_legacy_top_level_policy_package(tmp_path: Path) -> None:
    _write_package(tmp_path, "billing")
    policy_path = tmp_path / ".harness/project-policy.yaml"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        "package: billing\nproject:\n  name: demo\npolicies:\n  review_language: ko\n",
        encoding="utf-8",
    )

    initializer = BootstrapInitializer(project_dir=tmp_path, offline=True)
    result = initializer.migrate_existing()

    policy_plan = next(p for p in result.plans if p.target_path == policy_path)
    assert policy_plan.status == "updated"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    assert "package" not in policy
    assert policy["project"]["package"] == "billing"
    assert policy["policies"]["review_language"] == "ko"
    _assert_migration_gate_passes(tmp_path)


def test_migrate_creates_only_missing_files_without_force(tmp_path: Path) -> None:
    _write_package(tmp_path, "billing")
    convention_path = tmp_path / "docs/code-convention.yaml"
    convention_path.parent.mkdir(parents=True)
    convention_path.write_text("conventions: []\n", encoding="utf-8")

    initializer = BootstrapInitializer(project_dir=tmp_path, offline=True)
    result = initializer.migrate_existing()

    convention_plan = next(p for p in result.plans if p.target_path == convention_path)
    assert convention_plan.status == "skipped"
    assert convention_path.read_text(encoding="utf-8") == "conventions: []\n"
    assert (tmp_path / "docs/adr/0001-initial-architecture.md").exists()
    assert (tmp_path / "harness_structure.yaml").exists()
    assert (tmp_path / ".harness/project-policy.yaml").exists()
