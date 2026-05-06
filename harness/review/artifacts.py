"""리뷰 산출물 관리.

브랜치별 리뷰 결과물을 .harness/review-artifacts/{branch}/ 아래에 저장한다.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from harness.tools.path_safety import DEFAULT_BRANCH_FALLBACK, sanitize_branch_name

logger = logging.getLogger(__name__)

FALLBACK_BRANCH = DEFAULT_BRANCH_FALLBACK

__all__ = [
    "FALLBACK_BRANCH",
    "ReviewArtifactManager",
    "get_current_branch",
    "sanitize_branch_name",
]


def get_current_branch(project_dir: Path) -> str:
    """현재 git 브랜치 이름을 반환한다. 실패 시 fallback 이름을 반환한다."""
    cwd = Path(project_dir)  # normalize — justifies runtime import
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10,
        )
        branch = result.stdout.strip()
        return branch if branch else FALLBACK_BRANCH
    except (subprocess.SubprocessError, OSError):
        return FALLBACK_BRANCH


class ReviewArtifactManager:
    """브랜치별 리뷰 산출물을 생성·조회·목록화·존재 확인한다."""

    STANDARD_ARTIFACTS = (
        "design-intent.md",
        "code-quality-guide.md",
        "pr-body.md",
        "review-comments.md",
    )

    @staticmethod
    def _validate_filename(filename: str) -> None:
        name = Path(filename).name
        if name != filename or not filename or ".." in filename:
            raise ValueError(f"안전하지 않은 파일명입니다: {filename!r}")

    def __init__(self, project_dir: Path, branch: str | None = None) -> None:
        self.project_dir = Path(project_dir)  # normalize
        raw_branch = branch if branch is not None else get_current_branch(self.project_dir)
        self._branch = sanitize_branch_name(raw_branch)
        self._base = project_dir / ".harness" / "review-artifacts" / self._branch

    @property
    def branch(self) -> str:
        """sanitize된 브랜치명."""
        return self._branch

    @property
    def artifact_dir(self) -> Path:
        """산출물이 저장되는 디렉터리 경로."""
        return self._base

    def save(self, filename: str, content: str) -> Path:
        """산출물을 저장하고 경로를 반환한다."""
        self._validate_filename(filename)
        self._base.mkdir(parents=True, exist_ok=True)
        path = self._base / filename
        path.write_text(content, encoding="utf-8")
        logger.info("리뷰 산출물 저장: %s", path)
        return path

    def load(self, filename: str) -> str | None:
        """산출물을 읽어 반환한다. 없으면 None."""
        self._validate_filename(filename)
        path = self._base / filename
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def exists(self, filename: str) -> bool:
        """산출물이 존재하는지 확인한다."""
        self._validate_filename(filename)
        return (self._base / filename).exists()

    def list_artifacts(self) -> list[str]:
        """존재하는 산출물 파일명 목록을 반환한다."""
        if not self._base.exists():
            return []
        return sorted(p.name for p in self._base.iterdir() if p.is_file())
