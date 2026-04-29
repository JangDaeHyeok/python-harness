"""CodeReviewer git diff 실패 처리 테스트."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from harness.sensors.inferential.code_reviewer import CodeReviewer


class TestGetDiff:
    def test_raises_on_nonzero_returncode(self, tmp_path: Path) -> None:
        reviewer = CodeReviewer(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr=""),
                subprocess.CompletedProcess(
                    args=[], returncode=128, stdout="", stderr="unknown revision"
                ),
            ]
            with pytest.raises(RuntimeError, match="unknown revision"):
                reviewer._get_diff("nonexistent-base")

    def test_raises_on_exception(self, tmp_path: Path) -> None:
        reviewer = CodeReviewer(str(tmp_path))
        with patch("subprocess.run", side_effect=OSError("git not found")), \
             pytest.raises(RuntimeError, match="실행 실패"):
            reviewer._get_diff("main")

    def test_returns_stdout_on_success(self, tmp_path: Path) -> None:
        reviewer = CodeReviewer(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="diff --git a/f.py b/f.py\n", stderr=""
                ),
            ]
            result = reviewer._get_diff("main")
        assert "diff --git" in result

    def test_falls_back_to_origin_base_when_local_base_missing(
        self, tmp_path: Path
    ) -> None:
        reviewer = CodeReviewer(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="diff --git a/f.py b/f.py\n", stderr=""
                ),
            ]

            result = reviewer._get_diff("main")

        assert "diff --git" in result
        assert mock_run.call_args_list[-1].args[0] == [
            "git",
            "diff",
            "origin/main...HEAD",
        ]


class TestGetStagedDiff:
    def test_raises_on_nonzero_returncode(self, tmp_path: Path) -> None:
        reviewer = CodeReviewer(str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="error"
            )
            with pytest.raises(RuntimeError, match="실패"):
                reviewer._get_staged_diff()

    def test_raises_on_exception(self, tmp_path: Path) -> None:
        reviewer = CodeReviewer(str(tmp_path))
        with patch("subprocess.run", side_effect=OSError("git not found")), \
             pytest.raises(RuntimeError, match="실행 실패"):
            reviewer._get_staged_diff()
