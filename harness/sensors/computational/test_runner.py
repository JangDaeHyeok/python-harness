"""연산적 센서: 테스트 러너. pytest를 실행하고 결과를 구조화한다."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestCase:
    """테스트 케이스 결과."""

    name: str
    outcome: str  # "passed", "failed", "error", "skipped"
    duration: float
    message: str = ""


@dataclass
class TestResult:
    """테스트 실행 결과."""

    passed: bool
    total: int
    passed_count: int
    failed_count: int
    error_count: int
    skipped_count: int
    test_cases: list[TestCase]
    coverage_percent: float | None
    summary_for_llm: str


class TestRunnerSensor:
    """연산적 피드백 센서: 테스트 러너."""

    def __init__(
        self,
        project_dir: str,
        command: str = "pytest",
        timeout: int = 300,
        coverage: bool = False,
        min_coverage: float | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.command = command
        self.timeout = timeout
        self.coverage = coverage
        self.min_coverage = min_coverage

    def run_pytest(self, coverage: bool = True) -> TestResult:
        """pytest를 실행하고 결과를 구조화한다."""
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "--tb=short",
            "-q",
            "--json-report",
            "--json-report-file=-",
        ]
        if coverage:
            cmd.extend(["--cov=.", "--cov-report=json:/dev/stdout"])

        try:
            result = subprocess.run(
                cmd, cwd=str(self.project_dir),
                capture_output=True, text=True, timeout=300,
            )
        except FileNotFoundError:
            return TestResult(
                passed=False, total=0, passed_count=0, failed_count=0,
                error_count=0, skipped_count=0, test_cases=[],
                coverage_percent=None,
                summary_for_llm="[ENV] pytest이(가) 설치되어 있지 않습니다. pip install pytest 후 다시 시도하세요.",
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                passed=False, total=0, passed_count=0, failed_count=0,
                error_count=0, skipped_count=0, test_cases=[],
                coverage_percent=None, summary_for_llm="테스트 실행 타임아웃 (300초)",
            )

        if self._is_missing_pytest_module(result):
            return self._missing_pytest_result()

        parsed = self._parse_pytest_output(result)
        return self._apply_coverage_threshold(parsed, self.min_coverage)

    def run_pytest_simple(
        self,
        command: str | None = None,
        timeout: int | None = None,
        coverage: bool | None = None,
        min_coverage: float | None = None,
    ) -> TestResult:
        """pytest를 JSON report 없이 간단하게 실행한다."""
        effective_coverage = self.coverage if coverage is None else coverage
        effective_min_coverage = self.min_coverage if min_coverage is None else min_coverage
        cmd = self._build_simple_command(command or self.command, effective_coverage)
        effective_timeout = self.timeout if timeout is None else timeout
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.project_dir),
                capture_output=True, text=True, timeout=effective_timeout,
            )
        except FileNotFoundError:
            return TestResult(
                passed=False, total=0, passed_count=0, failed_count=0,
                error_count=0, skipped_count=0, test_cases=[],
                coverage_percent=None,
                summary_for_llm="[ENV] pytest이(가) 설치되어 있지 않습니다. pip install pytest 후 다시 시도하세요.",
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                passed=False, total=0, passed_count=0, failed_count=0,
                error_count=0, skipped_count=0, test_cases=[],
                coverage_percent=None,
                summary_for_llm=f"테스트 실행 타임아웃 ({effective_timeout}초)",
            )

        if self._is_missing_pytest_module(result):
            return self._missing_pytest_result()

        parsed = self._parse_simple_output(result)
        return self._apply_coverage_threshold(parsed, effective_min_coverage)

    def _missing_pytest_result(self) -> TestResult:
        return TestResult(
            passed=False, total=0, passed_count=0, failed_count=0,
            error_count=0, skipped_count=0, test_cases=[],
            coverage_percent=None,
            summary_for_llm="[ENV] pytest이(가) 설치되어 있지 않습니다. pip install pytest 후 다시 시도하세요.",
        )

    def _is_missing_pytest_module(
        self, result: subprocess.CompletedProcess[str]
    ) -> bool:
        output = result.stdout + "\n" + result.stderr
        return "No module named pytest" in output or "No module named 'pytest'" in output

    def _build_simple_command(self, command: str, coverage: bool) -> list[str]:
        cmd = shlex.split(command) if command else [sys.executable, "-m", "pytest"]
        if cmd and cmd[0] == "pytest":
            cmd = [sys.executable, "-m", *cmd]
        if "--tb=short" not in cmd:
            cmd.append("--tb=short")
        if "-v" not in cmd and "--verbose" not in cmd and "-q" not in cmd:
            cmd.append("-v")
        if coverage and not any(part.startswith("--cov") for part in cmd):
            cmd.extend(["--cov=.", "--cov-report=term-missing"])
        return cmd

    def _parse_pytest_output(self, result: subprocess.CompletedProcess[str]) -> TestResult:
        """pytest JSON report 출력을 파싱한다."""
        test_cases: list[TestCase] = []
        coverage_percent: float | None = None

        # JSON report 파싱 시도
        try:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    data = json.loads(line)
                    if "tests" in data:
                        for t in data["tests"]:
                            test_cases.append(TestCase(
                                name=t.get("nodeid", "unknown"),
                                outcome=t.get("outcome", "unknown"),
                                duration=t.get("duration", 0.0),
                                message=t.get("call", {}).get("longrepr", "")[:500] if isinstance(t.get("call"), dict) else "",
                            ))
                    if "totals" in data.get("summary", {}):
                        coverage_percent = data["summary"]["totals"].get("percent_covered")
                    break
        except (json.JSONDecodeError, KeyError):
            pass

        if not test_cases:
            return self._parse_simple_output(result)

        passed_count = sum(1 for t in test_cases if t.outcome == "passed")
        failed_count = sum(1 for t in test_cases if t.outcome == "failed")
        error_count = sum(1 for t in test_cases if t.outcome == "error")
        skipped_count = sum(1 for t in test_cases if t.outcome == "skipped")

        return TestResult(
            passed=result.returncode == 0,
            total=len(test_cases),
            passed_count=passed_count,
            failed_count=failed_count,
            error_count=error_count,
            skipped_count=skipped_count,
            test_cases=test_cases,
            coverage_percent=coverage_percent,
            summary_for_llm=self._build_summary(
                result.returncode == 0, test_cases, coverage_percent
            ),
        )

    def _parse_simple_output(self, result: subprocess.CompletedProcess[str]) -> TestResult:
        """pytest의 텍스트 출력을 간단히 파싱한다."""
        output = result.stdout + "\n" + result.stderr
        passed = result.returncode == 0
        coverage_percent = self._parse_coverage_percent(output)

        passed_count = output.count(" PASSED")
        failed_count = output.count(" FAILED")
        error_count = output.count(" ERROR")
        skipped_count = output.count(" SKIPPED")
        total = passed_count + failed_count + error_count + skipped_count

        summary = f"테스트 결과: {'통과' if passed else '실패'}\n"
        summary += f"총 {total}개 — 통과: {passed_count}, 실패: {failed_count}, 에러: {error_count}, 스킵: {skipped_count}\n"
        if coverage_percent is not None:
            summary += f"커버리지: {coverage_percent:.1f}%\n"
        if not passed:
            # 실패한 테스트 출력의 마지막 부분
            summary += f"\n출력:\n{output[-2000:]}"

        return TestResult(
            passed=passed,
            total=total,
            passed_count=passed_count,
            failed_count=failed_count,
            error_count=error_count,
            skipped_count=skipped_count,
            test_cases=[],
            coverage_percent=coverage_percent,
            summary_for_llm=summary,
        )

    def _parse_coverage_percent(self, output: str) -> float | None:
        match = re.search(r"^TOTAL\s+.*\s+(\d+(?:\.\d+)?)%", output, re.MULTILINE)
        if not match:
            return None
        return float(match.group(1))

    def _apply_coverage_threshold(
        self, result: TestResult, min_coverage: float | None
    ) -> TestResult:
        if min_coverage is None:
            return result
        if result.coverage_percent is None:
            result.passed = False
            result.summary_for_llm += (
                f"\n커버리지 정보를 찾지 못했습니다. 최소 기준: {min_coverage:.1f}%"
            )
            return result
        if result.coverage_percent < min_coverage:
            result.passed = False
            result.summary_for_llm += (
                f"\n커버리지 기준 미달: {result.coverage_percent:.1f}% < {min_coverage:.1f}%"
            )
        return result

    def _build_summary(
        self,
        passed: bool,
        test_cases: list[TestCase],
        coverage: float | None,
    ) -> str:
        lines = [f"테스트 결과: {'통과' if passed else '실패'}"]
        lines.append(
            f"총 {len(test_cases)}개 — "
            f"통과: {sum(1 for t in test_cases if t.outcome == 'passed')}, "
            f"실패: {sum(1 for t in test_cases if t.outcome == 'failed')}, "
            f"에러: {sum(1 for t in test_cases if t.outcome == 'error')}"
        )
        if coverage is not None:
            lines.append(f"커버리지: {coverage:.1f}%")

        failed = [t for t in test_cases if t.outcome in ("failed", "error")]
        if failed:
            lines.append("\n실패한 테스트:")
            for t in failed[:10]:
                lines.append(f"  - {t.name}: {t.message[:200]}")

        return "\n".join(lines)
