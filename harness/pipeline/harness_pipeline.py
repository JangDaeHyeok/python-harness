"""하네스 파이프라인. 모든 센서를 순차적으로 실행하고 결과를 통합한다."""

from __future__ import annotations

import logging
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.context.project_policy import ProjectPolicy
from harness.sensors.computational.linter import LinterSensor, LintResult
from harness.sensors.computational.structure_test import StructureAnalyzer, StructureResult
from harness.sensors.computational.test_runner import TestResult, TestRunnerSensor
from harness.sensors.computational.type_checker import TypeCheckerSensor, TypeCheckResult
from harness.tools.shell import run_argv_safe

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


PipelineReport = PipelineResult


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
        policy: ProjectPolicy | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.policy = policy or ProjectPolicy()
        self.linter = LinterSensor(
            project_dir, custom_lint_rules or self.policy.custom_rules
        )
        self.test_runner = TestRunnerSensor(
            project_dir,
            command=self.policy.commands.test,
            timeout=self.policy.pytest_timeout,
            coverage=self.policy.pytest_coverage,
            min_coverage=self.policy.min_coverage,
        )
        self.type_checker = TypeCheckerSensor(project_dir)
        self.structure_analyzer = StructureAnalyzer(project_dir)

    def run_all(self) -> PipelineResult:
        """모든 센서를 실행하고 통합 결과를 반환한다."""
        logger.info("파이프라인 실행 시작")
        required_checks = self._required_checks()

        # 1. 유지보수성 하네스
        lint_result: LintResult | None = None
        if "ruff" in required_checks:
            logger.info("  [1/4] 린트 검사...")
            lint_result = self.linter.run_all(self.policy.commands.lint)

        type_result: TypeCheckResult | None = None
        if "mypy" in required_checks:
            logger.info("  [2/4] 타입 체크...")
            type_result = self.type_checker.run_mypy(command=self.policy.commands.type)

        # 2. 아키텍처 적합성 하네스
        structure_result: StructureResult | None = None
        if "structure" in required_checks:
            logger.info("  [3/4] 구조 분석...")
            structure_result = self._run_structure_check()

        # 3. 행동 하네스
        test_result: TestResult | None = None
        if "pytest" in required_checks:
            logger.info("  [4/4] 테스트 실행...")
            test_result = self.test_runner.run_pytest_simple()

        # 통합
        all_passed = all(
            result.passed
            for result in [lint_result, type_result, structure_result, test_result]
            if result is not None
        )

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
                "required_checks": sorted(required_checks),
                "lint_passed": None if lint_result is None else lint_result.passed,
                "type_check_passed": None if type_result is None else type_result.passed,
                "structure_passed": None if structure_result is None else structure_result.passed,
                "tests_passed": None if test_result is None else test_result.passed,
            },
        )

    def run_fast(self) -> PipelineResult:
        """빠른 검사만 실행한다 (린트 + 타입 체크)."""
        lint_result = self.linter.run_ruff(self.policy.commands.lint)
        type_result = self.type_checker.run_mypy(command=self.policy.commands.type)

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
        lint: LintResult | None,
        type_check: TypeCheckResult | None,
        structure: StructureResult | None,
        tests: TestResult | None,
    ) -> str:
        lines = [
            "# 파이프라인 결과\n",
            self._lint_summary_line(lint),
            self._type_summary_line(type_check),
            self._structure_summary_line(structure),
            self._test_summary_line(tests),
        ]

        # 실패한 항목의 상세 정보 추가
        failed_details: list[str] = []
        if lint is not None and not lint.passed:
            failed_details.append(f"\n## 린트 상세\n{lint.summary_for_llm}")
        if type_check is not None and not type_check.passed:
            failed_details.append(f"\n## 타입 체크 상세\n{type_check.summary_for_llm}")
        if structure is not None and not structure.passed:
            failed_details.append(f"\n## 구조 분석 상세\n{structure.summary_for_llm}")
        if tests is not None and not tests.passed:
            failed_details.append(f"\n## 테스트 상세\n{tests.summary_for_llm}")

        return "\n".join(lines) + "\n".join(failed_details)

    def _required_checks(self) -> set[str]:
        aliases = {
            "lint": "ruff",
            "ruff": "ruff",
            "type": "mypy",
            "mypy": "mypy",
            "test": "pytest",
            "tests": "pytest",
            "pytest": "pytest",
            "structure": "structure",
        }
        return {
            aliases[check]
            for check in self.policy.required_checks
            if check in aliases
        }

    def _run_structure_check(self) -> StructureResult:
        command = self.policy.commands.structure
        default_command = ProjectPolicy().commands.structure
        script_exists = (Path(self.project_dir) / "scripts" / "check_structure.py").exists()
        if command == default_command and not script_exists:
            return self.structure_analyzer.analyze()
        result = run_argv_safe(
            self._python_command(shlex.split(command)),
            self.project_dir,
            timeout=120,
        )
        if result.returncode == 127:
            return StructureResult(
                passed=False,
                violations=[],
                summary_for_llm="[ENV] 구조 검사 명령을 찾을 수 없습니다.",
            )
        if result.timed_out:
            return StructureResult(
                passed=False,
                violations=[],
                summary_for_llm="구조 검사 실행 타임아웃 (120초)",
            )
        if result.error_message:
            return StructureResult(
                passed=False,
                violations=[],
                summary_for_llm=f"구조 검사 실행 실패: {result.error_message}",
            )
        output = (result.stdout + "\n" + result.stderr).strip()
        return StructureResult(
            passed=result.returncode == 0,
            violations=[],
            summary_for_llm=output or "구조 검사 통과. 위반 없음.",
        )

    def _python_command(self, cmd: list[str]) -> list[str]:
        if cmd and cmd[0] == "python":
            return [sys.executable, *cmd[1:]]
        return cmd

    def _lint_summary_line(self, lint: LintResult | None) -> str:
        if lint is None:
            return "⏭️ 린트: 정책에서 제외"
        return (
            f"{self._icon(lint.passed)} 린트: "
            f"{lint.total_errors}개 에러, {lint.total_warnings}개 경고"
        )

    def _type_summary_line(self, type_check: TypeCheckResult | None) -> str:
        if type_check is None:
            return "⏭️ 타입 체크: 정책에서 제외"
        return f"{self._icon(type_check.passed)} 타입 체크: {type_check.total_errors}개 에러"

    def _structure_summary_line(self, structure: StructureResult | None) -> str:
        if structure is None:
            return "⏭️ 구조 분석: 정책에서 제외"
        return f"{self._icon(structure.passed)} 구조 분석: {len(structure.violations)}개 위반"

    def _test_summary_line(self, tests: TestResult | None) -> str:
        if tests is None:
            return "⏭️ 테스트: 정책에서 제외"
        return f"{self._icon(tests.passed)} 테스트: {tests.passed_count}/{tests.total} 통과"

    def _icon(self, passed: bool) -> str:
        return "✅" if passed else "❌"
