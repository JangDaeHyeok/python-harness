"""scripts/run_harness.py CLI 옵션 연결 테스트."""

from __future__ import annotations

import sys
from pathlib import Path
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


def test_main_passes_mode_to_config(tmp_path) -> None:
    project_dir = tmp_path / "project"
    summary = {
        "title": "수정",
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
                "--mode",
                "modify",
                "기존 코드를 수정해줘",
            ],
        ),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator

        run_harness.main()

    config = mock_orchestrator_cls.call_args.args[0]
    assert config.mode == "modify"


def test_main_default_mode_is_create(tmp_path) -> None:
    project_dir = tmp_path / "project"
    summary = {
        "title": "생성",
        "passed_sprints": 1,
        "total_sprints": 1,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }

    with (
        patch.object(
            sys,
            "argv",
            ["run_harness.py", "--project-dir", str(project_dir), "앱을 만들어줘"],
        ),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator

        run_harness.main()

    config = mock_orchestrator_cls.call_args.args[0]
    assert config.mode == "create"


def test_modify_mode_defaults_to_current_dir(tmp_path) -> None:
    """--mode modify에서 --project-dir 미지정 시 현재 디렉터리를 사용한다."""
    summary = {
        "title": "수정",
        "passed_sprints": 1,
        "total_sprints": 1,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }

    with (
        patch.object(
            sys,
            "argv",
            ["run_harness.py", "--mode", "modify", "기능 추가"],
        ),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator

        run_harness.main()

    config = mock_orchestrator_cls.call_args.args[0]
    assert config.project_dir == str(Path(".").resolve())
    assert config.mode == "modify"


def test_create_mode_defaults_to_project_subdir(tmp_path) -> None:
    """--mode create에서 --project-dir 미지정 시 ./project를 사용한다."""
    summary = {
        "title": "생성",
        "passed_sprints": 1,
        "total_sprints": 1,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }

    with (
        patch.object(
            sys,
            "argv",
            ["run_harness.py", "앱을 만들어줘"],
        ),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator

        run_harness.main()

    config = mock_orchestrator_cls.call_args.args[0]
    assert config.project_dir == str(Path("./project"))


def test_resume_defaults_to_current_dir_when_current_checkpoint_exists(
    tmp_path, monkeypatch,
) -> None:
    """modify 실행의 자연스러운 --resume은 현재 디렉터리 체크포인트를 우선한다."""
    (tmp_path / ".harness" / "checkpoints").mkdir(parents=True)
    (tmp_path / ".harness" / "checkpoints" / "latest.json").write_text(
        '{"run_id": "abc123"}', encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    summary = {
        "title": "재개",
        "passed_sprints": 0,
        "total_sprints": 0,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }

    with (
        patch.object(sys, "argv", ["run_harness.py", "--resume"]),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator

        run_harness.main()

    config = mock_orchestrator_cls.call_args.args[0]
    assert config.project_dir == str(tmp_path)
    assert config.mode == "modify"
    mock_orchestrator.run.assert_called_once_with("", resume_run_id="latest")


def test_run_id_defaults_to_current_dir_when_current_checkpoint_exists(
    tmp_path, monkeypatch,
) -> None:
    """--run-id도 현재 디렉터리의 해당 체크포인트를 찾아 modify로 재개한다."""
    (tmp_path / ".harness" / "checkpoints").mkdir(parents=True)
    (tmp_path / ".harness" / "checkpoints" / "abc123.json").write_text(
        "{}", encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    summary = {
        "title": "재개",
        "passed_sprints": 0,
        "total_sprints": 0,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }

    with (
        patch.object(sys, "argv", ["run_harness.py", "--run-id", "abc123"]),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator

        run_harness.main()

    config = mock_orchestrator_cls.call_args.args[0]
    assert config.project_dir == str(tmp_path)
    assert config.mode == "modify"
    mock_orchestrator.run.assert_called_once_with("", resume_run_id="abc123")


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
