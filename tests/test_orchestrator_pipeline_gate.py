from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from harness.agents.evaluator import EvaluationResult
from harness.agents.orchestrator import HarnessConfig, HarnessOrchestrator
from harness.agents.planner import ProductSpec
from harness.context.checkpoint import SessionState
from harness.pipeline.harness_pipeline import PipelineReport

if TYPE_CHECKING:
    from pathlib import Path


def _pipeline_result(passed: bool) -> PipelineReport:
    return PipelineReport(
        passed=passed,
        summary_for_llm="결정적 결과 요약",
        details={
            "lint_passed": passed,
            "type_check_passed": passed,
            "structure_passed": passed,
            "tests_passed": passed,
        },
    )


def _llm_result(passed: bool) -> EvaluationResult:
    return EvaluationResult(
        sprint_number=1,
        passed=passed,
        overall_score=9.0 if passed else 4.0,
        criteria_scores=[],
        bugs_found=[],
        summary="LLM pass" if passed else "LLM fail",
        detailed_feedback="LLM 평가 상세",
    )


def _make_orchestrator(
    tmp_path: Path,
    *,
    pipeline_passed: bool,
    llm_passed: bool,
) -> HarnessOrchestrator:
    config = HarnessConfig(
        project_dir=str(tmp_path),
        max_sprint_retries=1,
        save_artifacts=False,
    )

    with (
        patch("harness.agents.orchestrator.PlannerAgent"),
        patch("harness.agents.orchestrator.GeneratorAgent") as mock_gen_cls,
        patch("harness.agents.orchestrator.ReviewArtifactManager"),
        patch("harness.agents.orchestrator.ContractStore") as mock_contract_cls,
        patch("harness.agents.orchestrator.CriteriaGenerator") as mock_criteria_cls,
        patch("harness.agents.orchestrator.IntentGenerator"),
        patch("harness.agents.orchestrator.WorktreeManager"),
        patch("harness.agents.orchestrator.CheckpointStore"),
        patch("harness.agents.orchestrator.SessionForkManager") as mock_fork_cls,
        patch("harness.agents.orchestrator.HarnessPipeline") as mock_pipeline_cls,
    ):
        mock_gen = MagicMock()
        mock_gen.run.return_value = "proposal"
        mock_gen.implement_sprint.return_value = "impl"
        mock_gen._token_usage = {"input": 0, "output": 0}
        mock_gen_cls.return_value = mock_gen

        mock_contract_store = MagicMock()
        mock_contract_store.load.return_value = None
        mock_contract_cls.return_value = mock_contract_store

        mock_criteria = MagicMock()
        mock_criteria.generate.return_value = []
        mock_criteria.to_markdown.return_value = ""
        mock_criteria_cls.return_value = mock_criteria

        mock_fork = MagicMock()
        mock_fork.create_context.return_value = MagicMock()
        mock_fork.generate_intent_from_context.return_value = ""
        mock_fork_cls.return_value = mock_fork

        mock_pipeline = MagicMock()
        mock_pipeline.run_all.return_value = _pipeline_result(pipeline_passed)
        mock_pipeline_cls.return_value = mock_pipeline

        orchestrator = HarnessOrchestrator(config)

    orchestrator.evaluator.negotiate_contract = MagicMock(return_value="contract")  # type: ignore[method-assign]
    orchestrator.evaluator.run = MagicMock(return_value=_llm_result(llm_passed))  # type: ignore[method-assign]
    sprint_info = {"number": 1, "name": "Sprint 1", "goal": "goal"}
    orchestrator.spec = ProductSpec(
        title="Test",
        description="",
        features=[],
        design_language={},
        tech_stack={},
        sprints=[sprint_info],
    )
    orchestrator._session = SessionState(run_id="test", user_prompt="test")
    return orchestrator


def test_pipeline_fail_llm_pass_final_fail(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path, pipeline_passed=False, llm_passed=True)

    success = orchestrator._execute_sprint(1, {"number": 1, "name": "Sprint 1", "goal": "goal"})

    assert success is False
    assert orchestrator.sprint_results[-1].passed is False
    assert "결정적 결과:" in orchestrator.sprint_results[-1].detailed_feedback
    assert "LLM 평가:" in orchestrator.sprint_results[-1].detailed_feedback


def test_pipeline_pass_llm_fail_final_fail(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path, pipeline_passed=True, llm_passed=False)

    success = orchestrator._execute_sprint(1, {"number": 1, "name": "Sprint 1", "goal": "goal"})

    assert success is False
    assert orchestrator.sprint_results[-1].passed is False


def test_pipeline_pass_llm_pass_final_pass(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path, pipeline_passed=True, llm_passed=True)

    success = orchestrator._execute_sprint(1, {"number": 1, "name": "Sprint 1", "goal": "goal"})

    assert success is True
    assert orchestrator.sprint_results[-1].passed is True
