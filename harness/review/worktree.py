"""git worktree 기반 격리 실행 유틸리티.

사용자의 기존 변경사항을 건드리지 않도록 매우 보수적으로 구현한다.
dirty worktree면 실행을 중단하고, worktree 생성 실패 시 원본 디렉터리 fallback은 금지한다.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class WorktreeError(RuntimeError):
    """worktree 관련 오류."""


def _run_git(args: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str, str]:
    """git 명령을 실행하고 (returncode, stdout, stderr)를 반환한다."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def is_git_repository(project_dir: Path) -> bool:
    """디렉터리가 git 저장소 안에 있는지 확인한다."""
    rc, _, _ = _run_git(["rev-parse", "--is-inside-work-tree"], project_dir)
    return rc == 0


def is_worktree_dirty(project_dir: Path) -> bool:
    """작업 트리에 uncommitted 변경이 있는지 확인한다."""
    rc, stdout, _ = _run_git(["status", "--porcelain"], project_dir)
    if rc != 0:
        return True
    return bool(stdout.strip())


def _get_changed_paths(project_dir: Path, worktree_path: Path) -> list[str]:
    """worktree에서 변경/추가/삭제된 파일 경로 목록을 반환한다 (delta sync용)."""
    rc, stdout, _ = _run_git(["status", "--porcelain"], worktree_path)
    if rc != 0:
        return []
    paths: list[str] = []
    for line in stdout.splitlines():
        if len(line) > 3:
            paths.append(line[3:].strip())
    return paths


class WorktreeManager:
    """git worktree 기반 격리 실행 관리자.

    - 임시 worktree를 detached HEAD로 생성하여 기존 브랜치를 변경하지 않는다.
    - dirty worktree면 실행을 중단한다 (allow_dirty=True로 우회 가능).
    - worktree 생성 실패 시 WorktreeError를 발생시킨다 (원본 디렉터리 fallback 금지).
    - 위험한 git 명령(reset, checkout ., clean -f 등)은 사용하지 않는다.
    """

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self._worktree_path: Path | None = None

    def create_worktree(self) -> Path:
        """임시 worktree를 생성한다.

        Raises:
            WorktreeError: git 저장소가 아니거나 worktree 생성에 실패한 경우.
        """
        if not is_git_repository(self.project_dir):
            raise WorktreeError("git 저장소가 아닙니다.")

        tmp_dir = tempfile.mkdtemp(prefix="harness-wt-")
        worktree_path = Path(tmp_dir)

        rc, _, stderr = _run_git(
            ["worktree", "add", "--detach", str(worktree_path)],
            self.project_dir,
        )

        if rc != 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise WorktreeError(f"worktree 생성 실패: {stderr}")

        self._worktree_path = worktree_path
        logger.info("worktree 생성 완료: %s", worktree_path)
        return worktree_path

    def cleanup_worktree(self, worktree_path: Path) -> None:
        """worktree를 안전하게 정리한다. 실패해도 예외를 발생시키지 않는다."""
        if is_git_repository(self.project_dir):
            rc, _, stderr = _run_git(
                ["worktree", "remove", "--force", str(worktree_path)],
                self.project_dir,
            )
            if rc != 0:
                logger.warning("worktree 제거 실패: %s. 수동 삭제 시도.", stderr)
                shutil.rmtree(str(worktree_path), ignore_errors=True)
        else:
            shutil.rmtree(str(worktree_path), ignore_errors=True)

        if worktree_path == self._worktree_path:
            self._worktree_path = None

    def run_isolated(
        self,
        callback: Callable[[Path], list[Path]],
        preserve_to: Path | None = None,
        *,
        allow_dirty: bool = False,
    ) -> bool:
        """격리된 worktree에서 콜백을 실행하고 산출물을 보존한다.

        Args:
            callback: (worktree_path) -> list[생성된 파일 경로]
            preserve_to: 산출물을 복사할 대상 디렉터리 (None이면 복사 안 함)
            allow_dirty: True이면 dirty worktree에서도 실행 허용

        Returns:
            실행 성공 여부

        Raises:
            WorktreeError: dirty worktree이거나 worktree 생성 실패 시.
        """
        if not allow_dirty and is_worktree_dirty(self.project_dir):
            raise WorktreeError(
                "작업 트리에 uncommitted 변경이 있습니다. "
                "커밋하거나 allow_dirty=True를 사용하세요."
            )

        worktree_path = self.create_worktree()

        try:
            return self._run_callback(callback, worktree_path, preserve_to)
        finally:
            self.cleanup_worktree(worktree_path)

    def sync_artifacts(
        self,
        worktree_path: Path,
        preserve_to: Path,
        artifacts: list[Path],
    ) -> list[Path]:
        """변경된 산출물만 delta sync하고 충돌이 있으면 건너뛴다.

        Returns:
            실제로 복사된 파일 목록.
        """
        changed_relpaths = set(_get_changed_paths(self.project_dir, worktree_path))
        preserve_to.mkdir(parents=True, exist_ok=True)

        synced: list[Path] = []
        for artifact in artifacts:
            if not artifact.exists():
                continue

            try:
                relpath = str(artifact.relative_to(worktree_path))
            except ValueError:
                relpath = artifact.name

            if changed_relpaths and relpath not in changed_relpaths:
                logger.debug("변경 없음, 건너뜀: %s", relpath)
                continue

            dest = preserve_to / artifact.name
            if dest.exists():
                existing_content = dest.read_bytes()
                new_content = artifact.read_bytes()
                if existing_content != new_content:
                    logger.warning(
                        "충돌 감지, 덮어쓰기 건너뜀: %s (기존 로컬 변경 보존)", dest
                    )
                    continue

            shutil.copy2(str(artifact), str(dest))
            logger.info("산출물 동기화: %s → %s", artifact, dest)
            synced.append(dest)

        return synced

    def _run_callback(
        self,
        callback: Callable[[Path], list[Path]],
        work_dir: Path,
        preserve_to: Path | None,
    ) -> bool:
        try:
            artifacts = callback(work_dir)
            logger.info("실행 완료. 산출물: %d개", len(artifacts))

            if preserve_to and artifacts:
                self.sync_artifacts(work_dir, preserve_to, artifacts)
            return True
        except Exception as e:
            logger.error("실행 실패: %s", e)
            return False

    @property
    def active_worktree(self) -> Path | None:
        """현재 활성 worktree 경로. 없으면 None."""
        return self._worktree_path
