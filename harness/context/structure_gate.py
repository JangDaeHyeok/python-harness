"""하네스 고정 프로젝트 구조 게이트."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from harness.context.project_policy import DEFAULT_POLICY_PATH, ProjectPolicyManager

STRUCTURE_ADR_PATH = "docs/adr/0010-structure-enforcement.md"
MIGRATION_COMMAND = "harness-init --migrate"


@dataclass(frozen=True)
class StructureReport:
    """고정 구조 검사 결과."""

    ok: bool
    missing: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def check_structure(project_dir: Path) -> StructureReport:
    """프로젝트가 하네스 고정 구조를 만족하는지 검사한다."""
    root = Path(project_dir)
    missing: list[str] = []

    _require_dir(root, "docs/", missing)
    _require_adr_dir(root, missing)
    _require_file(root, "docs/code-convention.yaml", missing)
    _require_file(root, "harness_structure.yaml", missing)
    _require_file(root, str(DEFAULT_POLICY_PATH), missing)
    _require_dir(root, "tests/", missing)
    _require_dir(root, "scripts/", missing)

    package = ProjectPolicyManager(root).load().package.strip() or "harness"
    _require_dir(root, f"{package}/", missing)

    return StructureReport(
        ok=not missing,
        missing=missing,
        suggestions=[MIGRATION_COMMAND] if missing else [],
    )


def format_structure_violation(report: StructureReport) -> str:
    """사용자에게 보여줄 구조 위반 메시지를 만든다."""
    missing_lines = "\n".join(f"  - {path}" for path in report.missing)
    suggestions = report.suggestions or [MIGRATION_COMMAND]
    suggestion_lines = "\n".join(f"  {suggestion}" for suggestion in suggestions)
    return "\n".join([
        "[STRUCTURE VIOLATION] 하네스 구조를 따르지 않는 프로젝트입니다.",
        "누락:",
        missing_lines,
        "조치:",
        suggestion_lines,
        f"상세 정책: {STRUCTURE_ADR_PATH}",
    ])


def _require_dir(root: Path, relative: str, missing: list[str]) -> None:
    path = root / relative
    if not path.is_dir():
        missing.append(relative)


def _require_file(root: Path, relative: str, missing: list[str]) -> None:
    path = root / relative
    if not path.is_file():
        missing.append(relative)


def _require_adr_dir(root: Path, missing: list[str]) -> None:
    relative = "docs/adr/"
    path = root / relative
    if not path.is_dir():
        missing.append(relative)
        return
    if not any(child.is_file() and child.suffix == ".md" for child in path.iterdir()):
        missing.append(f"{relative}*.md")
