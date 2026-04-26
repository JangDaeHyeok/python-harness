"""오케스트레이터. Planner → Generator → Evaluator 전체 파이프라인을 조율한다."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.agents.evaluator import EvaluationResult, EvaluatorAgent
from harness.agents.generator import GeneratorAgent
from harness.agents.planner import PlannerAgent, ProductSpec

logger = logging.getLogger(__name__)


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

        self.planner = PlannerAgent(model=config.model)
        self.generator = GeneratorAgent(project_dir=config.project_dir, model=config.model)
        self.evaluator = EvaluatorAgent(project_dir=config.project_dir, model=config.model)

        self.spec: ProductSpec | None = None
        self.sprint_results: list[EvaluationResult] = []
        self.total_cost = 0.0
        self.start_time = 0.0

    def run(self, user_prompt: str) -> dict[str, Any]:
        """하네스를 실행한다."""
        self.start_time = time.time()
        self._ensure_dirs()

        # Phase 1: Planning
        logger.info("=" * 60)
        logger.info("Phase 1: Planning")
        logger.info("=" * 60)

        self.spec = self.planner.plan(user_prompt)
        self._save_artifact("spec.json", self.spec.__dict__)
        logger.info(
            "스펙 생성 완료: %s (%d개 기능, %d개 스프린트)",
            self.spec.title,
            len(self.spec.features),
            len(self.spec.sprints),
        )

        # Phase 2: Sprint Execution
        for sprint in self.spec.sprints[: self.config.max_total_sprints]:
            sprint_num = sprint["number"]
            logger.info("=" * 60)
            logger.info("Phase 2: Sprint %d - %s", sprint_num, sprint["name"])
            logger.info("=" * 60)

            success = self._execute_sprint(sprint_num, sprint)
            if not success:
                logger.warning("Sprint %d 최대 재시도 후에도 실패.", sprint_num)

        # Phase 3: Summary
        elapsed = time.time() - self.start_time
        self.total_cost = (
            self.planner.total_cost + self.generator.total_cost + self.evaluator.total_cost
        )

        summary: dict[str, Any] = {
            "title": self.spec.title,
            "total_sprints": len(self.sprint_results),
            "passed_sprints": sum(1 for r in self.sprint_results if r.passed),
            "total_cost_usd": round(self.total_cost, 2),
            "elapsed_seconds": round(elapsed, 1),
            "elapsed_human": self._format_duration(elapsed),
        }
        self._save_artifact("summary.json", summary)
        logger.info("하네스 실행 완료: %s", json.dumps(summary, indent=2))
        return summary

    def _execute_sprint(self, sprint_num: int, sprint_info: dict[str, Any]) -> bool:
        assert self.spec is not None
        spec_json = self.spec.to_json()

        # 계약 협상
        logger.info("  [Sprint %d] 계약 협상 중...", sprint_num)
        proposal = self.generator.run(
            f"스프린트 {sprint_num}에서 구현할 내용과 검증 기준을 제안해주세요.\n"
            f"스프린트 정보: {json.dumps(sprint_info, ensure_ascii=False)}\n"
            f"제품 스펙: {spec_json}"
        )
        contract = self.evaluator.negotiate_contract(spec_json, sprint_num, proposal)
        self._save_artifact(f"sprint_{sprint_num}_contract.md", contract)

        # 구현 + 평가 루프
        eval_result: EvaluationResult | None = None
        for attempt in range(1, self.config.max_sprint_retries + 1):
            logger.info(
                "  [Sprint %d] 구현 시도 %d/%d",
                sprint_num, attempt, self.config.max_sprint_retries,
            )

            if attempt > 1 and self.config.enable_context_reset:
                self.generator.reset_context()

            impl_report = self.generator.implement_sprint(spec_json, contract, sprint_num)
            self._save_artifact(f"sprint_{sprint_num}_impl_attempt{attempt}.md", impl_report)

            logger.info("  [Sprint %d] 평가 중...", sprint_num)
            eval_result = self.evaluator.evaluate_sprint(
                sprint_num, contract, self.config.app_url
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

            if eval_result.passed:
                logger.info("  [Sprint %d] 통과! (점수: %s)", sprint_num, eval_result.overall_score)
                self.sprint_results.append(eval_result)
                return True

            logger.info(
                "  [Sprint %d] 실패 (점수: %s). 피드백 전달 중...",
                sprint_num, eval_result.overall_score,
            )
            self._send_feedback(eval_result, attempt)

        if eval_result is not None:
            self.sprint_results.append(eval_result)
        return False

    def _send_feedback(self, eval_result: EvaluationResult, attempt: int) -> None:
        feedback_lines = [
            f"## Evaluator 피드백 (시도 {attempt})\n",
            f"**점수**: {eval_result.overall_score}/10",
            f"**요약**: {eval_result.summary}\n",
            "### 발견된 버그",
        ]
        for bug in eval_result.bugs_found:
            feedback_lines.append(
                f"- [{bug['severity']}] {bug['description']} ({bug.get('location', 'N/A')})\n"
                f"  수정 제안: {bug.get('fix_suggestion', 'N/A')}"
            )
        feedback_lines.append(f"\n### 상세 피드백\n{eval_result.detailed_feedback}")

        self.generator.run(
            "이전 구현에 대한 Evaluator의 피드백입니다. "
            "피드백을 반영하여 수정해주세요.\n\n" + "\n".join(feedback_lines)
        )

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
