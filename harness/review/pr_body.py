"""PR 본문 생성.

현재 브랜치 diff와 리뷰 산출물을 기반으로 pr-body.md를 생성한다.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.review.artifacts import ReviewArtifactManager

logger = logging.getLogger(__name__)


class DiffError(RuntimeError):
    """git diff 명령 실행 실패."""


def _resolve_base_ref(project_dir: Path, base_branch: str) -> str:
    """로컬 브랜치가 없을 때 origin/ 리모트 ref로 폴백한다.

    CI 환경(detached HEAD)에서는 로컬 main 브랜치가 없을 수 있으므로
    origin/main 등 리모트 ref를 시도한다.
    """
    check = subprocess.run(
        ["git", "rev-parse", "--verify", base_branch],
        cwd=str(project_dir),
        capture_output=True, text=True, timeout=10,
    )
    if check.returncode == 0:
        return base_branch

    remote_ref = f"origin/{base_branch}"
    check_remote = subprocess.run(
        ["git", "rev-parse", "--verify", remote_ref],
        cwd=str(project_dir),
        capture_output=True, text=True, timeout=10,
    )
    if check_remote.returncode == 0:
        return remote_ref

    return base_branch


def get_git_diff_stat(project_dir: Path, base_branch: str = "main") -> str:
    """base_branch에서 HEAD까지의 diff stat을 반환한다.

    Raises:
        DiffError: git diff 명령이 실패하면 발생한다.
    """
    ref = _resolve_base_ref(project_dir, base_branch)
    try:
        result = subprocess.run(
            ["git", "diff", f"{ref}...HEAD", "--stat"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        raise DiffError(f"git diff --stat 실행 실패: {e}") from e
    if result.returncode != 0:
        raise DiffError(
            f"git diff --stat 실패 (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def get_changed_files(project_dir: Path, base_branch: str = "main") -> list[str]:
    """base_branch에서 HEAD까지 변경된 파일 목록을 반환한다.

    Raises:
        DiffError: git diff 명령이 실패하면 발생한다.
    """
    ref = _resolve_base_ref(project_dir, base_branch)
    try:
        result = subprocess.run(
            ["git", "diff", f"{ref}...HEAD", "--name-only"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        raise DiffError(f"git diff --name-only 실행 실패: {e}") from e
    if result.returncode != 0:
        raise DiffError(
            f"git diff --name-only 실패 (exit {result.returncode}): {result.stderr.strip()}"
        )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


class PRBodyGenerator:
    """diff와 리뷰 산출물을 조합하여 PR 본문을 생성한다."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)  # normalize

    def generate(
        self,
        artifact_manager: ReviewArtifactManager,
        base_branch: str = "main",
        summary: str = "",
    ) -> str:
        """diff와 산출물 기반으로 PR 본문 마크다운을 생성한다."""
        diff_stat = get_git_diff_stat(self.project_dir, base_branch)
        changed_files = get_changed_files(self.project_dir, base_branch)

        design_intent = artifact_manager.load("design-intent.md")
        quality_guide = artifact_manager.load("code-quality-guide.md")

        lines: list[str] = ["# PR 본문\n"]

        # Summary
        lines.append("## Summary\n")
        if summary:
            lines.append(summary)
        elif design_intent:
            lines.extend(self._extract_overview(design_intent))
        else:
            lines.append("_작업 요약을 여기에 작성하세요._")
        lines.append("")

        # Changes
        lines.append("## Changes\n")
        if changed_files:
            for f in changed_files:
                lines.append(f"- `{f}`")
        else:
            lines.append("_변경 파일 없음_")
        lines.append("")

        if diff_stat:
            lines.append("### Diff Summary\n")
            lines.append("```")
            lines.append(diff_stat[:3000])
            lines.append("```")
            lines.append("")

        # Breaking Changes
        lines.append("## Breaking Changes\n")
        lines.append("_없음 (있으면 여기에 기술)_\n")

        # Test Plan
        lines.append("## Test Plan\n")
        lines.append("- [ ] 단위 테스트 통과 (`pytest`)")
        lines.append("- [ ] 타입 체크 통과 (`mypy harness`)")
        lines.append("- [ ] 린트 통과 (`ruff check .`)")
        lines.append("- [ ] 구조 분석 통과 (`python scripts/check_structure.py`)")
        lines.append("")

        # Related Artifacts
        lines.append("## Related Artifacts\n")
        artifact_list = artifact_manager.list_artifacts()
        if artifact_list:
            for a in artifact_list:
                branch = artifact_manager.branch
                lines.append(f"- `.harness/review-artifacts/{branch}/{a}`")
        else:
            lines.append("_생성된 산출물 없음_")

        if quality_guide:
            lines.append("\n### Code Quality Guide\n")
            lines.append(quality_guide[:2000])
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _extract_overview(design_intent_md: str) -> list[str]:
        """design-intent.md에서 작업 개요 섹션을 추출한다."""
        in_section = False
        extracted: list[str] = []
        for line in design_intent_md.splitlines():
            if line.startswith("## 작업 개요"):
                in_section = True
                continue
            if in_section:
                if line.startswith("##"):
                    break
                if line.strip():
                    extracted.append(line)
        return extracted if extracted else ["_설계 의도에서 개요를 찾을 수 없음_"]
