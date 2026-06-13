from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from harness.agents.evaluator import EvaluationResult
from harness.agents.orchestrator import HarnessConfig, HarnessOrchestrator
from harness.context.checkpoint import SessionState
from harness.pipeline.harness_pipeline import PipelineReport
from harness.tools.shell import CommandResult

if TYPE_CHECKING:
    from pathlib import Path


def _make_orchestrator(tmp_path: Path) -> HarnessOrchestrator:
    config = HarnessConfig(
        project_dir=str(tmp_path),
        max_sprint_retries=1,
        save_artifacts=False,
    )
    with (
        patch("harness.agents.orchestrator.PlannerAgent"),
        patch("harness.agents.orchestrator.GeneratorAgent"),
        patch("harness.agents.orchestrator.ReviewArtifactManager"),
        patch("harness.agents.orchestrator.ContractStore"),
        patch("harness.agents.orchestrator.CriteriaGenerator"),
        patch("harness.agents.orchestrator.IntentGenerator"),
        patch("harness.agents.orchestrator.WorktreeManager"),
        patch("harness.agents.orchestrator.CheckpointStore"),
        patch("harness.agents.orchestrator.SessionForkManager"),
        patch("harness.agents.orchestrator.HarnessPipeline"),
    ):
        orchestrator = HarnessOrchestrator(config)
    orchestrator._session = SessionState(run_id="test", user_prompt="task")
    return orchestrator


def _eval_result() -> EvaluationResult:
    return EvaluationResult(
        sprint_number=1,
        passed=True,
        overall_score=9.0,
        criteria_scores=[],
        bugs_found=[],
        summary="요약",
        detailed_feedback="상세",
    )


def _pipeline_report() -> PipelineReport:
    return PipelineReport(passed=True, summary_for_llm="요약", details={})


def test_record_knowledge_persists_changed_files(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path)
    porcelain = " M harness/auth.py\n?? new_file.py\n"
    git_result = CommandResult(argv=["git"], returncode=0, stdout=porcelain)

    with patch(
        "harness.tools.shell.run_argv_safe", return_value=git_result
    ) as mock_git:
        orchestrator._record_knowledge(
            task_goal="auth 리팩터링",
            sprint_num=1,
            attempt=1,
            eval_result=_eval_result(),
            pipeline_report=_pipeline_report(),
            filtered_ctx=MagicMock(relevant_adrs=[]),
        )

    mock_git.assert_called_once()
    stored = orchestrator._knowledge_store.load_all()
    assert len(stored) == 1
    assert stored[0].changed_files == ["harness/auth.py", "new_file.py"]


def test_record_knowledge_empty_on_git_failure(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path)
    git_result = CommandResult(argv=["git"], returncode=128, stderr="fatal")

    with patch("harness.tools.shell.run_argv_safe", return_value=git_result):
        orchestrator._record_knowledge(
            task_goal="작업",
            sprint_num=1,
            attempt=1,
            eval_result=_eval_result(),
            pipeline_report=_pipeline_report(),
            filtered_ctx=MagicMock(relevant_adrs=[]),
        )

    stored = orchestrator._knowledge_store.load_all()
    assert len(stored) == 1
    assert stored[0].changed_files == []
