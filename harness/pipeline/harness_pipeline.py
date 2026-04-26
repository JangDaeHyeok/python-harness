"""하네스 파이프라인. 모든 센서를 순차적으로 실행하고 결과를 통합한다."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from harness.sensors.computational.linter import LinterSensor, LintResult
from harness.sensors.computational.structure_test import StructureAnalyzer, StructureResult
from harness.sensors.computational.test_runner import TestResult, TestRunnerSensor
from harness.sensors.computational.type_checker import TypeCheckerSensor, TypeCheckResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """파이프라인 실행 결과."""

    passed: bool
    lint: LintResult | None = None
    tests: TestResult | None = None
    type_check: TypeCheckResult | None = None
    structure: StructureResult | None = None
    summary_for_llm: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class HarnessPipeline:
    """
    하네스 파이프라인.
    유지보수성 + 아키텍처 적합성 + 행동 하네스를 통합 실행한다.

    - 유지보수성: 린터, 타입 체커
    - 아키텍처 적합성: 구조 분석 (ADR 기반)
    - 행동: 테스트 러너
    """

    def __init__(
        self,
        project_dir: str,
        custom_lint_rules: list[dict[str, Any]] | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.linter = LinterSensor(project_dir, custom_lint_rules)
        self.test_runner = TestRunnerSensor(project_dir)
        self.type_checker = TypeCheckerSensor(project_dir)
        self.structure_analyzer = StructureAnalyzer(project_dir)

    def run_all(self) -> PipelineResult:
        """모든 센서를 실행하고 통합 결과를 반환한다."""
        logger.info("파이프라인 실행 시작")

        # 1. 유지보수성 하네스
        logger.info("  [1/4] 린트 검사...")
        lint_result = self.linter.run_all()

        logger.info("  [2/4] 타입 체크...")
        type_result = self.type_checker.run_mypy()

        # 2. 아키텍처 적합성 하네스
        logger.info("  [3/4] 구조 분석...")
        structure_result = self.structure_analyzer.analyze()

        # 3. 행동 하네스
        logger.info("  [4/4] 테스트 실행...")
        test_result = self.test_runner.run_pytest_simple()

        # 통합
        all_passed = all([
            lint_result.passed,
            type_result.passed,
            structure_result.passed,
            test_result.passed,
        ])

        summary = self._build_summary(lint_result, type_result, structure_result, test_result)

        logger.info("파이프라인 완료: %s", "통과" if all_passed else "실패")

        return PipelineResult(
            passed=all_passed,
            lint=lint_result,
            tests=test_result,
            type_check=type_result,
            structure=structure_result,
            summary_for_llm=summary,
            details={
                "lint_passed": lint_result.passed,
                "type_check_passed": type_result.passed,
                "structure_passed": structure_result.passed,
                "tests_passed": test_result.passed,
            },
        )

    def run_fast(self) -> PipelineResult:
        """빠른 검사만 실행한다 (린트 + 타입 체크)."""
        lint_result = self.linter.run_ruff()
        type_result = self.type_checker.run_mypy()

        all_passed = lint_result.passed and type_result.passed
        summary_parts = [lint_result.summary_for_llm, type_result.summary_for_llm]

        return PipelineResult(
            passed=all_passed,
            lint=lint_result,
            type_check=type_result,
            summary_for_llm="\n\n".join(summary_parts),
        )

    def _build_summary(
        self,
        lint: LintResult,
        type_check: TypeCheckResult,
        structure: StructureResult,
        tests: TestResult,
    ) -> str:
        def icon(passed: bool) -> str:
            return "✅" if passed else "❌"

        lines = [
            "# 파이프라인 결과\n",
            f"{icon(lint.passed)} 린트: {lint.total_errors}개 에러, {lint.total_warnings}개 경고",
            f"{icon(type_check.passed)} 타입 체크: {type_check.total_errors}개 에러",
            f"{icon(structure.passed)} 구조 분석: {len(structure.violations)}개 위반",
            f"{icon(tests.passed)} 테스트: {tests.passed_count}/{tests.total} 통과",
        ]

        # 실패한 항목의 상세 정보 추가
        failed_details: list[str] = []
        if not lint.passed:
            failed_details.append(f"\n## 린트 상세\n{lint.summary_for_llm}")
        if not type_check.passed:
            failed_details.append(f"\n## 타입 체크 상세\n{type_check.summary_for_llm}")
        if not structure.passed:
            failed_details.append(f"\n## 구조 분석 상세\n{structure.summary_for_llm}")
        if not tests.passed:
            failed_details.append(f"\n## 테스트 상세\n{tests.summary_for_llm}")

        return "\n".join(lines) + "\n".join(failed_details)
