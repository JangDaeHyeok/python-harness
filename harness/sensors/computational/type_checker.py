"""연산적 센서: 타입 체커. mypy를 실행하고 결과를 구조화한다."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TypeIssue:
    """타입 체크 이슈."""

    file: str
    line: int
    severity: str
    message: str
    error_code: str


@dataclass
class TypeCheckResult:
    """타입 체크 결과."""

    passed: bool
    total_errors: int
    issues: list[TypeIssue]
    summary_for_llm: str


class TypeCheckerSensor:
    """연산적 피드백 센서: 타입 체커 (mypy)."""

    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir)

    def run_mypy(self, target: str = ".") -> TypeCheckResult:
        """mypy를 실행하고 결과를 구조화한다."""
        try:
            result = subprocess.run(
                ["mypy", target, "--no-color-output", "--show-error-codes", "--no-error-summary"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            return TypeCheckResult(True, 0, [], "mypy가 설치되어 있지 않습니다.")
        except subprocess.TimeoutExpired:
            return TypeCheckResult(False, 0, [], "mypy 실행 타임아웃 (120초)")

        return self._parse_mypy_output(result)

    def _parse_mypy_output(self, result: subprocess.CompletedProcess[str]) -> TypeCheckResult:
        issues: list[TypeIssue] = []
        output = result.stdout + result.stderr

        for line in output.splitlines():
            parsed = self._parse_line(line)
            if parsed:
                issues.append(parsed)

        return TypeCheckResult(
            passed=result.returncode == 0,
            total_errors=len(issues),
            issues=issues,
            summary_for_llm=self._build_summary(issues, result.returncode == 0),
        )

    def _parse_line(self, line: str) -> TypeIssue | None:
        # Format: file.py:10: error: Message [error-code]
        parts = line.split(":", 3)
        if len(parts) < 4:
            return None

        file_path = parts[0].strip()
        try:
            line_num = int(parts[1].strip())
        except ValueError:
            return None

        rest = parts[2].strip() + ":" + parts[3]
        severity = "error"
        if rest.startswith("error:"):
            severity = "error"
            message = rest[6:].strip()
        elif rest.startswith("warning:"):
            severity = "warning"
            message = rest[8:].strip()
        elif rest.startswith("note:"):
            severity = "note"
            message = rest[5:].strip()
        else:
            message = rest.strip()

        error_code = ""
        if message.endswith("]") and "[" in message:
            bracket_start = message.rfind("[")
            error_code = message[bracket_start + 1 : -1]
            message = message[:bracket_start].strip()

        return TypeIssue(
            file=file_path,
            line=line_num,
            severity=severity,
            message=message,
            error_code=error_code,
        )

    def _build_summary(self, issues: list[TypeIssue], passed: bool) -> str:
        if not issues:
            return "타입 체크 통과. 이슈 없음." if passed else "타입 체크 완료 (파싱 가능한 이슈 없음)."

        errors = [i for i in issues if i.severity == "error"]
        lines = [f"타입 체크 {'통과' if passed else '실패'}: {len(errors)}개 에러\n"]
        for issue in errors[:20]:
            lines.append(
                f"- {issue.file}:{issue.line} [{issue.error_code}]: {issue.message}"
            )
        if len(errors) > 20:
            lines.append(f"\n... 외 {len(errors) - 20}개 에러")
        return "\n".join(lines)
