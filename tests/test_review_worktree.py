"""WorktreeManager 단위 테스트."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from harness.review.worktree import (
    WorktreeError,
    WorktreeManager,
    is_git_repository,
    is_worktree_dirty,
)


class TestIsGitRepository:
    def test_returns_false_for_plain_dir(self, tmp_path: Path) -> None:
        result = is_git_repository(tmp_path)
        assert result is False

    def test_returns_true_when_git_available(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="true\n", stderr=""
            )
            result = is_git_repository(tmp_path)
        assert result is True

    def test_returns_false_on_nonzero_returncode(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr="not a git repo"
            )
            result = is_git_repository(tmp_path)
        assert result is False

    def test_returns_false_on_exception(self, tmp_path: Path) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = is_git_repository(tmp_path)
        assert result is False


class TestIsWorktreeDirty:
    def test_clean_worktree(self, tmp_path: Path) -> None:
        with patch("harness.review.worktree._run_git", return_value=(0, "", "")):
            assert is_worktree_dirty(tmp_path) is False

    def test_dirty_worktree(self, tmp_path: Path) -> None:
        with patch("harness.review.worktree._run_git", return_value=(0, " M foo.py", "")):
            assert is_worktree_dirty(tmp_path) is True

    def test_git_failure_treated_as_dirty(self, tmp_path: Path) -> None:
        with patch("harness.review.worktree._run_git", return_value=(1, "", "error")):
            assert is_worktree_dirty(tmp_path) is True


class TestWorktreeManager:
    def test_create_worktree_raises_when_not_git_repo(
        self, tmp_path: Path
    ) -> None:
        manager = WorktreeManager(tmp_path)
        with pytest.raises(WorktreeError, match="git 저장소"):
            manager.create_worktree()

    def test_create_worktree_raises_on_git_failure(self, tmp_path: Path) -> None:
        manager = WorktreeManager(tmp_path)
        with patch("harness.review.worktree.is_git_repository", return_value=True), \
             patch("harness.review.worktree._run_git", return_value=(1, "", "lock exists")), \
             pytest.raises(WorktreeError, match="lock exists"):
            manager.create_worktree()

    def test_active_worktree_initially_none(self, tmp_path: Path) -> None:
        manager = WorktreeManager(tmp_path)
        assert manager.active_worktree is None

    def test_run_isolated_raises_on_dirty_worktree(self, tmp_path: Path) -> None:
        manager = WorktreeManager(tmp_path)
        with patch("harness.review.worktree.is_worktree_dirty", return_value=True), \
             pytest.raises(WorktreeError, match="uncommitted"):
            manager.run_isolated(lambda p: [])

    def test_run_isolated_allows_dirty_when_flag_set(self, tmp_path: Path) -> None:
        fake_worktree = tmp_path / "fake-wt"
        fake_worktree.mkdir()

        manager = WorktreeManager(tmp_path)
        with patch("harness.review.worktree.is_worktree_dirty", return_value=True), \
             patch.object(manager, "create_worktree", return_value=fake_worktree), \
             patch.object(manager, "cleanup_worktree"):
            success = manager.run_isolated(lambda p: [], allow_dirty=True)
        assert success is True

    def test_run_isolated_no_fallback_on_create_failure(self, tmp_path: Path) -> None:
        """worktree 생성 실패 시 원본 디렉터리 fallback 없이 예외를 전파한다."""
        manager = WorktreeManager(tmp_path)
        with patch("harness.review.worktree.is_worktree_dirty", return_value=False), \
             patch.object(manager, "create_worktree", side_effect=WorktreeError("생성 실패")), \
             pytest.raises(WorktreeError, match="생성 실패"):
            manager.run_isolated(lambda p: [])

    def test_run_isolated_returns_false_on_callback_exception(
        self, tmp_path: Path
    ) -> None:
        fake_worktree = tmp_path / "fake-wt"
        fake_worktree.mkdir()

        def failing_callback(work_dir: Path) -> list[Path]:
            raise RuntimeError("콜백 실패")

        manager = WorktreeManager(tmp_path)
        with patch("harness.review.worktree.is_worktree_dirty", return_value=False), \
             patch.object(manager, "create_worktree", return_value=fake_worktree), \
             patch.object(manager, "cleanup_worktree"):
            success = manager.run_isolated(failing_callback)
        assert success is False

    def test_run_isolated_with_worktree_success(self, tmp_path: Path) -> None:
        fake_worktree = tmp_path / "fake-wt"
        fake_worktree.mkdir()

        def my_callback(work_dir: Path) -> list[Path]:
            f = work_dir / "output.md"
            f.write_text("output", encoding="utf-8")
            return [f]

        manager = WorktreeManager(tmp_path)

        with patch("harness.review.worktree.is_worktree_dirty", return_value=False), \
             patch.object(manager, "create_worktree", return_value=fake_worktree), \
             patch.object(manager, "cleanup_worktree"):
            success = manager.run_isolated(my_callback)

        assert success is True

    def test_cleanup_called_even_on_exception(self, tmp_path: Path) -> None:
        fake_worktree = tmp_path / "fake-wt"
        fake_worktree.mkdir()
        cleanup_called: list[Path] = []

        def my_callback(work_dir: Path) -> list[Path]:
            raise ValueError("의도적 실패")

        manager = WorktreeManager(tmp_path)

        with patch("harness.review.worktree.is_worktree_dirty", return_value=False), \
             patch.object(manager, "create_worktree", return_value=fake_worktree), \
             patch.object(manager, "cleanup_worktree", side_effect=lambda p: cleanup_called.append(p)):
            success = manager.run_isolated(my_callback)

        assert success is False
        assert len(cleanup_called) == 1

    def test_cleanup_worktree_noop_on_nonexistent(self, tmp_path: Path) -> None:
        manager = WorktreeManager(tmp_path)
        nonexistent = tmp_path / "does-not-exist"
        manager.cleanup_worktree(nonexistent)


class TestSyncArtifacts:
    def test_delta_sync_only_changed_files(self, tmp_path: Path) -> None:
        """변경된 파일만 동기화된다."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        dest = tmp_path / "dest"

        changed = worktree / "changed.md"
        changed.write_text("new content", encoding="utf-8")
        unchanged = worktree / "unchanged.md"
        unchanged.write_text("old content", encoding="utf-8")

        manager = WorktreeManager(tmp_path)
        with patch("harness.review.worktree._get_changed_paths", return_value=["changed.md"]):
            synced = manager.sync_artifacts(worktree, dest, [changed, unchanged])

        assert len(synced) == 1
        assert synced[0].name == "changed.md"

    def test_conflict_detection_skips_differing_existing(self, tmp_path: Path) -> None:
        """대상에 다른 내용의 파일이 있으면 덮어쓰지 않는다."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()

        artifact = worktree / "report.md"
        artifact.write_text("worktree version", encoding="utf-8")
        existing = dest / "report.md"
        existing.write_text("local version", encoding="utf-8")

        manager = WorktreeManager(tmp_path)
        with patch("harness.review.worktree._get_changed_paths", return_value=["report.md"]):
            synced = manager.sync_artifacts(worktree, dest, [artifact])

        assert len(synced) == 0
        assert existing.read_text(encoding="utf-8") == "local version"

    def test_overwrites_identical_existing(self, tmp_path: Path) -> None:
        """대상에 동일한 내용의 파일이 있으면 정상 동기화한다."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()

        artifact = worktree / "report.md"
        artifact.write_text("same content", encoding="utf-8")
        existing = dest / "report.md"
        existing.write_text("same content", encoding="utf-8")

        manager = WorktreeManager(tmp_path)
        with patch("harness.review.worktree._get_changed_paths", return_value=["report.md"]):
            synced = manager.sync_artifacts(worktree, dest, [artifact])

        assert len(synced) == 1

    def test_skips_nonexistent_artifacts(self, tmp_path: Path) -> None:
        worktree = tmp_path / "wt"
        worktree.mkdir()
        dest = tmp_path / "dest"

        nonexistent = worktree / "missing.md"
        manager = WorktreeManager(tmp_path)
        with patch("harness.review.worktree._get_changed_paths", return_value=[]):
            synced = manager.sync_artifacts(worktree, dest, [nonexistent])

        assert len(synced) == 0

    def test_syncs_all_when_no_changed_paths(self, tmp_path: Path) -> None:
        """changed_paths가 비어 있으면 모든 존재하는 산출물을 동기화한다."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        dest = tmp_path / "dest"

        a = worktree / "a.md"
        a.write_text("a", encoding="utf-8")
        b = worktree / "b.md"
        b.write_text("b", encoding="utf-8")

        manager = WorktreeManager(tmp_path)
        with patch("harness.review.worktree._get_changed_paths", return_value=[]):
            synced = manager.sync_artifacts(worktree, dest, [a, b])

        assert len(synced) == 2
