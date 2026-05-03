"""orchestrator.py 통합 단위 테스트.

API 호출 없이 구조·동작·연결만 검증한다.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import ANY, MagicMock, patch

import pytest

from harness.agents.orchestrator import (
    HarnessConfig,
    HarnessOrchestrator,
    WorktreeChange,
    WorktreeSyncError,
)
from harness.context.modify_context import ModifyContext
from harness.review.worktree import WorktreeError

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# HarnessConfig
# ---------------------------------------------------------------------------

class TestHarnessConfig:
    def test_default_values(self) -> None:
        config = HarnessConfig(project_dir=".")
        assert config.model == "claude-sonnet-4-6"
        assert config.max_sprint_retries == 3
        assert config.max_total_sprints == 15
        assert config.app_url == "http://localhost:3000"
        assert config.enable_context_reset is True
        assert config.save_artifacts is True
        assert config.mode == "create"
        assert config.use_worktree_isolation is False
        assert config.worktree_sync_excludes == []
        assert config.use_headless_phases is False
        assert config.headless_phase_timeout == 600
        assert config.require_docs_diff_for_headless is True

    def test_worktree_flag(self) -> None:
        config = HarnessConfig(project_dir=".", use_worktree_isolation=True)
        assert config.use_worktree_isolation is True

    def test_custom_excludes(self) -> None:
        config = HarnessConfig(project_dir=".", worktree_sync_excludes=["tmp", "cache"])
        assert "tmp" in config.worktree_sync_excludes

    def test_modify_mode(self) -> None:
        config = HarnessConfig(project_dir=".", mode="modify")
        assert config.mode == "modify"

    def test_headless_phase_flag(self) -> None:
        config = HarnessConfig(
            project_dir=".",
            use_headless_phases=True,
            headless_phase_timeout=1200,
            require_docs_diff_for_headless=False,
        )
        assert config.use_headless_phases is True
        assert config.headless_phase_timeout == 1200
        assert config.require_docs_diff_for_headless is False


# ---------------------------------------------------------------------------
# headless phase implementation
# ---------------------------------------------------------------------------

class TestHeadlessPhaseImplementation:
    def _make_orch(self, project_dir: Path) -> HarnessOrchestrator:
        orch = HarnessOrchestrator.__new__(HarnessOrchestrator)
        orch.config = HarnessConfig(
            project_dir=str(project_dir),
            use_headless_phases=True,
            headless_phase_timeout=123,
            require_docs_diff_for_headless=True,
        )
        orch.project_dir = project_dir
        orch._phase_mgr = MagicMock()
        return orch

    def test_implement_with_headless_phases_returns_report(self, tmp_path: Path) -> None:
        orch = self._make_orch(tmp_path)

        with patch(
            "scripts.run_phases.run_sprint_phases",
            return_value={
                "phase-01-docs-update": "done",
                "phase-02-core-impl": "done",
            },
        ) as mock_run:
            report = orch._implement_with_headless_phases(1, attempt=1)

        mock_run.assert_called_once_with(
            tmp_path,
            1,
            timeout=123,
            require_docs_diff=True,
        )
        assert "phase-01-docs-update" in report
        orch._phase_mgr.reset_incomplete_phases.assert_not_called()

    def test_headless_retry_resets_incomplete_phases(self, tmp_path: Path) -> None:
        orch = self._make_orch(tmp_path)

        with patch(
            "scripts.run_phases.run_sprint_phases",
            return_value={"phase-01-docs-update": "done"},
        ):
            orch._implement_with_headless_phases(1, attempt=2)

        orch._phase_mgr.reset_incomplete_phases.assert_called_once_with(1)

    def test_headless_failed_status_raises(self, tmp_path: Path) -> None:
        orch = self._make_orch(tmp_path)

        with (
            patch(
                "scripts.run_phases.run_sprint_phases",
                return_value={"phase-01-docs-update": "failed"},
            ),
            pytest.raises(RuntimeError, match="failed=phase-01-docs-update"),
        ):
            orch._implement_with_headless_phases(1, attempt=1)


# ---------------------------------------------------------------------------
# resume helpers
# ---------------------------------------------------------------------------

class TestResumeHelpers:
    def test_is_sprint_done_uses_failed_done_state(self) -> None:
        from harness.context.checkpoint import SessionState, SprintState

        orch = HarnessOrchestrator.__new__(HarnessOrchestrator)
        orch._session = SessionState(
            run_id="run",
            user_prompt="prompt",
            sprints=[SprintState(sprint_number=1, done=True, passed=False)],
        )

        assert orch._is_sprint_done(1) is True
        assert orch._is_sprint_done(2) is False


# ---------------------------------------------------------------------------
# _sync_from_worktree
# ---------------------------------------------------------------------------

class TestSyncFromWorktree:
    def _make_orch_for_sync(self, project: Path) -> HarnessOrchestrator:
        config = HarnessConfig(project_dir=str(project))
        orch = HarnessOrchestrator.__new__(HarnessOrchestrator)
        orch.config = config
        orch.project_dir = project
        return orch

    def test_syncs_only_changed_files_via_git_diff(self, tmp_path: Path) -> None:
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        project = tmp_path / "project"
        project.mkdir()

        (worktree / "changed.py").write_text("new", encoding="utf-8")
        (worktree / "unchanged.py").write_text("old", encoding="utf-8")

        orch = self._make_orch_for_sync(project)

        diff_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="M\tchanged.py\n")
        untracked_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="")

        with (
            patch("subprocess.run", side_effect=[diff_result, untracked_result]),
            patch.object(orch, "_has_local_change", return_value=False),
        ):
            synced = orch._sync_from_worktree(worktree)

        assert synced == 1
        assert (project / "changed.py").exists()
        assert not (project / "unchanged.py").exists()

    def test_includes_untracked_files(self, tmp_path: Path) -> None:
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        project = tmp_path / "project"
        project.mkdir()

        (worktree / "tracked.py").write_text("t", encoding="utf-8")
        (worktree / "new_file.py").write_text("n", encoding="utf-8")

        orch = self._make_orch_for_sync(project)

        diff_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="M\ttracked.py\n")
        untracked_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="new_file.py\n")

        with (
            patch("subprocess.run", side_effect=[diff_result, untracked_result]),
            patch.object(orch, "_has_local_change", return_value=False),
        ):
            synced = orch._sync_from_worktree(worktree)

        assert synced == 2
        assert (project / "tracked.py").exists()
        assert (project / "new_file.py").exists()

    def test_fallback_to_full_copy_on_git_failure(self, tmp_path: Path) -> None:
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        project = tmp_path / "project"
        project.mkdir()

        (worktree / "foo.py").write_text("pass", encoding="utf-8")

        orch = self._make_orch_for_sync(project)

        fail_result = subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="not a repo")

        with (
            patch("subprocess.run", return_value=fail_result),
            patch.object(orch, "_has_local_change", return_value=False),
        ):
            synced = orch._sync_from_worktree(worktree)

        assert synced == 1
        assert (project / "foo.py").exists()

    def test_fallback_excludes_git_dir(self, tmp_path: Path) -> None:
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        project = tmp_path / "project"
        project.mkdir()

        git_dir = worktree / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]", encoding="utf-8")
        (worktree / "real.py").write_text("pass", encoding="utf-8")

        orch = self._make_orch_for_sync(project)

        with (
            patch("subprocess.run", side_effect=OSError("no git")),
            patch.object(orch, "_has_local_change", return_value=False),
        ):
            synced = orch._sync_from_worktree(worktree)

        assert synced == 1
        assert not (project / ".git").exists()

    def test_empty_worktree_returns_zero(self, tmp_path: Path) -> None:
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        project = tmp_path / "project"
        project.mkdir()

        orch = self._make_orch_for_sync(project)

        diff_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="")
        untracked_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="")

        with patch("subprocess.run", side_effect=[diff_result, untracked_result]):
            assert orch._sync_from_worktree(worktree) == 0

    def test_sync_deletes_removed_files(self, tmp_path: Path) -> None:
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        project = tmp_path / "project"
        project.mkdir()
        target = project / "removed.py"
        target.write_text("old", encoding="utf-8")

        orch = self._make_orch_for_sync(project)

        with patch.object(orch, "_has_local_change", return_value=False):
            synced = orch._sync_changed_files(
                worktree, [WorktreeChange("D", "removed.py")]
            )

        assert synced == 1
        assert not target.exists()

    def test_sync_refuses_to_overwrite_local_change(self, tmp_path: Path) -> None:
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        project = tmp_path / "project"
        project.mkdir()

        (worktree / "changed.py").write_text("worktree", encoding="utf-8")
        (project / "changed.py").write_text("local", encoding="utf-8")

        orch = self._make_orch_for_sync(project)

        with (
            patch.object(orch, "_has_local_change", return_value=True),
            pytest.raises(WorktreeSyncError, match="덮어쓸 수 없습니다"),
        ):
            orch._sync_changed_files(worktree, [WorktreeChange("M", "changed.py")])

        assert (project / "changed.py").read_text(encoding="utf-8") == "local"

    def test_sync_refuses_to_delete_local_change(self, tmp_path: Path) -> None:
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        project = tmp_path / "project"
        project.mkdir()
        target = project / "changed.py"
        target.write_text("local", encoding="utf-8")

        orch = self._make_orch_for_sync(project)

        with (
            patch.object(orch, "_has_local_change", return_value=True),
            pytest.raises(WorktreeSyncError, match="삭제할 수 없습니다"),
        ):
            orch._sync_changed_files(worktree, [WorktreeChange("D", "changed.py")])

        assert target.exists()


# ---------------------------------------------------------------------------
# _implement_in_worktree
# ---------------------------------------------------------------------------

class TestImplementInWorktree:
    def _make_orch(self, project_dir: Path) -> HarnessOrchestrator:
        """실제 API 없이 Orchestrator 인스턴스를 생성한다."""
        config = HarnessConfig(
            project_dir=str(project_dir), use_worktree_isolation=True
        )
        with (
            patch("harness.agents.orchestrator.PlannerAgent"),
            patch("harness.agents.orchestrator.GeneratorAgent"),
            patch("harness.agents.orchestrator.EvaluatorAgent"),
            patch("harness.agents.orchestrator.ReviewArtifactManager"),
            patch("harness.agents.orchestrator.ContractStore"),
            patch("harness.agents.orchestrator.CriteriaGenerator"),
            patch("harness.agents.orchestrator.IntentGenerator"),
            patch("harness.agents.orchestrator.WorktreeManager"),
            patch("harness.agents.orchestrator.CheckpointStore"),
        ):
            return HarnessOrchestrator(config)

    def test_dirty_worktree_raises(self, tmp_path: Path) -> None:
        orch = self._make_orch(tmp_path)

        with (
            patch("harness.agents.orchestrator.is_worktree_dirty", return_value=True),
            pytest.raises(WorktreeError, match="uncommitted"),
        ):
            orch._implement_in_worktree("spec", "contract", 1)

        orch._worktree_mgr.create_worktree.assert_not_called()  # type: ignore[union-attr]

    def test_no_fallback_when_worktree_fails(self, tmp_path: Path) -> None:
        orch = self._make_orch(tmp_path)

        orch._worktree_mgr.create_worktree.side_effect = RuntimeError("worktree failed")  # type: ignore[union-attr]
        orch.generator.implement_sprint.return_value = "구현 보고서"  # type: ignore[union-attr]

        with (
            patch("harness.agents.orchestrator.is_worktree_dirty", return_value=False),
            pytest.raises(RuntimeError, match="worktree failed"),
        ):
            orch._implement_in_worktree("spec", "contract", 1)

        orch.generator.implement_sprint.assert_not_called()  # type: ignore[union-attr]

    def test_uses_worktree_generator_when_available(self, tmp_path: Path) -> None:
        orch = self._make_orch(tmp_path)

        worktree_path = tmp_path / "wt"
        worktree_path.mkdir()
        orch._worktree_mgr.create_worktree.return_value = worktree_path  # type: ignore[union-attr]

        with (
            patch("harness.agents.orchestrator.is_worktree_dirty", return_value=False),
            patch("harness.agents.orchestrator.GeneratorAgent") as mock_gen_cls,
        ):
            mock_gen_instance = MagicMock()
            mock_gen_instance.implement_sprint.return_value = "wt 구현 보고서"
            mock_gen_instance._token_usage = {"input": 100, "output": 50}
            mock_gen_cls.return_value = mock_gen_instance

            # _sync_from_worktree mock
            orch._sync_from_worktree = MagicMock(return_value=5)  # type: ignore[method-assign]

            result = orch._implement_in_worktree("spec", "contract", 1)

        assert result == "wt 구현 보고서"
        orch._sync_from_worktree.assert_called_once_with(worktree_path, ANY)
        # merge_token_usage 호출 확인
        orch.generator.merge_token_usage.assert_called_once_with(mock_gen_instance)  # type: ignore[union-attr]

    def test_no_sync_on_exception(self, tmp_path: Path) -> None:
        orch = self._make_orch(tmp_path)

        worktree_path = tmp_path / "wt"
        worktree_path.mkdir()
        orch._worktree_mgr.create_worktree.return_value = worktree_path  # type: ignore[union-attr]

        with (
            patch("harness.agents.orchestrator.is_worktree_dirty", return_value=False),
            patch("harness.agents.orchestrator.GeneratorAgent") as mock_gen_cls,
        ):
            mock_gen_instance = MagicMock()
            mock_gen_instance.implement_sprint.side_effect = RuntimeError("API crash")
            mock_gen_cls.return_value = mock_gen_instance

            orch._sync_from_worktree = MagicMock(return_value=0)  # type: ignore[method-assign]

            with pytest.raises(RuntimeError, match="API crash"):
                orch._implement_in_worktree("spec", "contract", 1)

        # 예외 발생 시 동기화 호출 없음
        orch._sync_from_worktree.assert_not_called()
        # worktree는 항상 cleanup
        orch._worktree_mgr.cleanup_worktree.assert_called_once()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# criteria_md → evaluate_sprint 연결
# ---------------------------------------------------------------------------

class TestCriteriaMdConnection:
    def test_evaluate_sprint_receives_criteria_md(self, tmp_path: Path) -> None:
        """_execute_sprint()이 criteria_md를 evaluate_sprint()에 전달하는지 검증."""
        config = HarnessConfig(project_dir=str(tmp_path), save_artifacts=False)

        with (
            patch("harness.agents.orchestrator.PlannerAgent"),
            patch("harness.agents.orchestrator.GeneratorAgent") as mock_gen_cls,
            patch("harness.agents.orchestrator.EvaluatorAgent") as mock_eval_cls,
            patch("harness.agents.orchestrator.ReviewArtifactManager"),
            patch("harness.agents.orchestrator.ContractStore"),
            patch("harness.agents.orchestrator.CriteriaGenerator") as mock_criteria_cls,
            patch("harness.agents.orchestrator.IntentGenerator") as mock_intent_cls,
            patch("harness.agents.orchestrator.WorktreeManager"),
            patch("harness.agents.orchestrator.CheckpointStore"),
        ):
            from harness.agents.evaluator import EvaluationResult

            mock_gen = MagicMock()
            mock_gen.run.return_value = "스프린트 제안"
            mock_gen.implement_sprint.return_value = "구현 보고서"
            mock_gen._token_usage = {"input": 0, "output": 0}
            mock_gen_cls.return_value = mock_gen

            mock_eval = MagicMock()
            mock_eval.negotiate_contract.return_value = "스프린트 계약"
            passed_result = EvaluationResult(
                sprint_number=1,
                passed=True,
                overall_score=8.0,
                criteria_scores=[],
                bugs_found=[],
                summary="통과",
                detailed_feedback="",
            )
            mock_eval.evaluate_sprint.return_value = passed_result
            mock_eval_cls.return_value = mock_eval

            mock_criteria = MagicMock()
            mock_criteria.generate.return_value = []
            mock_criteria.to_markdown.return_value = "## 평가 기준\n- 테스트 커버리지"
            mock_criteria_cls.return_value = mock_criteria

            mock_intent = MagicMock()
            mock_intent.generate_from_spec.return_value = MagicMock()
            mock_intent.to_markdown.return_value = "## 설계 의도"
            mock_intent_cls.return_value = mock_intent

            orch = HarnessOrchestrator(config)

            sprint_info = {"number": 1, "name": "테스트 스프린트", "goal": "기본 CRUD 구현"}
            from harness.agents.planner import ProductSpec
            from harness.context.checkpoint import SessionState
            orch.spec = ProductSpec(
                title="테스트",
                description="",
                features=[],
                design_language={},
                tech_stack={},
                sprints=[sprint_info],
            )
            orch._session = SessionState(run_id="test", user_prompt="test")

            orch._execute_sprint(1, sprint_info)

            # evaluate_sprint 호출 시 criteria_md 인수가 전달됐는지 확인
            call_kwargs = mock_eval.evaluate_sprint.call_args
            assert call_kwargs is not None
            actual_criteria_md = call_kwargs.kwargs.get("criteria_md", "")
            assert actual_criteria_md.startswith("## 평가 기준\n- 테스트 커버리지")

    def test_criteria_md_none_when_generator_returns_empty(self, tmp_path: Path) -> None:
        """CriteriaGenerator가 빈 목록 반환 시 to_markdown 결과가 전달된다."""
        config = HarnessConfig(project_dir=str(tmp_path), save_artifacts=False)

        with (
            patch("harness.agents.orchestrator.PlannerAgent"),
            patch("harness.agents.orchestrator.GeneratorAgent") as mock_gen_cls,
            patch("harness.agents.orchestrator.EvaluatorAgent") as mock_eval_cls,
            patch("harness.agents.orchestrator.ReviewArtifactManager"),
            patch("harness.agents.orchestrator.ContractStore"),
            patch("harness.agents.orchestrator.CriteriaGenerator") as mock_criteria_cls,
            patch("harness.agents.orchestrator.IntentGenerator") as mock_intent_cls,
            patch("harness.agents.orchestrator.WorktreeManager"),
            patch("harness.agents.orchestrator.CheckpointStore"),
        ):
            from harness.agents.evaluator import EvaluationResult

            mock_gen = MagicMock()
            mock_gen.run.return_value = "제안"
            mock_gen.implement_sprint.return_value = "보고서"
            mock_gen._token_usage = {"input": 0, "output": 0}
            mock_gen_cls.return_value = mock_gen

            mock_eval = MagicMock()
            mock_eval.negotiate_contract.return_value = "계약"
            mock_eval.evaluate_sprint.return_value = EvaluationResult(
                sprint_number=1, passed=True, overall_score=7.0,
                criteria_scores=[], bugs_found=[], summary="", detailed_feedback="",
            )
            mock_eval_cls.return_value = mock_eval

            mock_criteria = MagicMock()
            mock_criteria.generate.return_value = []
            mock_criteria.to_markdown.return_value = ""  # 빈 문자열
            mock_criteria_cls.return_value = mock_criteria

            mock_intent = MagicMock()
            mock_intent.generate_from_spec.return_value = MagicMock()
            mock_intent.to_markdown.return_value = ""
            mock_intent_cls.return_value = mock_intent

            orch = HarnessOrchestrator(config)
            from harness.agents.planner import ProductSpec
            from harness.context.checkpoint import SessionState
            sprint_info = {"number": 1, "name": "Sprint", "goal": "goal"}
            orch.spec = ProductSpec(
                title="T", description="", features=[],
                design_language={}, tech_stack={}, sprints=[sprint_info],
            )
            orch._session = SessionState(run_id="test", user_prompt="test")

            orch._execute_sprint(1, sprint_info)

            # 빈 문자열이라도 키워드 인수로 전달됨
            call_kwargs = mock_eval.evaluate_sprint.call_args
            assert "criteria_md" in call_kwargs.kwargs


# ---------------------------------------------------------------------------
# Modify Mode
# ---------------------------------------------------------------------------

class TestModifyMode:
    def _make_modify_orch(self, project_dir: Path) -> HarnessOrchestrator:
        config = HarnessConfig(
            project_dir=str(project_dir), mode="modify", save_artifacts=False,
        )
        with (
            patch("harness.agents.orchestrator.PlannerAgent") as mock_planner_cls,
            patch("harness.agents.orchestrator.GeneratorAgent"),
            patch("harness.agents.orchestrator.EvaluatorAgent"),
            patch("harness.agents.orchestrator.ReviewArtifactManager"),
            patch("harness.agents.orchestrator.ContractStore"),
            patch("harness.agents.orchestrator.CriteriaGenerator"),
            patch("harness.agents.orchestrator.IntentGenerator"),
            patch("harness.agents.orchestrator.WorktreeManager"),
            patch("harness.agents.orchestrator.CheckpointStore"),
            patch("harness.agents.orchestrator.ModifyContextCollector"),
            patch("harness.agents.orchestrator.ProjectPolicyManager"),
        ):
            mock_planner_cls.return_value = MagicMock()
            orch = HarnessOrchestrator(config)
        return orch

    def test_plan_modify_collects_context(self, tmp_path: Path) -> None:
        orch = self._make_modify_orch(tmp_path)

        from harness.agents.planner import ProductSpec
        mock_spec = ProductSpec(
            title="수정 작업",
            description="기존 코드 수정",
            features=[],
            design_language={},
            tech_stack={},
            sprints=[{"number": 1, "name": "수정", "features": [], "goal": "수정"}],
        )
        orch.planner.run.return_value = mock_spec  # type: ignore[union-attr]

        mock_ctx = ModifyContext(git_branch="feature/test")
        orch._modify_ctx_collector.collect.return_value = mock_ctx  # type: ignore[union-attr]

        result = orch._plan_modify("기능 추가")

        assert result.title == "수정 작업"
        orch._modify_ctx_collector.collect.assert_called_once()  # type: ignore[union-attr]
        call_args = orch.planner.run.call_args  # type: ignore[union-attr]
        assert "수정 요청" in call_args.args[0]
        assert "기능 추가" in call_args.args[0]

    def test_modify_mode_sprint_adds_hint(self, tmp_path: Path) -> None:
        """modify 모드에서 스프린트 구현 시 수정 모드 힌트가 계약에 추가되는지 검증."""
        config = HarnessConfig(
            project_dir=str(tmp_path), mode="modify", save_artifacts=False,
        )

        with (
            patch("harness.agents.orchestrator.PlannerAgent"),
            patch("harness.agents.orchestrator.GeneratorAgent") as mock_gen_cls,
            patch("harness.agents.orchestrator.EvaluatorAgent") as mock_eval_cls,
            patch("harness.agents.orchestrator.ReviewArtifactManager"),
            patch("harness.agents.orchestrator.ContractStore"),
            patch("harness.agents.orchestrator.CriteriaGenerator") as mock_criteria_cls,
            patch("harness.agents.orchestrator.IntentGenerator") as mock_intent_cls,
            patch("harness.agents.orchestrator.WorktreeManager"),
            patch("harness.agents.orchestrator.CheckpointStore"),
            patch("harness.agents.orchestrator.ModifyContextCollector"),
            patch("harness.agents.orchestrator.ProjectPolicyManager"),
        ):
            from harness.agents.evaluator import EvaluationResult

            mock_gen = MagicMock()
            mock_gen.run.return_value = "제안"
            mock_gen.implement_sprint.return_value = "보고서"
            mock_gen._token_usage = {"input": 0, "output": 0}
            mock_gen_cls.return_value = mock_gen

            mock_eval = MagicMock()
            mock_eval.negotiate_contract.return_value = "계약"
            mock_eval.evaluate_sprint.return_value = EvaluationResult(
                sprint_number=1, passed=True, overall_score=8.0,
                criteria_scores=[], bugs_found=[], summary="", detailed_feedback="",
            )
            mock_eval_cls.return_value = mock_eval

            mock_criteria = MagicMock()
            mock_criteria.generate.return_value = []
            mock_criteria.to_markdown.return_value = ""
            mock_criteria_cls.return_value = mock_criteria

            mock_intent = MagicMock()
            mock_intent.generate_from_spec.return_value = MagicMock()
            mock_intent.to_markdown.return_value = ""
            mock_intent_cls.return_value = mock_intent

            orch = HarnessOrchestrator(config)

            from harness.agents.planner import ProductSpec
            from harness.context.checkpoint import SessionState
            sprint_info = {"number": 1, "name": "수정", "goal": "코드 수정"}
            orch.spec = ProductSpec(
                title="T", description="", features=[],
                design_language={}, tech_stack={}, sprints=[sprint_info],
            )
            orch._session = SessionState(run_id="test", user_prompt="test")

            orch._execute_sprint(1, sprint_info)

            # Generator의 implement_sprint에 수정 모드 힌트가 포함되었는지 확인
            impl_call = mock_gen.implement_sprint.call_args
            contract_arg = impl_call.args[1]
            assert "수정 모드" in contract_arg

    def test_worktree_generator_receives_modify_mode(self, tmp_path: Path) -> None:
        """--mode modify --use-worktree 조합에서 worktree Generator에 mode가 전달되는지 검증."""
        config = HarnessConfig(
            project_dir=str(tmp_path), mode="modify",
            use_worktree_isolation=True, save_artifacts=False,
        )

        captured: list[dict] = []

        def fake_gen_init(self_inner: object, **kwargs: object) -> None:
            captured.append(dict(kwargs))

        with (
            patch("harness.agents.orchestrator.PlannerAgent"),
            patch("harness.agents.orchestrator.GeneratorAgent"),
            patch("harness.agents.orchestrator.EvaluatorAgent"),
            patch("harness.agents.orchestrator.ReviewArtifactManager"),
            patch("harness.agents.orchestrator.ContractStore"),
            patch("harness.agents.orchestrator.CriteriaGenerator"),
            patch("harness.agents.orchestrator.IntentGenerator"),
            patch("harness.agents.orchestrator.WorktreeManager"),
            patch("harness.agents.orchestrator.CheckpointStore"),
            patch("harness.agents.orchestrator.ModifyContextCollector"),
            patch("harness.agents.orchestrator.ProjectPolicyManager"),
            patch("harness.agents.orchestrator.is_worktree_dirty", return_value=False),
            patch("harness.agents.orchestrator.GeneratorAgent") as mock_gen_cls,
        ):
            wt_gen = MagicMock()
            wt_gen.implement_sprint.return_value = "보고서"
            wt_gen._token_usage = {"input": 0, "output": 0}
            mock_gen_cls.return_value = wt_gen

            orch = HarnessOrchestrator(config)
            worktree_path = tmp_path / "wt"
            worktree_path.mkdir()

            with (
                patch.object(orch, "_get_head_commit", return_value="abc123"),
                patch.object(orch._worktree_mgr, "create_worktree", return_value=worktree_path),
                patch.object(orch, "_sync_from_worktree", return_value=0),
                patch.object(orch, "_worktree_mgr"),
            ):
                orch._worktree_mgr.create_worktree.return_value = worktree_path
                orch._implement_in_worktree("spec", "contract", 1)

            # worktree 용 GeneratorAgent 생성 시 mode="modify"가 전달되어야 한다
            init_kwargs = mock_gen_cls.call_args_list[-1]
            assert init_kwargs.kwargs.get("mode") == "modify"
