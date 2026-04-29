"""scripts/run_harness.py CLI 옵션 연결 테스트."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from scripts import run_harness


def test_main_passes_worktree_options_to_config(tmp_path) -> None:
    project_dir = tmp_path / "project"
    summary = {
        "title": "테스트",
        "passed_sprints": 1,
        "total_sprints": 1,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }

    with (
        patch.object(
            sys,
            "argv",
            [
                "run_harness.py",
                "--project-dir",
                str(project_dir),
                "--use-worktree",
                "--worktree-sync-exclude",
                "tmp",
                "--worktree-sync-exclude",
                "cache",
                "앱을 만들어줘",
            ],
        ),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator

        run_harness.main()

    config = mock_orchestrator_cls.call_args.args[0]
    assert config.use_worktree_isolation is True
    assert config.worktree_sync_excludes == ["tmp", "cache"]
    mock_orchestrator.run.assert_called_once_with("앱을 만들어줘", resume_run_id="")


def test_main_allows_resume_without_prompt(tmp_path) -> None:
    project_dir = tmp_path / "project"
    summary = {
        "title": "재개",
        "passed_sprints": 0,
        "total_sprints": 0,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }

    with (
        patch.object(
            sys,
            "argv",
            ["run_harness.py", "--project-dir", str(project_dir), "--resume"],
        ),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator

        run_harness.main()

    mock_orchestrator.run.assert_called_once_with("", resume_run_id="latest")
