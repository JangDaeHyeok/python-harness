"""scripts/run_harness.py CLI 옵션 연결 테스트."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from scripts import run_harness

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _disable_structure_gate() -> Iterator[None]:
    with patch("scripts.run_harness.enforce_structure_gate"):
        yield


def test_main_passes_worktree_options_to_config(tmp_path: Path) -> None:
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


def test_main_passes_headless_phase_options_to_config(tmp_path: Path) -> None:
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
                "--use-headless-phases",
                "--headless-phase-timeout",
                "1200",
                "--allow-empty-docs-diff",
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
    assert config.use_headless_phases is True
    assert config.headless_phase_timeout == 1200
    assert config.require_docs_diff_for_headless is False


def test_main_passes_auto_pr_options_to_pipeline(tmp_path: Path) -> None:
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
                "--auto-pr",
                "--pr-base",
                "develop",
                "--pr-title",
                "docs: sync cli docs",
                "--pr-number",
                "42",
                "--pr-no-poll",
                "--pr-skip-review",
                "문서를 맞춰줘",
            ],
        ),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
        patch("scripts.auto_pr_pipeline.run_pipeline") as mock_run_pipeline,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator
        mock_run_pipeline.return_value = MagicMock(
            pr_info=MagicMock(url="https://example.test/pr/42"),
            review_comments=[],
            actionable_comments=[],
            review_applied=False,
            replies_posted=0,
            merged=False,
            warnings=[],
            errors=[],
        )

        run_harness.main()

    mock_run_pipeline.assert_called_once_with(
        project_dir.resolve(),
        "develop",
        title="docs: sync cli docs",
        skip_review=True,
        auto_merge=False,
        poll_reviews=False,
        pr_number=42,
        current_pr=False,
        confirm_github_writes=False,
    )


def test_main_rejects_ambiguous_existing_pr_options() -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["run_harness.py", "--auto-pr", "--pr-number", "42", "--pr-current-pr", "수정"],
        ),
        pytest.raises(SystemExit),
    ):
        run_harness.main()


def test_main_passes_mode_to_config(tmp_path: Path) -> None:
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


def test_main_default_mode_is_create(tmp_path: Path) -> None:
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


def test_structure_gate_policy_only_enforces_existing_project_runs() -> None:
    assert run_harness.should_enforce_structure_gate("create", "") is False
    assert run_harness.should_enforce_structure_gate("modify", "") is True
    assert run_harness.should_enforce_structure_gate("create", "latest") is True


def test_modify_mode_defaults_to_current_dir(tmp_path: Path) -> None:
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


def test_create_mode_defaults_to_project_subdir(tmp_path: Path) -> None:
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
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


def test_main_allows_resume_without_prompt(tmp_path: Path) -> None:
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
