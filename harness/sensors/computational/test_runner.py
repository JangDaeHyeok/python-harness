"""연산적 센서: 테스트 러너. pytest를 실행하고 결과를 구조화한다."""

from __future__ import annotations

import json
import subprocess
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

    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir)

    def run_pytest(self, coverage: bool = True) -> TestResult:
        """pytest를 실행하고 결과를 구조화한다."""
        cmd = ["python", "-m", "pytest", "--tb=short", "-q", "--json-report", "--json-report-file=-"]
        if coverage:
            cmd.extend(["--cov=.", "--cov-report=json:/dev/stdout"])

        try:
            result = subprocess.run(
                cmd, cwd=str(self.project_dir),
                capture_output=True, text=True, timeout=300,
            )
        except FileNotFoundError:
            return TestResult(
                passed=True, total=0, passed_count=0, failed_count=0,
                error_count=0, skipped_count=0, test_cases=[],
                coverage_percent=None, summary_for_llm="pytest가 설치되어 있지 않습니다.",
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                passed=False, total=0, passed_count=0, failed_count=0,
                error_count=0, skipped_count=0, test_cases=[],
                coverage_percent=None, summary_for_llm="테스트 실행 타임아웃 (300초)",
            )

        return self._parse_pytest_output(result)

    def run_pytest_simple(self) -> TestResult:
        """pytest를 JSON report 없이 간단하게 실행한다."""
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "--tb=short", "-v"],
                cwd=str(self.project_dir),
                capture_output=True, text=True, timeout=300,
            )
        except FileNotFoundError:
            return TestResult(
                passed=True, total=0, passed_count=0, failed_count=0,
                error_count=0, skipped_count=0, test_cases=[],
                coverage_percent=None, summary_for_llm="pytest가 설치되어 있지 않습니다.",
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                passed=False, total=0, passed_count=0, failed_count=0,
                error_count=0, skipped_count=0, test_cases=[],
                coverage_percent=None, summary_for_llm="테스트 실행 타임아웃 (300초)",
            )

        return self._parse_simple_output(result)

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

        passed_count = output.count(" PASSED")
        failed_count = output.count(" FAILED")
        error_count = output.count(" ERROR")
        skipped_count = output.count(" SKIPPED")
        total = passed_count + failed_count + error_count + skipped_count

        summary = f"테스트 결과: {'통과' if passed else '실패'}\n"
        summary += f"총 {total}개 — 통과: {passed_count}, 실패: {failed_count}, 에러: {error_count}, 스킵: {skipped_count}\n"
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
            coverage_percent=None,
            summary_for_llm=summary,
        )

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
