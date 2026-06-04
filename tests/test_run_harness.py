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
            pr_info=MagicMock(url="https://example.test/pr/42", number=42),
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


def _auto_pr_argv(project_dir: Path, *extra: str) -> list[str]:
    return [
        "run_harness.py",
        "--project-dir",
        str(project_dir),
        "--auto-pr",
        *extra,
        "수정해줘",
    ]


def _pipeline_result(errors: list[str]) -> MagicMock:
    return MagicMock(
        pr_info=MagicMock(url="https://example.test/pr/1", number=1),
        review_comments=[],
        actionable_comments=[],
        review_applied=False,
        replies_posted=0,
        merged=False,
        warnings=[],
        errors=errors,
    )


def test_auto_pr_records_artifact(tmp_path: Path) -> None:
    """PR 자동화 결과는 별도 artifact로 기록된다."""
    project_dir = tmp_path / "project"
    summary = {
        "title": "수정",
        "passed_sprints": 1,
        "total_sprints": 1,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }

    with (
        patch.object(sys, "argv", _auto_pr_argv(project_dir)),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
        patch("scripts.auto_pr_pipeline.run_pipeline") as mock_run_pipeline,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator
        mock_run_pipeline.return_value = _pipeline_result(errors=[])

        run_harness.main()

    artifact = project_dir.resolve() / ".harness" / "artifacts" / "auto-pr-result.json"
    assert artifact.exists()


def test_auto_pr_errors_exit_nonzero_with_flag(tmp_path: Path) -> None:
    """--fail-on-pr-error 사용 시 PR 오류가 있으면 종료 코드 1."""
    project_dir = tmp_path / "project"
    summary = {
        "title": "수정",
        "passed_sprints": 1,
        "total_sprints": 1,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }

    with (
        patch.object(sys, "argv", _auto_pr_argv(project_dir, "--fail-on-pr-error")),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
        patch("scripts.auto_pr_pipeline.run_pipeline") as mock_run_pipeline,
        pytest.raises(SystemExit) as exc_info,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator
        mock_run_pipeline.return_value = _pipeline_result(errors=["push 실패: x"])

        run_harness.main()

    assert exc_info.value.code == 1


def test_auto_pr_errors_exit_zero_without_flag(tmp_path: Path) -> None:
    """플래그 없으면 PR 오류가 있어도 종료 코드 0(기록만)."""
    project_dir = tmp_path / "project"
    summary = {
        "title": "수정",
        "passed_sprints": 1,
        "total_sprints": 1,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }

    with (
        patch.object(sys, "argv", _auto_pr_argv(project_dir)),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
        patch("scripts.auto_pr_pipeline.run_pipeline") as mock_run_pipeline,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator
        mock_run_pipeline.return_value = _pipeline_result(errors=["push 실패: x"])

        run_harness.main()

    artifact = project_dir.resolve() / ".harness" / "artifacts" / "auto-pr-result.json"
    assert artifact.exists()


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


def test_fix_subcommand_runs_modify_mode(tmp_path: Path) -> None:
    """`harness fix`는 modify 모드로 위임하고 프롬프트를 그대로 전달한다."""
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
            ["harness", "fix", "--project-dir", str(project_dir), "로그인 에러 개선"],
        ),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator

        run_harness.main()

    config = mock_orchestrator_cls.call_args.args[0]
    assert config.mode == "modify"
    assert config.use_headless_phases is False
    mock_orchestrator.run.assert_called_once_with("로그인 에러 개선", resume_run_id="")


def test_fix_headless_flag_enables_phases_and_relaxes_docs_diff() -> None:
    """`harness fix --headless`는 헤드리스 Phase + docs-diff 완화로 매핑된다."""
    argv = run_harness._build_fix_argv(["--headless", "리팩터링"])
    assert "--use-headless-phases" in argv
    assert "--allow-empty-docs-diff" in argv
    assert argv[:2] == ["--mode", "modify"]
    assert argv[-1] == "리팩터링"


def test_ship_argv_enables_pr_automation_without_github_writes() -> None:
    """`harness ship`은 구현→PR→리뷰 반영까지만 자동화한다.

    머지/리뷰 답글 같은 GitHub 쓰기 명시 승인 플래그는 정책상 자동 주입하지 않는다.
    """
    argv = run_harness._build_ship_argv(["로그인 에러 개선"])
    assert argv[:2] == ["--mode", "modify"]
    for flag in (
        "--use-headless-phases",
        "--allow-empty-docs-diff",
        "--auto-pr",
    ):
        assert flag in argv
    assert "--pr-auto-merge" not in argv
    assert "--pr-confirm-github-writes" not in argv
    assert argv[-1] == "로그인 에러 개선"


def test_ship_argv_forwards_explicit_merge_optin() -> None:
    """머지까지 원하면 사용자가 명시 승인 플래그를 직접 덧붙일 수 있다."""
    argv = run_harness._build_ship_argv(
        ["--pr-auto-merge", "--pr-confirm-github-writes", "수정"]
    )
    assert "--pr-auto-merge" in argv
    assert "--pr-confirm-github-writes" in argv


def test_ship_argv_allows_pr_base_override() -> None:
    """`harness ship --pr-base develop`은 기본 main을 뒤에서 덮어쓸 수 있다."""
    argv = run_harness._build_ship_argv(["--pr-base", "develop", "수정"])
    assert argv.count("--pr-base") == 2
    assert argv[-3:] == ["--pr-base", "develop", "수정"]


def test_ship_argv_drops_redundant_headless_flag() -> None:
    """`harness ship`은 이미 헤드리스이므로 중복 `--headless`를 제거한다."""
    argv = run_harness._build_ship_argv(["--headless", "수정"])
    assert "--headless" not in argv
    assert argv[-1] == "수정"


def test_reserved_word_prompt_via_double_dash(tmp_path: Path) -> None:
    """`harness -- fix`는 예약어를 서브커맨드가 아닌 create 프롬프트로 전달한다."""
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
            ["harness", "--project-dir", str(project_dir), "--", "fix"],
        ),
        patch("scripts.run_harness.HarnessOrchestrator") as mock_orchestrator_cls,
    ):
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = summary
        mock_orchestrator_cls.return_value = mock_orchestrator

        run_harness.main()

    config = mock_orchestrator_cls.call_args.args[0]
    assert config.mode == "create"
    mock_orchestrator.run.assert_called_once_with("fix", resume_run_id="")


def _capture_delegated_argv(target: str, argv: list[str]) -> list[str]:
    """서브커맨드 위임 시 위임 대상 main()에 전달되는 argv를 캡처한다."""
    captured: list[str] = []

    def _record(passed_argv: list[str] | None = None) -> None:
        captured.extend(passed_argv or [])

    with (
        patch.object(sys, "argv", argv),
        patch(target, side_effect=_record),
    ):
        run_harness.main()
    return captured


def test_doctor_subcommand_delegates() -> None:
    """`harness doctor`는 harness-doctor 엔트리포인트로 위임한다."""
    captured = _capture_delegated_argv(
        "scripts.doctor.main", ["harness", "doctor", "--project-dir", "."]
    )
    assert captured == ["--project-dir", "."]


def test_init_subcommand_delegates() -> None:
    """`harness init`은 harness-init 엔트리포인트로 위임한다."""
    captured = _capture_delegated_argv(
        "scripts.init_harness.main", ["harness", "init", "결제 서비스"]
    )
    assert captured == ["결제 서비스"]


def test_pr_subcommand_delegates_without_injection() -> None:
    """`harness pr`은 auto-pr-pipeline에 인자를 그대로 위임한다."""
    captured = _capture_delegated_argv(
        "scripts.auto_pr_pipeline.main", ["harness", "pr", "--base", "develop"]
    )
    assert captured == ["--base", "develop"]


def test_review_subcommand_injects_current_pr() -> None:
    """`harness review`는 --current-pr 프리셋을 주입한다."""
    captured = _capture_delegated_argv(
        "scripts.auto_pr_pipeline.main", ["harness", "review"]
    )
    assert captured == ["--current-pr"]


def test_review_subcommand_skips_injection_when_pr_number_given() -> None:
    """`harness review --pr-number N`은 --current-pr를 주입하지 않는다."""
    assert run_harness._build_review_argv(["--pr-number", "7"]) == ["--pr-number", "7"]


def test_review_subcommand_skips_injection_when_pr_number_uses_equals() -> None:
    """`harness review --pr-number=N`(argparse 표준형)도 주입을 건너뛴다."""
    assert run_harness._build_review_argv(["--pr-number=7"]) == ["--pr-number=7"]


def test_dispatch_subcommand_does_not_mutate_sys_argv() -> None:
    """위임은 argv를 인자로 전달하므로 전역 sys.argv를 건드리지 않는다."""
    sentinel = ["harness", "review"]
    with (
        patch.object(sys, "argv", list(sentinel)),
        patch("scripts.auto_pr_pipeline.main") as mock_main,
    ):
        run_harness._dispatch_subcommand("review", [])
        assert sys.argv == sentinel
    mock_main.assert_called_once_with(["--current-pr"])


def test_as_int_narrows_supported_types() -> None:
    """passed/total 합산값을 안전하게 int로 좁히고, 비수치형은 0으로 폴백한다."""
    assert run_harness._as_int(3) == 3
    assert run_harness._as_int(2.0) == 2
    assert run_harness._as_int(None) == 0
    assert run_harness._as_int("nope") == 0


def _summary(passed: int = 1, total: int = 1) -> dict[str, object]:
    return {
        "title": "테스트",
        "passed_sprints": passed,
        "total_sprints": total,
        "total_cost_usd": 0.0,
        "elapsed_human": "0분",
    }


def test_print_completion_pr_hint_uses_project_dir_when_not_cwd(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """project_dir가 cwd가 아니면 --project-dir를 포함한 정확한 명령을 안내한다."""
    project_dir = tmp_path / "app"
    with patch("scripts.run_harness._changed_files", return_value=[]):
        run_harness._print_completion(
            project_dir,
            _summary(),
            mode="modify",
            auto_pr_enabled=False,
            headless=False,
            verbose=False,
        )
    out = capsys.readouterr().out
    assert f"harness pr --project-dir {project_dir}" in out


def test_print_completion_pr_hint_short_form_when_cwd(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """project_dir가 cwd면 짧은 'harness pr' 안내만 출력한다."""
    with patch("scripts.run_harness._changed_files", return_value=[]):
        run_harness._print_completion(
            Path.cwd(),
            _summary(),
            mode="modify",
            auto_pr_enabled=False,
            headless=False,
            verbose=False,
        )
    out = capsys.readouterr().out
    assert "'harness pr' 로" in out
    assert "--project-dir" not in out


def test_print_completion_pr_hint_skipped_in_create_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """create 모드에서는 harness pr 안내를 출력하지 않는다."""
    with patch("scripts.run_harness._changed_files", return_value=[]):
        run_harness._print_completion(
            tmp_path / "app",
            _summary(),
            mode="create",
            auto_pr_enabled=False,
            headless=False,
            verbose=False,
        )
    out = capsys.readouterr().out
    assert "harness pr" not in out


def test_changed_files_returns_empty_on_git_failure(tmp_path: Path) -> None:
    """git 실행이 실패하면 변경 파일 목록은 빈 리스트로 폴백한다."""
    from harness.tools.shell import CommandResult

    failure = CommandResult(
        ["git", "status"], returncode=128, error_message="not a repo"
    )
    with patch("harness.tools.shell.run_argv_safe", return_value=failure):
        assert run_harness._changed_files(tmp_path) == []


def test_changed_files_parses_porcelain(tmp_path: Path) -> None:
    """porcelain 출력(result.stdout)에서 파일 경로를 추출한다."""
    from harness.tools.shell import CommandResult

    result = CommandResult(
        ["git", "status"],
        returncode=0,
        stdout=" M src/auth.py\n?? new_file.py\n",
    )
    with patch("harness.tools.shell.run_argv_safe", return_value=result):
        assert run_harness._changed_files(tmp_path) == ["src/auth.py", "new_file.py"]
