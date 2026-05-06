"""오케스트레이터. Planner → Generator → Evaluator 전체 파이프라인을 조율한다."""

from __future__ import annotations

import json
import logging
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.agents.evaluator import EvaluationResult, EvaluatorAgent
from harness.agents.generator import GeneratorAgent
from harness.agents.planner import PlannerAgent, ProductSpec
from harness.context.checkpoint import (
    AttemptState,
    CheckpointStore,
    Phase,
    SessionState,
    SprintState,
)
from harness.context.modify_context import ModifyContextCollector
from harness.context.phase_manager import PhaseManager, PhaseStatus
from harness.context.project_policy import ProjectPolicyManager
from harness.contracts.models import SprintContract
from harness.contracts.store import ContractStore
from harness.guides.context_filter import ContextFilter
from harness.review.artifacts import ReviewArtifactManager
from harness.review.criteria import CriteriaGenerator
from harness.review.docs_diff import DocsDiffGenerator
from harness.review.intent import IntentGenerator
from harness.review.session_fork import SessionForkManager
from harness.review.worktree import WorktreeError, WorktreeManager, is_worktree_dirty

logger = logging.getLogger(__name__)

_WORKTREE_SKIP_DIRS = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".next", "dist", "build",
})


class WorktreeSyncError(RuntimeError):
    """worktree 결과를 메인 프로젝트에 동기화할 수 없을 때 발생한다."""


@dataclass(frozen=True)
class WorktreeChange:
    """worktree에서 발생한 단일 파일 변경."""

    status: str
    path: str
    old_path: str = ""


@dataclass
class HarnessConfig:
    """하네스 설정."""

    project_dir: str
    model: str = "claude-sonnet-4-6"
    max_sprint_retries: int = 3
    max_total_sprints: int = 15
    app_url: str = "http://localhost:3000"
    enable_context_reset: bool = True
    save_artifacts: bool = True
    mode: str = "create"
    use_worktree_isolation: bool = False
    worktree_sync_excludes: list[str] = field(default_factory=list)
    use_headless_phases: bool = False
    headless_phase_timeout: int = 600
    require_docs_diff_for_headless: bool = True


class HarnessOrchestrator:
    """
    3-에이전트 하네스의 오케스트레이터.

    실행 흐름:
    1. Planner가 스펙 생성
    2. 각 스프린트에 대해:
       a. Generator와 Evaluator가 스프린트 계약 협상
       b. Generator가 구현
       c. Evaluator가 평가
       d. 실패 시 피드백과 함께 재시도
    """

    def __init__(self, config: HarnessConfig) -> None:
        self.config = config
        self.project_dir = Path(config.project_dir)
        self.artifacts_dir = self.project_dir / ".harness" / "artifacts"

        self.planner = PlannerAgent(model=config.model, mode=config.mode)
        self.generator = GeneratorAgent(
            project_dir=config.project_dir, model=config.model, mode=config.mode,
        )
        self.evaluator = EvaluatorAgent(
            project_dir=config.project_dir, model=config.model, mode=config.mode,
        )

        self.spec: ProductSpec | None = None
        self.sprint_results: list[EvaluationResult] = []
        self.total_cost = 0.0
        self.start_time = 0.0

        self.review_artifacts = ReviewArtifactManager(self.project_dir)
        self.contract_store = ContractStore(self.project_dir)
        self._intent_gen = IntentGenerator()
        self._criteria_gen = CriteriaGenerator(self.project_dir)
        self._worktree_mgr = WorktreeManager(self.project_dir)
        self._checkpoint_store = CheckpointStore(self.project_dir)
        self._session: SessionState | None = None
        self._modify_ctx_collector = ModifyContextCollector(self.project_dir)
        self._policy_mgr = ProjectPolicyManager(self.project_dir)
        self._phase_mgr = PhaseManager(self.project_dir)
        self._docs_diff_gen = DocsDiffGenerator(self.project_dir)
        self._context_filter = ContextFilter(self.project_dir)
        self._session_fork_mgr = SessionForkManager(self.project_dir)

    def run(
        self, user_prompt: str, *, resume_run_id: str = ""
    ) -> dict[str, Any]:
        """하네스를 실행한다.

        Args:
            user_prompt: 프로젝트 설명.
            resume_run_id: 재개할 run_id. "latest"이면 가장 최근 체크포인트에서 재개.
        """
        self.start_time = time.time()
        self._ensure_dirs()

        # Resume 또는 새 세션 생성
        if resume_run_id:
            self._session = self._load_session(resume_run_id)
            if self._session is None:
                raise ValueError(f"체크포인트를 찾을 수 없습니다: {resume_run_id}")
            if user_prompt and user_prompt != self._session.user_prompt:
                logger.warning(
                    "재개 시 전달된 user_prompt가 저장된 값과 다릅니다. "
                    "저장된 프롬프트를 사용합니다. (저장=%s..., 전달=%s...)",
                    self._session.user_prompt[:50], user_prompt[:50],
                )
            logger.info("세션 재개: %s (phase=%s)", self._session.run_id, self._session.phase)
        else:
            run_id = uuid.uuid4().hex[:12]
            self._session = SessionState(run_id=run_id, user_prompt=user_prompt)
            self._checkpoint_store.save(self._session)

        session = self._require_session()

        # Phase 1: Planning (이미 완료된 경우 건너뛰기)
        if session.phase == Phase.INIT.value:
            logger.info("=" * 60)
            logger.info("Phase 1: Planning (%s mode)", self.config.mode)
            logger.info("=" * 60)

            if self.config.mode == "modify":
                self.spec = self._plan_modify(user_prompt)
            else:
                self.spec = self.planner.plan(user_prompt)
            self._save_artifact("spec.json", self.spec.__dict__)
            logger.info(
                "스펙 생성 완료: %s (%d개 기능, %d개 스프린트)",
                self.spec.title,
                len(self.spec.features),
                len(self.spec.sprints),
            )

            session.spec_json = self.spec.to_json()
            session.phase = Phase.PLANNING_DONE.value
            self._checkpoint_store.save(session)
        else:
            self.spec = ProductSpec.from_json(session.spec_json)
            logger.info("저장된 스펙에서 복원: %s", self.spec.title)

        # 재개 시 이미 완료된 스프린트 결과를 복원하여 최종 요약에 반영
        if resume_run_id:
            self._restore_completed_sprint_results()

        spec = self._require_spec()

        # Phase 2: Sprint Execution
        for sprint in spec.sprints[: self.config.max_total_sprints]:
            sprint_num = sprint["number"]

            if self._is_sprint_done(sprint_num):
                logger.info("Sprint %d 이미 완료 — 건너뛰기", sprint_num)
                continue

            logger.info("=" * 60)
            logger.info("Phase 2: Sprint %d - %s", sprint_num, sprint["name"])
            logger.info("=" * 60)

            success = self._execute_sprint(sprint_num, sprint)
            if not success:
                logger.warning("Sprint %d 최대 재시도 후에도 실패.", sprint_num)

        # Phase 3: Summary
        session.phase = Phase.RUN_DONE.value
        self._checkpoint_store.save(session)

        elapsed = time.time() - self.start_time
        self.total_cost = (
            self.planner.total_cost + self.generator.total_cost + self.evaluator.total_cost
        )

        summary: dict[str, Any] = {
            "title": spec.title,
            "total_sprints": len(self.sprint_results),
            "passed_sprints": sum(1 for r in self.sprint_results if r.passed),
            "total_cost_usd": round(self.total_cost, 2),
            "elapsed_seconds": round(elapsed, 1),
            "elapsed_human": self._format_duration(elapsed),
        }
        self._save_artifact("summary.json", summary)
        logger.info("하네스 실행 완료: %s", json.dumps(summary, indent=2))
        return summary

    def _require_spec(self) -> ProductSpec:
        if self.spec is None:
            raise ValueError("spec is required")
        return self.spec

    def _require_session(self) -> SessionState:
        if self._session is None:
            raise ValueError("session is required")
        return self._session

    def _plan_modify(self, user_prompt: str) -> ProductSpec:
        """modify 모드 전용 계획 수립. 기존 코드베이스 컨텍스트를 수집하여 Planner에 전달한다."""
        policy = self._policy_mgr.load()
        modify_ctx = self._modify_ctx_collector.collect(policy=policy)
        context_md = modify_ctx.to_markdown()

        message = (
            f"다음 수정 요청을 분석하고 수정 계획을 수립해주세요:\n\n"
            f"## 수정 요청\n{user_prompt}\n\n"
            f"{context_md}\n\n"
            "위 프로젝트 컨텍스트를 참고하여 기존 코드베이스를 수정하는 계획을 세워주세요.\n"
            "새 프로젝트를 만들지 말고 기존 파일을 수정하거나 필요한 파일만 추가하세요.\n"
            "변경 범위는 최소화하고, 기존 아키텍처 규칙과 코드 컨벤션을 준수하세요."
        )
        result = self.planner.run(message)
        if not isinstance(result, ProductSpec):
            raise TypeError(f"ProductSpec 예상, {type(result).__name__} 반환됨")
        return result

    def _load_session(self, resume_run_id: str) -> SessionState | None:
        if resume_run_id == "latest":
            return self._checkpoint_store.load_latest()
        return self._checkpoint_store.load(resume_run_id)

    def _execute_sprint(self, sprint_num: int, sprint_info: dict[str, Any]) -> bool:
        spec_json = self._require_spec().to_json()
        session = self._require_session()

        # 스프린트 상태 초기화 또는 복원
        sprint_state = self._get_or_create_sprint_state(sprint_num)
        resuming_mid_sprint = sprint_state.started and not sprint_state.done

        if not sprint_state.started:
            # checkpoint: sprint_start
            sprint_state.started = True
            session.phase = Phase.SPRINT_START.value
            self._checkpoint_store.save(session)

        # 계약 협상 (재개 시 이미 저장된 계약이 있으면 건너뛰기)
        saved_contract = self.contract_store.load(sprint_num)
        if saved_contract is not None and resuming_mid_sprint:
            contract = saved_contract.raw_text
            logger.info("  [Sprint %d] 저장된 계약에서 복원", sprint_num)
        else:
            logger.info("  [Sprint %d] 계약 협상 중...", sprint_num)
            proposal = self.generator.run(
                f"스프린트 {sprint_num}에서 구현할 내용과 검증 기준을 제안해주세요.\n"
                f"스프린트 정보: {json.dumps(sprint_info, ensure_ascii=False)}\n"
                f"제품 스펙: {spec_json}"
            )
            contract = self.evaluator.negotiate_contract(spec_json, sprint_num, proposal)
            self._save_artifact(f"sprint_{sprint_num}_contract.md", contract)

            structured_contract = SprintContract.from_raw_text(sprint_num, contract)
            structured_contract.metadata.model = self.config.model
            self.contract_store.save(structured_contract)

        # 설계 의도 문서 생성 (세션 포크 활용)
        task_goal = str(sprint_info.get("goal", ""))
        fork_ctx = self._session_fork_mgr.create_context(
            user_prompt=self._require_session().user_prompt,
            sprint_info=json.dumps(sprint_info, ensure_ascii=False),
            key_decisions=[f"스프린트 {sprint_num} 계약에 따른 구현"],
        )
        intent_md = self._session_fork_mgr.generate_intent_from_context(fork_ctx)
        self.review_artifacts.save(f"design-intent-sprint{sprint_num}.md", intent_md)
        logger.info("  [Sprint %d] 설계 의도 문서 생성 완료", sprint_num)

        # docs-diff 생성
        docs_diff = self._docs_diff_gen.generate()
        docs_diff_md = docs_diff.to_markdown()
        if docs_diff.has_changes:
            self.review_artifacts.save(f"docs-diff-sprint{sprint_num}.md", docs_diff_md)
            logger.info("  [Sprint %d] docs-diff 생성 완료 (%d개 파일)", sprint_num, len(docs_diff.changed_files))

        # 유사 RAG: 컨텍스트 필터링으로 관련 평가 기준만 추출
        filtered_ctx = self._context_filter.filter(task_goal)
        filtered_criteria_md = filtered_ctx.to_markdown()

        # 평가 기준 문서 생성 (필터링된 컨텍스트 + 기존 기준 결합)
        criteria = self._criteria_gen.generate(task_goal)
        base_criteria_md = self._criteria_gen.to_markdown(criteria)
        criteria_md = f"{base_criteria_md}\n\n{filtered_criteria_md}"
        self.review_artifacts.save(
            f"code-quality-guide-sprint{sprint_num}.md", criteria_md,
        )
        self.review_artifacts.save("code-quality-guide.md", criteria_md)
        logger.info("  [Sprint %d] 평가 기준 문서 생성 완료 (%d개)", sprint_num, len(criteria))

        # Phase 분할 (Task/Phase 시스템). 중간 재개 시 기존 상태를 보존한다.
        existing_task_index = self._phase_mgr.load_task_index(sprint_num)
        if existing_task_index is not None and resuming_mid_sprint:
            task_index = existing_task_index
            logger.info("  [Sprint %d] 기존 Phase 인덱스 복원 (%d개)", sprint_num, len(task_index.phases))
        else:
            task_index = self._phase_mgr.create_phases(
                sprint_number=sprint_num,
                task_name=str(sprint_info.get("name", f"Sprint {sprint_num}")),
            )
            self._phase_mgr.save_task_index(task_index)
        for phase in task_index.phases:
            phase_prompt_path = (
                self._phase_mgr.tasks_dir / f"sprint-{sprint_num}" / phase.prompt_file
            )
            if not phase_prompt_path.exists():
                prompt_content = self._phase_mgr.build_phase_prompt(
                    phase=phase,
                    sprint_contract=contract,
                    docs_diff_md=docs_diff_md if docs_diff.has_changes else "",
                    extra_context=filtered_criteria_md,
                )
                self._phase_mgr.save_phase_prompt(sprint_num, phase, prompt_content)
        logger.info("  [Sprint %d] Phase 분할 완료 (%d개)", sprint_num, len(task_index.phases))

        # 구현 + 평가 루프 (재개 시 완료된 attempt 건너뛰기)
        resume_from_attempt = sprint_state.current_attempt if resuming_mid_sprint else 0
        eval_result: EvaluationResult | None = None
        for attempt in range(1, self.config.max_sprint_retries + 1):
            if attempt <= resume_from_attempt:
                existing = next(
                    (a for a in sprint_state.attempts if a.attempt == attempt), None,
                )
                if existing and existing.eval_done:
                    logger.info("  [Sprint %d] 시도 %d 이미 완료 — 건너뛰기", sprint_num, attempt)
                    continue
            logger.info(
                "  [Sprint %d] 구현 시도 %d/%d",
                sprint_num, attempt, self.config.max_sprint_retries,
            )

            attempt_state = AttemptState(attempt=attempt)
            sprint_state.current_attempt = attempt
            sprint_state.attempts.append(attempt_state)

            # checkpoint: attempt_start
            session.phase = Phase.ATTEMPT_START.value
            self._checkpoint_store.save(session)

            if attempt > 1 and self.config.enable_context_reset:
                self.generator.reset_context()

            # modify 모드 추가 컨텍스트
            modify_hint = ""
            if self.config.mode == "modify":
                modify_hint = (
                    "\n\n## 주의: 수정 모드\n"
                    "새 프로젝트를 만들지 말고 기존 파일을 수정하세요.\n"
                    "기존 아키텍처 규칙과 코드 컨벤션을 준수하세요.\n"
                )

            effective_contract = contract + modify_hint

            # 구현 방식 분기: 헤드리스 Phase 실행 → worktree 격리 → 기존 Generator
            if self.config.use_headless_phases:
                try:
                    impl_report = self._implement_with_headless_phases(sprint_num, attempt)
                except RuntimeError as e:
                    logger.error(
                        "  [Sprint %d] 헤드리스 Phase 실행 실패 — 다음 시도로 진행: %s",
                        sprint_num, e,
                    )
                    continue
            elif self.config.use_worktree_isolation:
                try:
                    impl_report = self._implement_in_worktree(
                        spec_json, effective_contract, sprint_num,
                    )
                except (
                    WorktreeError,
                    WorktreeSyncError,
                    subprocess.SubprocessError,
                    OSError,
                    RuntimeError,
                    TypeError,
                ) as e:
                    logger.error(
                        "  [Sprint %d] worktree 구현 예외 — 메인 프로젝트 변경 없이 다음 시도로 진행: %s",
                        sprint_num, e,
                    )
                    continue
            else:
                impl_report = self.generator.implement_sprint(
                    spec_json, effective_contract, sprint_num,
                )

            self._save_artifact(f"sprint_{sprint_num}_impl_attempt{attempt}.md", impl_report)

            # checkpoint: impl_done
            attempt_state.impl_done = True
            session.phase = Phase.IMPL_DONE.value
            self._checkpoint_store.save(session)

            logger.info("  [Sprint %d] 평가 중...", sprint_num)
            eval_result = self.evaluator.evaluate_sprint(
                sprint_num, contract, self.config.app_url, criteria_md=criteria_md
            )
            self._save_artifact(
                f"sprint_{sprint_num}_eval_attempt{attempt}.json",
                {
                    "passed": eval_result.passed,
                    "score": eval_result.overall_score,
                    "bugs": eval_result.bugs_found,
                    "summary": eval_result.summary,
                },
            )

            # checkpoint: eval_done
            attempt_state.eval_done = True
            attempt_state.passed = eval_result.passed
            attempt_state.score = eval_result.overall_score
            session.phase = Phase.EVAL_DONE.value
            self._checkpoint_store.save(session)

            if eval_result.passed:
                logger.info("  [Sprint %d] 통과! (점수: %s)", sprint_num, eval_result.overall_score)
                self.sprint_results.append(eval_result)

                # checkpoint: sprint_done (성공)
                sprint_state.done = True
                sprint_state.passed = True
                session.completed_sprint_numbers.append(sprint_num)
                session.phase = Phase.SPRINT_DONE.value
                self._checkpoint_store.save(session)
                return True

            logger.info(
                "  [Sprint %d] 실패 (점수: %s). 피드백 전달 중...",
                sprint_num, eval_result.overall_score,
            )
            self._send_feedback(eval_result, attempt)

        if eval_result is not None:
            self.sprint_results.append(eval_result)
        else:
            self.sprint_results.append(EvaluationResult(
                sprint_number=sprint_num,
                passed=False,
                overall_score=0.0,
                criteria_scores=[],
                bugs_found=[],
                summary=f"Sprint {sprint_num}: 모든 구현 시도가 예외로 실패",
                detailed_feedback="",
            ))

        # checkpoint: sprint_done (실패)
        sprint_state.done = True
        sprint_state.passed = False
        session.phase = Phase.SPRINT_DONE.value
        self._checkpoint_store.save(session)
        return False

    def _implement_with_headless_phases(self, sprint_num: int, attempt: int) -> str:
        """Phase 파일을 claude --print 독립 세션으로 실행한다."""
        from scripts.run_phases import PhaseExecutionError, run_sprint_phases

        if attempt > 1:
            self._phase_mgr.reset_incomplete_phases(sprint_num)

        try:
            results = run_sprint_phases(
                self.project_dir,
                sprint_num,
                timeout=self.config.headless_phase_timeout,
                require_docs_diff=self.config.require_docs_diff_for_headless,
            )
        except PhaseExecutionError as e:
            raise RuntimeError(str(e)) from e

        failed = [pid for pid, status in results.items() if status == PhaseStatus.FAILED.value]
        skipped = [pid for pid, status in results.items() if status == PhaseStatus.SKIPPED.value]
        if failed or skipped:
            problems = []
            if failed:
                problems.append(f"failed={', '.join(failed)}")
            if skipped:
                problems.append(f"skipped={', '.join(skipped)}")
            raise RuntimeError("; ".join(problems))

        lines = [
            f"# Sprint {sprint_num} Headless Phase 실행 결과\n",
            "## Phase 상태\n",
        ]
        for phase_id, status in results.items():
            lines.append(f"- `{phase_id}`: {status}")

        return "\n".join(lines)

    def _get_or_create_sprint_state(self, sprint_num: int) -> SprintState:
        session = self._require_session()
        for s in session.sprints:
            if s.sprint_number == sprint_num:
                return s
        state = SprintState(sprint_number=sprint_num)
        session.sprints.append(state)
        return state

    def _is_sprint_done(self, sprint_num: int) -> bool:
        session = self._require_session()
        if sprint_num in session.completed_sprint_numbers:
            return True
        return any(s.sprint_number == sprint_num and s.done for s in session.sprints)

    def _restore_completed_sprint_results(self) -> None:
        """체크포인트에서 완료된 스프린트의 평가 결과를 sprint_results에 복원한다."""
        session = self._require_session()
        for sprint_state in session.sprints:
            if not sprint_state.done:
                continue
            last_attempt = next(
                (a for a in reversed(sprint_state.attempts) if a.eval_done),
                None,
            )
            self.sprint_results.append(EvaluationResult(
                sprint_number=sprint_state.sprint_number,
                passed=sprint_state.passed if sprint_state.passed is not None else False,
                overall_score=last_attempt.score if last_attempt and last_attempt.score is not None else 0.0,
                criteria_scores=[],
                bugs_found=[],
                summary="체크포인트에서 복원됨",
                detailed_feedback="",
            ))

    def _send_feedback(self, eval_result: EvaluationResult, attempt: int) -> None:
        feedback_lines = [
            f"## Evaluator 피드백 (시도 {attempt})\n",
            f"**점수**: {eval_result.overall_score}/10",
            f"**요약**: {eval_result.summary}\n",
            "### 발견된 버그",
        ]

        # 반영 판단 로그 기록
        reflection_lines = [
            f"# 리뷰 반영 판단 로그 (Sprint {eval_result.sprint_number}, 시도 {attempt})\n",
        ]
        for i, bug in enumerate(eval_result.bugs_found, start=1):
            severity = str(bug.get("severity", "minor"))
            description = str(bug.get("description", ""))
            location = str(bug.get("location", "N/A"))
            fix_suggestion = str(bug.get("fix_suggestion", "N/A"))
            priority = "p1" if severity in ("critical", "high") else "p2" if severity == "major" else "p3"
            decision = "ACCEPT" if severity in ("critical", "high", "major") else "DEFER"
            feedback_lines.append(
                f"- [{severity}] {description} ({location})\n"
                f"  수정 제안: {fix_suggestion}"
            )
            reflection_lines.append(
                f"## [bug-{i:03d}] {location}\n"
                f"- **심각도**: {severity} / **우선순위**: [{priority}]\n"
                f"- **문제**: {description}\n"
                f"- **제안**: {fix_suggestion}\n"
                f"- **판정**: **{decision}** (자동 분류)\n"
            )

        feedback_lines.append(f"\n### 상세 피드백\n{eval_result.detailed_feedback}")
        reflection_lines.append(
            f"\n## 통계\n\n"
            f"- 총 버그: {len(eval_result.bugs_found)}개\n"
            f"- 점수: {eval_result.overall_score}/10\n"
        )

        self.review_artifacts.save(
            f"review-comments-sprint{eval_result.sprint_number}-attempt{attempt}.md",
            "\n".join(reflection_lines),
        )
        logger.info(
            "  [Sprint %d] 리뷰 반영 로그 저장 완료 (%d개 버그)",
            eval_result.sprint_number, len(eval_result.bugs_found),
        )

        self.generator.run(
            "이전 구현에 대한 Evaluator의 피드백입니다. "
            "피드백을 반영하여 수정해주세요.\n\n" + "\n".join(feedback_lines)
        )

    def _implement_in_worktree(
        self, spec_json: str, contract: str, sprint_num: int
    ) -> str:
        """임시 worktree에서 스프린트를 구현하고 메인 프로젝트에 동기화한다.

        구현 도중 예외가 발생하면 메인 프로젝트에 아무 변경도 남기지 않는다.
        구현이 완료되면 변경 파일을 메인 프로젝트로 복사한다.
        """
        if is_worktree_dirty(self.project_dir):
            raise WorktreeError(
                "작업 트리에 uncommitted 변경이 있습니다. "
                "커밋 후 다시 실행하세요."
            )

        # worktree 생성 전 메인 HEAD를 기록 — Generator가 커밋해도 이 기준으로 diff
        base_commit = self._get_head_commit(self.project_dir)
        worktree_path = self._worktree_mgr.create_worktree()

        try:
            wt_generator = GeneratorAgent(
                project_dir=str(worktree_path),
                model=self.config.model,
                mode=self.config.mode,
            )
            impl_report = wt_generator.implement_sprint(spec_json, contract, sprint_num)

            self.generator.merge_token_usage(wt_generator)

            # 구현 완료 → 메인 프로젝트에 동기화
            synced = self._sync_from_worktree(worktree_path, base_commit)
            logger.info(
                "  [Sprint %d] worktree 구현 완료. %d개 파일 메인 프로젝트에 동기화.",
                sprint_num, synced,
            )
            return impl_report
        except (
            WorktreeError,
            WorktreeSyncError,
            subprocess.SubprocessError,
            OSError,
        ):
            # 예외 발생 시 worktree 변경을 동기화하지 않는다
            logger.warning(
                "  [Sprint %d] worktree 구현 예외 — 메인 프로젝트 변경 없음.", sprint_num
            )
            raise
        finally:
            self._worktree_mgr.cleanup_worktree(worktree_path)

    @staticmethod
    def _get_head_commit(repo_dir: Path) -> str:
        """리포지토리의 현재 HEAD 커밋 해시를 반환한다."""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()

    def _sync_from_worktree(self, worktree_path: Path, base_commit: str = "") -> int:
        """worktree에서 변경된 파일만 메인 프로젝트로 복사한다.

        git diff로 실제 변경된 파일 목록을 구하고, 해당 파일만 동기화한다.
        git diff가 실패하면 exclude 기반 전체 복사로 폴백한다.

        Args:
            worktree_path: worktree 경로
            base_commit: 비교 기준 커밋. 빈 문자열이면 HEAD 사용.

        Returns:
            동기화된 파일 수
        """
        changes = self._get_worktree_changes(worktree_path, base_commit)
        if changes is not None:
            return self._sync_changed_files(worktree_path, changes)
        return self._sync_all_files(worktree_path)

    def _get_worktree_changes(
        self, worktree_path: Path, base_commit: str = ""
    ) -> list[WorktreeChange] | None:
        """worktree에서 git diff로 변경 종류와 파일 목록을 반환한다. 실패 시 None.

        커밋된 변경과 uncommitted 변경을 모두 포착하기 위해 base_commit 기준으로
        워킹 트리 전체를 비교한다.
        """
        diff_ref = base_commit or "HEAD"
        try:
            result = subprocess.run(
                ["git", "diff", "--name-status", diff_ref],
                cwd=str(worktree_path),
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                logger.warning("worktree git diff 실패, 전체 복사로 폴백")
                return None
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=str(worktree_path),
                capture_output=True, text=True, timeout=30,
            )
            changes = [
                self._parse_name_status_line(line)
                for line in result.stdout.strip().splitlines()
                if line.strip()
            ]
            if untracked.returncode == 0:
                changes += [
                    WorktreeChange("A", f.strip())
                    for f in untracked.stdout.strip().splitlines()
                    if f.strip()
                ]
            return changes
        except (subprocess.SubprocessError, OSError):
            logger.warning("worktree git 명령 실패, 전체 복사로 폴백")
            return None

    @staticmethod
    def _parse_name_status_line(line: str) -> WorktreeChange:
        """git diff --name-status 한 줄을 WorktreeChange로 변환한다."""
        parts = line.split("\t")
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            return WorktreeChange(status=status, path=parts[2], old_path=parts[1])
        path = parts[-1]
        return WorktreeChange(status=status, path=path)

    def _sync_changed_files(
        self, worktree_path: Path, changes: list[WorktreeChange]
    ) -> int:
        """변경된 파일만 메인 프로젝트로 복사한다."""
        excludes = _WORKTREE_SKIP_DIRS | set(self.config.worktree_sync_excludes)
        synced = 0
        for change in changes:
            relpath = change.path
            self._validate_relative_worktree_path(relpath)
            if any(part in excludes for part in Path(relpath).parts):
                continue

            dest = self.project_dir / relpath
            if change.status.startswith("D"):
                if self._has_local_change(relpath):
                    raise WorktreeSyncError(
                        f"로컬 변경이 있는 파일은 삭제할 수 없습니다: {relpath}"
                    )
                if dest.exists():
                    dest.unlink()
                    synced += 1
                continue

            src = worktree_path / relpath
            if not src.is_file():
                continue
            if src.is_symlink():
                logger.warning("symlink 건너뜀: %s", relpath)
                continue
            if self._would_overwrite_local_change(relpath, src):
                raise WorktreeSyncError(
                    f"로컬 변경이 있는 파일은 덮어쓸 수 없습니다: {relpath}"
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            synced += 1

            # Rename: old path 삭제
            if change.old_path and change.status.startswith("R"):
                self._validate_relative_worktree_path(change.old_path)
                old_dest = self.project_dir / change.old_path
                if self._has_local_change(change.old_path):
                    raise WorktreeSyncError(
                        f"로컬 변경이 있는 파일은 삭제할 수 없습니다: {change.old_path}"
                    )
                if old_dest.exists():
                    old_dest.unlink()

        return synced

    @staticmethod
    def _validate_relative_worktree_path(relpath: str) -> None:
        path = Path(relpath)
        if path.is_absolute() or ".." in path.parts:
            raise WorktreeSyncError(f"안전하지 않은 worktree 경로입니다: {relpath}")

    def _would_overwrite_local_change(self, relpath: str, src: Path) -> bool:
        dest = self.project_dir / relpath
        if not self._has_local_change(relpath):
            return False
        if not dest.exists():
            return True
        return dest.read_bytes() != src.read_bytes()

    def _has_local_change(self, relpath: str) -> bool:
        """메인 프로젝트의 해당 경로가 HEAD와 다른지 보수적으로 확인한다."""
        diff = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", relpath],
            cwd=str(self.project_dir),
            capture_output=True, text=True, timeout=30,
        )
        if diff.returncode == 1:
            return True
        if diff.returncode != 0:
            logger.warning("로컬 변경 확인 실패, 충돌로 처리: %s", relpath)
            return True

        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relpath],
            cwd=str(self.project_dir),
            capture_output=True, text=True, timeout=30,
        )
        return tracked.returncode != 0 and (self.project_dir / relpath).exists()

    def _sync_all_files(self, worktree_path: Path) -> int:
        """exclude 기반 전체 복사 (git diff 폴백)."""
        excludes = _WORKTREE_SKIP_DIRS | set(self.config.worktree_sync_excludes)
        synced = 0
        for src in worktree_path.rglob("*"):
            if not src.is_file():
                continue
            if any(part in excludes for part in src.parts):
                continue
            rel = src.relative_to(worktree_path)
            self._validate_relative_worktree_path(str(rel))
            if src.is_symlink():
                logger.warning("symlink 건너뜀: %s", rel)
                continue
            dest = self.project_dir / rel
            if self._would_overwrite_local_change(str(rel), src):
                raise WorktreeSyncError(
                    f"로컬 변경이 있는 파일은 덮어쓸 수 없습니다: {rel}"
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            synced += 1
        return synced

    def _ensure_dirs(self) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def _save_artifact(self, filename: str, content: Any) -> None:
        if not self.config.save_artifacts:
            return
        path = self.artifacts_dir / filename
        if isinstance(content, (dict, list)):
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.write_text(str(content), encoding="utf-8")

    @staticmethod
    def _format_duration(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}시간 {minutes}분"
        return f"{minutes}분"
