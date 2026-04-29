"""harness/context/checkpoint 모듈 단위 테스트."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from harness.context.checkpoint import (
    AttemptState,
    CheckpointStore,
    Phase,
    SessionState,
    SprintState,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# AttemptState
# ---------------------------------------------------------------------------

class TestAttemptState:
    def test_defaults(self) -> None:
        a = AttemptState(attempt=1)
        assert a.impl_done is False
        assert a.eval_done is False
        assert a.passed is None
        assert a.score is None

    def test_roundtrip(self) -> None:
        a = AttemptState(attempt=2, impl_done=True, eval_done=True, passed=True, score=8.5)
        restored = AttemptState.from_dict(a.to_dict())
        assert restored.attempt == 2
        assert restored.passed is True
        assert restored.score == 8.5


# ---------------------------------------------------------------------------
# SprintState
# ---------------------------------------------------------------------------

class TestSprintState:
    def test_defaults(self) -> None:
        s = SprintState(sprint_number=1)
        assert s.started is False
        assert s.done is False
        assert s.attempts == []

    def test_roundtrip_with_attempts(self) -> None:
        s = SprintState(
            sprint_number=3,
            started=True,
            done=True,
            passed=True,
            current_attempt=2,
            attempts=[
                AttemptState(attempt=1, impl_done=True, eval_done=True, passed=False, score=4.0),
                AttemptState(attempt=2, impl_done=True, eval_done=True, passed=True, score=8.0),
            ],
        )
        restored = SprintState.from_dict(s.to_dict())
        assert restored.sprint_number == 3
        assert restored.passed is True
        assert len(restored.attempts) == 2
        assert restored.attempts[1].score == 8.0


# ---------------------------------------------------------------------------
# SessionState
# ---------------------------------------------------------------------------

class TestSessionState:
    def test_auto_timestamps(self) -> None:
        s = SessionState(run_id="test-001", user_prompt="hello")
        assert s.created_at != ""
        assert s.updated_at != ""

    def test_touch_updates_timestamp(self) -> None:
        s = SessionState(run_id="test-001", user_prompt="hello")
        old = s.updated_at
        s.touch()
        assert s.updated_at >= old

    def test_json_roundtrip(self) -> None:
        s = SessionState(
            run_id="abc123",
            user_prompt="테스트 프롬프트",
            phase=Phase.SPRINT_DONE.value,
            spec_json='{"title": "test"}',
            sprints=[SprintState(sprint_number=1, started=True, done=True, passed=True)],
            completed_sprint_numbers=[1],
        )
        text = s.to_json()
        data = json.loads(text)
        assert data["run_id"] == "abc123"
        assert data["phase"] == "sprint_done"

        restored = SessionState.from_json(text)
        assert restored.run_id == "abc123"
        assert restored.user_prompt == "테스트 프롬프트"
        assert restored.phase == Phase.SPRINT_DONE.value
        assert len(restored.sprints) == 1
        assert restored.sprints[0].passed is True
        assert restored.completed_sprint_numbers == [1]

    def test_from_dict_handles_missing_fields(self) -> None:
        s = SessionState.from_dict({"run_id": "x", "user_prompt": "y"})
        assert s.phase == Phase.INIT.value
        assert s.sprints == []
        assert s.completed_sprint_numbers == []

    def test_from_dict_handles_bad_types(self) -> None:
        s = SessionState.from_dict({
            "run_id": "x",
            "user_prompt": "y",
            "sprints": "not a list",
            "completed_sprint_numbers": "not a list",
        })
        assert s.sprints == []
        assert s.completed_sprint_numbers == []


# ---------------------------------------------------------------------------
# CheckpointStore
# ---------------------------------------------------------------------------

class TestCheckpointStore:
    def test_save_and_load(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        state = SessionState(run_id="run-001", user_prompt="hello")
        store.save(state)

        loaded = store.load("run-001")
        assert loaded is not None
        assert loaded.run_id == "run-001"
        assert loaded.user_prompt == "hello"

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        assert store.load("nonexistent") is None

    def test_latest_pointer(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        store.save(SessionState(run_id="run-a", user_prompt="first"))
        store.save(SessionState(run_id="run-b", user_prompt="second"))

        latest = store.load_latest()
        assert latest is not None
        assert latest.run_id == "run-b"

    def test_load_latest_empty(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        assert store.load_latest() is None

    def test_exists(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        assert store.exists("run-x") is False
        store.save(SessionState(run_id="run-x", user_prompt="x"))
        assert store.exists("run-x") is True

    def test_list_runs(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        for rid in ["c", "a", "b"]:
            store.save(SessionState(run_id=rid, user_prompt=rid))
        assert store.list_runs() == ["a", "b", "c"]

    def test_list_runs_empty(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        assert store.list_runs() == []

    def test_overwrite_existing(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        store.save(SessionState(run_id="run-1", user_prompt="v1", phase=Phase.INIT.value))
        store.save(SessionState(run_id="run-1", user_prompt="v1", phase=Phase.PLANNING_DONE.value))

        loaded = store.load("run-1")
        assert loaded is not None
        assert loaded.phase == Phase.PLANNING_DONE.value

    def test_corrupted_json_returns_none(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        store.base_dir.mkdir(parents=True, exist_ok=True)
        path = store.base_dir / "bad-run.json"
        path.write_text("{invalid json", encoding="utf-8")
        assert store.load("bad-run") is None

    def test_atomic_write_creates_no_temp_files(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        store.save(SessionState(run_id="clean", user_prompt="test"))
        temp_files = list(store.base_dir.glob(".ckpt-*.tmp"))
        assert temp_files == []


# ---------------------------------------------------------------------------
# Orchestrator resume 통합 테스트
# ---------------------------------------------------------------------------

class TestOrchestratorResume:
    def test_resume_skips_completed_sprints(self, tmp_path: Path) -> None:
        """이미 완료된 스프린트를 건너뛰고 남은 스프린트만 실행한다."""
        from unittest.mock import MagicMock, patch

        from harness.agents.orchestrator import HarnessConfig, HarnessOrchestrator

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
            patch("harness.agents.orchestrator.CheckpointStore") as mock_ckpt_cls,
        ):
            from harness.agents.evaluator import EvaluationResult
            from harness.agents.planner import ProductSpec

            spec = ProductSpec(
                title="Test",
                description="",
                features=[],
                design_language={},
                tech_stack={},
                sprints=[
                    {"number": 1, "name": "Sprint 1", "goal": "goal 1"},
                    {"number": 2, "name": "Sprint 2", "goal": "goal 2"},
                ],
            )

            saved_session = SessionState(
                run_id="resume-test",
                user_prompt="test",
                phase=Phase.SPRINT_DONE.value,
                spec_json=spec.to_json(),
                completed_sprint_numbers=[1],
            )

            mock_ckpt = MagicMock()
            mock_ckpt.load.return_value = saved_session
            mock_ckpt_cls.return_value = mock_ckpt

            mock_gen = MagicMock()
            mock_gen.run.return_value = "proposal"
            mock_gen.implement_sprint.return_value = "impl"
            mock_gen._token_usage = {"input": 0, "output": 0}
            mock_gen.total_cost = 0.0
            mock_gen_cls.return_value = mock_gen

            mock_eval = MagicMock()
            mock_eval.negotiate_contract.return_value = "contract"
            mock_eval.evaluate_sprint.return_value = EvaluationResult(
                sprint_number=2, passed=True, overall_score=9.0,
                criteria_scores=[], bugs_found=[], summary="pass",
                detailed_feedback="",
            )
            mock_eval.total_cost = 0.0
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
            orch.planner.total_cost = 0.0  # type: ignore[union-attr]
            result = orch.run("test", resume_run_id="resume-test")

            assert result["passed_sprints"] == 1
            assert result["total_sprints"] == 1
            # Sprint 1은 건너뛰므로 implement_sprint은 Sprint 2만 호출
            mock_gen.implement_sprint.assert_called_once()
            call_args = mock_gen.implement_sprint.call_args
            assert call_args[0][2] == 2  # sprint_num

    def test_resume_latest(self, tmp_path: Path) -> None:
        """--resume로 latest 체크포인트에서 재개한다."""
        from unittest.mock import MagicMock, patch

        from harness.agents.orchestrator import HarnessConfig, HarnessOrchestrator

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
            patch("harness.agents.orchestrator.CheckpointStore") as mock_ckpt_cls,
        ):
            from harness.agents.evaluator import EvaluationResult
            from harness.agents.planner import ProductSpec

            spec = ProductSpec(
                title="Latest",
                description="",
                features=[],
                design_language={},
                tech_stack={},
                sprints=[{"number": 1, "name": "Sprint 1", "goal": "g"}],
            )

            saved_session = SessionState(
                run_id="latest-run",
                user_prompt="test",
                phase=Phase.PLANNING_DONE.value,
                spec_json=spec.to_json(),
            )

            mock_ckpt = MagicMock()
            mock_ckpt.load_latest.return_value = saved_session
            mock_ckpt_cls.return_value = mock_ckpt

            mock_gen = MagicMock()
            mock_gen.run.return_value = "proposal"
            mock_gen.implement_sprint.return_value = "impl"
            mock_gen._token_usage = {"input": 0, "output": 0}
            mock_gen.total_cost = 0.0
            mock_gen_cls.return_value = mock_gen

            mock_eval = MagicMock()
            mock_eval.negotiate_contract.return_value = "contract"
            mock_eval.evaluate_sprint.return_value = EvaluationResult(
                sprint_number=1, passed=True, overall_score=9.0,
                criteria_scores=[], bugs_found=[], summary="",
                detailed_feedback="",
            )
            mock_eval.total_cost = 0.0
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
            orch.planner.total_cost = 0.0  # type: ignore[union-attr]
            result = orch.run("test", resume_run_id="latest")

            # load_latest가 호출됨
            mock_ckpt.load_latest.assert_called_once()
            assert result["title"] == "Latest"

    def test_resume_nonexistent_raises(self, tmp_path: Path) -> None:
        """존재하지 않는 run_id로 재개 시 ValueError."""
        from unittest.mock import MagicMock, patch

        import pytest

        from harness.agents.orchestrator import HarnessConfig, HarnessOrchestrator

        config = HarnessConfig(project_dir=str(tmp_path))

        with (
            patch("harness.agents.orchestrator.PlannerAgent"),
            patch("harness.agents.orchestrator.GeneratorAgent"),
            patch("harness.agents.orchestrator.EvaluatorAgent"),
            patch("harness.agents.orchestrator.ReviewArtifactManager"),
            patch("harness.agents.orchestrator.ContractStore"),
            patch("harness.agents.orchestrator.CriteriaGenerator"),
            patch("harness.agents.orchestrator.IntentGenerator"),
            patch("harness.agents.orchestrator.WorktreeManager"),
            patch("harness.agents.orchestrator.CheckpointStore") as mock_ckpt_cls,
        ):
            mock_ckpt = MagicMock()
            mock_ckpt.load.return_value = None
            mock_ckpt_cls.return_value = mock_ckpt

            orch = HarnessOrchestrator(config)

            with pytest.raises(ValueError, match="체크포인트를 찾을 수 없습니다"):
                orch.run("test", resume_run_id="nonexistent")
