"""기존 코드베이스 수정 모드의 컨텍스트 수집기.

modify 모드에서 Planner에게 전달할 현재 프로젝트 상태를 수집한다.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.context.project_policy import ProjectPolicy

logger = logging.getLogger(__name__)

_COLLECT_TIMEOUT = 30


def _sanitize_branch_for_path(name: str) -> str:
    """브랜치명을 파일 경로에 안전한 형식으로 변환한다 (review 의존 회피용 로컬 구현)."""
    sanitized = name.replace("/", "-")
    sanitized = re.sub(r"[^\w\-.]", "-", sanitized)
    sanitized = sanitized.replace("..", ".")
    sanitized = re.sub(r"-{2,}", "-", sanitized)
    sanitized = sanitized.strip("-.")
    return sanitized or "unknown-branch"


@dataclass
class ModifyContext:
    """수정 모드에서 수집된 프로젝트 컨텍스트."""

    git_branch: str = ""
    git_diff: str = ""
    changed_files: list[str] = field(default_factory=list)
    design_intent: str = ""
    code_convention: str = ""
    adrs: list[dict[str, str]] = field(default_factory=list)
    structure_rules: str = ""
    recent_test_summary: str = ""
    project_policy: str = ""

    def to_markdown(self) -> str:
        """수집된 컨텍스트를 마크다운으로 변환한다."""
        sections: list[str] = ["# 프로젝트 수정 컨텍스트\n"]

        sections.append(f"## Git 브랜치\n\n`{self.git_branch}`\n")

        if self.changed_files:
            sections.append("## 변경된 파일\n")
            for f in self.changed_files:
                sections.append(f"- `{f}`")
            sections.append("")

        if self.git_diff:
            sections.append("## Git Diff\n")
            diff_preview = self.git_diff[:5000]
            if len(self.git_diff) > 5000:
                diff_preview += "\n\n... (이하 생략)"
            sections.append(f"```diff\n{diff_preview}\n```\n")

        if self.design_intent:
            sections.append(f"## 설계 의도\n\n{self.design_intent}\n")

        if self.code_convention:
            conv_preview = self.code_convention[:3000]
            sections.append(f"## 코드 컨벤션\n\n```yaml\n{conv_preview}\n```\n")

        if self.adrs:
            sections.append("## 아키텍처 결정 (ADR)\n")
            for adr in self.adrs:
                sections.append(f"### {adr.get('filename', '')}: {adr.get('title', '')}")
                sections.append(f"상태: {adr.get('status', 'unknown')}\n")
            sections.append("")

        if self.structure_rules:
            rules_preview = self.structure_rules[:2000]
            sections.append(f"## 구조 규칙\n\n```yaml\n{rules_preview}\n```\n")

        if self.recent_test_summary:
            sections.append(f"## 최근 검증 결과\n\n{self.recent_test_summary}\n")

        if self.project_policy:
            sections.append(f"## 프로젝트 정책\n\n```yaml\n{self.project_policy}\n```\n")

        return "\n".join(sections)


class ModifyContextCollector:
    """modify 모드를 위한 프로젝트 컨텍스트 수집기."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)

    def collect(self, policy: ProjectPolicy | None = None) -> ModifyContext:
        """프로젝트 컨텍스트를 수집한다.

        Args:
            policy: 프로젝트 정책. None이면 기본 경로를 사용한다.
        """
        convention_path = (
            self.project_dir / policy.conventions_source
            if policy
            else self.project_dir / "docs" / "code-convention.yaml"
        )
        adr_dir = (
            self.project_dir / policy.adr_directory
            if policy
            else self.project_dir / "docs" / "adr"
        )
        structure_path = (
            self.project_dir / policy.structure_source
            if policy
            else self.project_dir / "harness_structure.yaml"
        )

        ctx = ModifyContext(
            git_branch=self._get_git_branch(),
            git_diff=self._get_git_diff(),
            changed_files=self._get_changed_files(),
            design_intent=self._read_file_safe(
                self._find_latest_design_intent()
            ),
            code_convention=self._read_file_safe(convention_path),
            adrs=self._load_adrs(adr_dir),
            structure_rules=self._read_file_safe(structure_path),
            recent_test_summary=self._get_recent_test_summary(),
            project_policy=self._read_file_safe(
                self.project_dir / ".harness" / "project-policy.yaml"
            ),
        )
        logger.info(
            "수정 컨텍스트 수집 완료: branch=%s, changed_files=%d, adrs=%d",
            ctx.git_branch,
            len(ctx.changed_files),
            len(ctx.adrs),
        )
        return ctx

    def _get_git_branch(self) -> str:
        return self._run_git("branch", "--show-current") or "unknown"

    def _get_git_diff(self) -> str:
        staged = self._run_git("diff", "--cached")
        unstaged = self._run_git("diff")
        parts: list[str] = []
        if staged:
            parts.append(f"### Staged\n{staged}")
        if unstaged:
            parts.append(f"### Unstaged\n{unstaged}")
        return "\n\n".join(parts)

    def _get_changed_files(self) -> list[str]:
        output = self._run_git("status", "--porcelain")
        if not output:
            return []
        return [
            line[3:].strip()
            for line in output.splitlines()
            if line.strip()
        ]

    def _load_adrs(self, adr_dir: Path | None = None) -> list[dict[str, str]]:
        if adr_dir is None:
            adr_dir = self.project_dir / "docs" / "adr"
        if not adr_dir.exists():
            return []
        adrs: list[dict[str, str]] = []
        for path in sorted(adr_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            title = "제목 없음"
            status = "unknown"
            for line in content.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            match = re.search(r"status:\s*(\w+)", content)
            if match:
                status = match.group(1)
            adrs.append({
                "filename": path.name,
                "title": title,
                "status": status,
                "content": content,
            })
        return adrs

    def _find_latest_design_intent(self) -> Path:
        artifacts_dir = self.project_dir / ".harness" / "review-artifacts"
        if not artifacts_dir.exists():
            return artifacts_dir / "unknown-branch" / "design-intent.md"
        branch = self._get_git_branch()
        sanitized = _sanitize_branch_for_path(branch)
        return artifacts_dir / sanitized / "design-intent.md"

    def _get_recent_test_summary(self) -> str:
        parts: list[str] = []
        ruff = self._run_cmd("ruff", "check", ".", "--quiet")
        if ruff is not None:
            parts.append(f"### Ruff\n{ruff or '에러 없음'}")
        mypy = self._run_cmd("mypy", "harness", "--no-error-summary")
        if mypy is not None:
            parts.append(f"### Mypy\n{mypy or '에러 없음'}")
        return "\n\n".join(parts) if parts else ""

    def _run_git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=_COLLECT_TIMEOUT,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _run_cmd(self, *args: str) -> str | None:
        try:
            result = subprocess.run(
                list(args),
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=_COLLECT_TIMEOUT,
            )
            return result.stdout.strip() + result.stderr.strip()
        except Exception:
            return None

    def _read_file_safe(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""
