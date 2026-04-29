"""ReviewArtifactManager 단위 테스트."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from harness.review.artifacts import (
    FALLBACK_BRANCH,
    ReviewArtifactManager,
    get_current_branch,
    sanitize_branch_name,
)


class TestSanitizeBranchName:
    def test_simple_name(self) -> None:
        assert sanitize_branch_name("main") == "main"

    def test_slash_replaced_with_hyphen(self) -> None:
        assert sanitize_branch_name("feature/my-feature") == "feature-my-feature"

    def test_nested_slash(self) -> None:
        assert sanitize_branch_name("release/2026/v1") == "release-2026-v1"

    def test_special_chars_removed(self) -> None:
        result = sanitize_branch_name("feat: add #123 thing!")
        assert " " not in result
        assert "#" not in result
        assert "!" not in result

    def test_consecutive_hyphens_collapsed(self) -> None:
        result = sanitize_branch_name("feat--double")
        assert "--" not in result

    def test_leading_trailing_hyphen_stripped(self) -> None:
        result = sanitize_branch_name("-leading-trailing-")
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_empty_string_returns_fallback(self) -> None:
        assert sanitize_branch_name("") == FALLBACK_BRANCH

    def test_only_special_chars_returns_fallback(self) -> None:
        assert sanitize_branch_name("!!!") == FALLBACK_BRANCH

    def test_dot_preserved(self) -> None:
        result = sanitize_branch_name("v1.2.3")
        assert "." in result

    def test_double_dot_collapsed(self) -> None:
        result = sanitize_branch_name("a..b")
        assert ".." not in result

    def test_path_traversal_neutralized(self) -> None:
        result = sanitize_branch_name("a/../../../etc")
        assert ".." not in result


class TestGetCurrentBranch:
    def test_returns_branch_on_success(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="feature/test\n", stderr=""
            )
            result = get_current_branch(tmp_path)
        assert result == "feature/test"

    def test_returns_fallback_on_empty_output(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="\n", stderr=""
            )
            result = get_current_branch(tmp_path)
        assert result == FALLBACK_BRANCH

    def test_returns_fallback_on_exception(self, tmp_path: Path) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = get_current_branch(tmp_path)
        assert result == FALLBACK_BRANCH

    def test_returns_fallback_on_timeout(self, tmp_path: Path) -> None:
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            result = get_current_branch(tmp_path)
        assert result == FALLBACK_BRANCH


class TestReviewArtifactManager:
    def test_init_with_explicit_branch(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="feature/foo")
        assert manager.branch == "feature-foo"

    def test_artifact_dir_path(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="main")
        expected = tmp_path / ".harness" / "review-artifacts" / "main"
        assert manager.artifact_dir == expected

    def test_save_creates_file(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="main")
        path = manager.save("design-intent.md", "# Test\nContent")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "# Test\nContent"

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="feature/new")
        manager.save("pr-body.md", "body")
        assert manager.artifact_dir.exists()

    def test_load_existing_file(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="main")
        manager.save("test.md", "hello")
        result = manager.load("test.md")
        assert result == "hello"

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="main")
        result = manager.load("does-not-exist.md")
        assert result is None

    def test_exists_true(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="main")
        manager.save("check.md", "x")
        assert manager.exists("check.md") is True

    def test_exists_false(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="main")
        assert manager.exists("missing.md") is False

    def test_list_artifacts_empty(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="main")
        assert manager.list_artifacts() == []

    def test_list_artifacts_sorted(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="main")
        manager.save("z.md", "z")
        manager.save("a.md", "a")
        manager.save("m.md", "m")
        assert manager.list_artifacts() == ["a.md", "m.md", "z.md"]

    def test_save_overwrites_existing(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="main")
        manager.save("file.md", "first")
        manager.save("file.md", "second")
        assert manager.load("file.md") == "second"

    def test_branch_property_sanitized(self, tmp_path: Path) -> None:
        manager = ReviewArtifactManager(tmp_path, branch="feat/weird#branch")
        assert "/" not in manager.branch
        assert "#" not in manager.branch

    @pytest.mark.parametrize(
        "branch,expected_contains",
        [
            ("main", "main"),
            ("feature/login", "feature-login"),
            ("release/v1.0", "release-v1.0"),
        ],
    )
    def test_various_branch_names(
        self, tmp_path: Path, branch: str, expected_contains: str
    ) -> None:
        manager = ReviewArtifactManager(tmp_path, branch=branch)
        assert expected_contains in str(manager.artifact_dir)
