"""연산적 센서: 린터. Ruff를 실행하고 LLM이 소비하기 쉬운 피드백을 생성한다."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar


@dataclass
class LintIssue:
    """린트 이슈."""

    file: str
    line: int
    column: int
    severity: str
    rule: str
    message: str
    fix_instruction: str


@dataclass
class LintResult:
    """린트 결과."""

    passed: bool
    total_errors: int
    total_warnings: int
    issues: list[LintIssue]
    summary_for_llm: str


class LinterSensor:
    """
    연산적 피드백 센서: 린터.
    린터 출력을 LLM이 이해하기 쉬운 형태로 변환한다.
    """

    RUFF_FIX_HINTS: ClassVar[dict[str, str]] = {
        "F401": "사용하지 않는 import를 제거하세요.",
        "F841": "사용하지 않는 변수를 제거하거나 _로 시작하는 이름으로 변경하세요.",
        "E711": "'== None' 대신 'is None'을 사용하세요.",
        "E712": "'== True/False' 대신 'is True/False' 또는 직접 비교를 사용하세요.",
        "I001": "import 순서를 정리하세요: 표준 라이브러리 → 서드파티 → 로컬.",
        "B006": "함수 기본 인자로 mutable 객체를 사용하지 마세요.",
        "UP035": "deprecated typing import를 내장 타입으로 교체하세요.",
    }

    def __init__(self, project_dir: str, custom_rules: list[dict[str, Any]] | None = None) -> None:
        self.project_dir = Path(project_dir)
        self.custom_rules = custom_rules or []

    def run_ruff(self) -> LintResult:
        """Ruff (Python 린터)를 실행하고 결과를 구조화한다."""
        try:
            result = subprocess.run(
                ["ruff", "check", ".", "--output-format", "json"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            return self._parse_ruff_json(result.stdout)
        except FileNotFoundError:
            return LintResult(True, 0, 0, [], "Ruff가 설치되어 있지 않습니다.")
        except subprocess.TimeoutExpired:
            return LintResult(False, 0, 0, [], "Ruff 실행 타임아웃 (60초)")

    def run_custom_rules(self) -> LintResult:
        """프로젝트별 커스텀 아키텍처 규칙을 검사한다."""
        issues: list[LintIssue] = []

        for rule in self.custom_rules:
            if rule["type"] == "forbidden_import":
                issues.extend(
                    self._check_forbidden_import(
                        rule["pattern"], rule["allowed_dirs"], rule["message"]
                    )
                )
            elif rule["type"] == "file_location":
                issues.extend(
                    self._check_file_location(
                        rule["pattern"], rule["required_dir"], rule["message"]
                    )
                )

        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        return LintResult(
            passed=len(errors) == 0,
            total_errors=len(errors),
            total_warnings=len(warnings),
            issues=issues,
            summary_for_llm=self._build_summary(issues),
        )

    def run_all(self) -> LintResult:
        """Ruff + 커스텀 규칙을 모두 실행한다."""
        ruff_result = self.run_ruff()
        custom_result = self.run_custom_rules()

        all_issues = ruff_result.issues + custom_result.issues
        total_errors = ruff_result.total_errors + custom_result.total_errors
        total_warnings = ruff_result.total_warnings + custom_result.total_warnings

        return LintResult(
            passed=ruff_result.passed and custom_result.passed,
            total_errors=total_errors,
            total_warnings=total_warnings,
            issues=all_issues,
            summary_for_llm=self._build_summary(all_issues),
        )

    def _check_forbidden_import(
        self, pattern: str, allowed_dirs: list[str], message: str
    ) -> list[LintIssue]:
        issues: list[LintIssue] = []
        for py_file in self.project_dir.rglob("*.py"):
            rel_path = str(py_file.relative_to(self.project_dir))
            if any(rel_path.startswith(d) for d in allowed_dirs):
                continue
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(pattern, line):
                    issues.append(LintIssue(
                        file=rel_path, line=i, column=0, severity="error",
                        rule="forbidden-import", message=message,
                        fix_instruction=f"이 import를 제거하고, {', '.join(allowed_dirs)} 내부에서만 사용하세요.",
                    ))
        return issues

    def _check_file_location(
        self, pattern: str, required_dir: str, message: str
    ) -> list[LintIssue]:
        issues: list[LintIssue] = []
        for py_file in self.project_dir.rglob("*.py"):
            rel_path = str(py_file.relative_to(self.project_dir))
            if rel_path.startswith(required_dir):
                continue
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if re.search(pattern, content):
                issues.append(LintIssue(
                    file=rel_path, line=0, column=0, severity="error",
                    rule="file-location", message=message,
                    fix_instruction=f"이 코드를 {required_dir} 디렉터리로 이동하세요.",
                ))
        return issues

    def _parse_ruff_json(self, output: str) -> LintResult:
        try:
            data = json.loads(output) if output.strip() else []
        except json.JSONDecodeError:
            return LintResult(True, 0, 0, [], "Ruff 출력 파싱 실패")

        issues: list[LintIssue] = []
        for item in data:
            code = item.get("code", "unknown")
            fix_hint = self.RUFF_FIX_HINTS.get(
                code, f"Ruff 규칙 {code} 위반을 수정하세요."
            )
            issues.append(LintIssue(
                file=item.get("filename", "unknown"),
                line=item.get("location", {}).get("row", 0),
                column=item.get("location", {}).get("column", 0),
                severity="error",
                rule=code,
                message=item.get("message", ""),
                fix_instruction=fix_hint,
            ))

        return LintResult(
            passed=len(issues) == 0,
            total_errors=len(issues),
            total_warnings=0,
            issues=issues,
            summary_for_llm=self._build_summary(issues),
        )

    def _build_summary(self, issues: list[LintIssue]) -> str:
        if not issues:
            return "린트 검사 통과. 이슈 없음."

        lines = [f"총 {len(issues)}개 이슈 발견:\n"]
        for issue in issues[:20]:
            lines.append(
                f"- [{issue.severity.upper()}] {issue.file}:{issue.line} "
                f"({issue.rule}): {issue.message}\n"
                f"  → 수정 방법: {issue.fix_instruction}"
            )
        if len(issues) > 20:
            lines.append(f"\n... 외 {len(issues) - 20}개 이슈")
        return "\n".join(lines)
