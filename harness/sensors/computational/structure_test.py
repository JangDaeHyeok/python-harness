"""연산적 센서: 구조 분석. 아키텍처 규칙과 ADR을 검증한다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class StructureViolation:
    """구조 위반."""

    rule_name: str
    file: str
    line: int
    message: str
    severity: str  # "error", "warning"


@dataclass
class StructureResult:
    """구조 분석 결과."""

    passed: bool
    violations: list[StructureViolation]
    summary_for_llm: str


@dataclass
class ADREntry:
    """Architecture Decision Record 항목."""

    id: str
    title: str
    status: str  # "accepted", "deprecated", "superseded"
    date: str
    context: str
    decision: str
    consequences: str
    enforced_by: list[str]  # 이 결정을 강제하는 규칙 이름들


class StructureAnalyzer:
    """
    구조 분석기.

    아키텍처 규칙을 정의하고 코드베이스에 대해 검증한다.
    ADR(Architecture Decision Records)과 연계하여
    모든 결정과 원칙을 코드로 강제할 수 있게 한다.
    """

    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir)
        self.rules: list[dict[str, Any]] = []
        self.adrs: list[ADREntry] = []
        self._load_config()
        self._load_adrs()

    def _load_config(self) -> None:
        """harness_structure.yaml에서 규칙을 로드한다."""
        config_path = self.project_dir / "harness_structure.yaml"
        if not config_path.exists():
            return
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self.rules = data.get("rules", [])

    def _load_adrs(self) -> None:
        """docs/adr/ 디렉터리에서 ADR을 로드한다."""
        adr_dir = self.project_dir / "docs" / "adr"
        if not adr_dir.exists():
            return
        for adr_file in sorted(adr_dir.glob("*.md")):
            adr = self._parse_adr(adr_file)
            if adr:
                self.adrs.append(adr)

    def _parse_adr(self, path: Path) -> ADREntry | None:
        """ADR 마크다운 파일을 파싱한다."""
        content = path.read_text(encoding="utf-8")
        sections: dict[str, str] = {}
        current_section = ""

        for line in content.splitlines():
            if line.startswith("# "):
                sections["title"] = line[2:].strip()
            elif line.startswith("## "):
                current_section = line[3:].strip().lower()
                sections[current_section] = ""
            elif current_section:
                sections[current_section] = sections.get(current_section, "") + line + "\n"

        title = sections.get("title", path.stem)

        # frontmatter에서 메타데이터 추출
        status = "accepted"
        date = ""
        enforced_by: list[str] = []
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                try:
                    meta = yaml.safe_load(content[3:end]) or {}
                    status = meta.get("status", "accepted")
                    date = meta.get("date", "")
                    enforced_by = meta.get("enforced_by", [])
                except yaml.YAMLError:
                    pass

        return ADREntry(
            id=path.stem,
            title=title,
            status=status,
            date=date,
            context=sections.get("context", "").strip(),
            decision=sections.get("decision", "").strip(),
            consequences=sections.get("consequences", "").strip(),
            enforced_by=enforced_by,
        )

    def analyze(self) -> StructureResult:
        """모든 구조 규칙을 검증한다."""
        violations: list[StructureViolation] = []

        for rule in self.rules:
            rule_type = rule.get("type", "")
            handler = self._get_handler(rule_type)
            if handler:
                violations.extend(handler(rule))

        errors = [v for v in violations if v.severity == "error"]
        return StructureResult(
            passed=len(errors) == 0,
            violations=violations,
            summary_for_llm=self._build_summary(violations),
        )

    def _get_handler(self, rule_type: str) -> Any:
        handlers = {
            "dependency_direction": self._check_dependency_direction,
            "layer_isolation": self._check_layer_isolation,
            "naming_convention": self._check_naming_convention,
            "required_files": self._check_required_files,
            "forbidden_pattern": self._check_forbidden_pattern,
        }
        return handlers.get(rule_type)

    def _check_dependency_direction(self, rule: dict[str, Any]) -> list[StructureViolation]:
        """의존성 방향 규칙: A 레이어는 B 레이어에 의존해서는 안 된다."""
        violations: list[StructureViolation] = []
        source_dir = rule.get("source", "")
        forbidden_imports = rule.get("forbidden_imports", [])

        source_path = self.project_dir / source_dir
        if not source_path.exists():
            return violations

        for py_file in source_path.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(py_file.relative_to(self.project_dir))
            for i, line in enumerate(content.splitlines(), 1):
                for forbidden in forbidden_imports:
                    if re.search(rf"(from|import)\s+{re.escape(forbidden)}", line):
                        violations.append(StructureViolation(
                            rule_name=rule.get("name", "dependency_direction"),
                            file=rel_path,
                            line=i,
                            message=f"'{source_dir}'에서 '{forbidden}'으로의 의존성이 금지되어 있습니다.",
                            severity="error",
                        ))
        return violations

    def _check_layer_isolation(self, rule: dict[str, Any]) -> list[StructureViolation]:
        """레이어 격리 규칙: 특정 디렉터리는 허용된 모듈만 import 가능."""
        violations: list[StructureViolation] = []
        layer_dir = rule.get("directory", "")
        allowed_imports = rule.get("allowed_imports", [])

        layer_path = self.project_dir / layer_dir
        if not layer_path.exists():
            return violations

        for py_file in layer_path.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(py_file.relative_to(self.project_dir))
            for i, line in enumerate(content.splitlines(), 1):
                match = re.match(r"^(?:from|import)\s+([\w.]+)", line)
                if not match:
                    continue
                module = match.group(1).split(".")[0]
                if module in allowed_imports or module.startswith("_"):
                    continue
                if module == layer_dir.split("/")[0]:
                    continue
                violations.append(StructureViolation(
                    rule_name=rule.get("name", "layer_isolation"),
                    file=rel_path,
                    line=i,
                    message=f"'{layer_dir}'에서 허용되지 않은 모듈 '{module}'을 import합니다.",
                    severity="error",
                ))

        return violations

    def _check_naming_convention(self, rule: dict[str, Any]) -> list[StructureViolation]:
        """네이밍 컨벤션 규칙: 파일명이 특정 패턴을 따라야 한다."""
        violations: list[StructureViolation] = []
        directory = rule.get("directory", "")
        pattern = rule.get("pattern", "")

        target = self.project_dir / directory
        if not target.exists():
            return violations

        for py_file in target.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            if not re.match(pattern, py_file.name):
                violations.append(StructureViolation(
                    rule_name=rule.get("name", "naming_convention"),
                    file=str(py_file.relative_to(self.project_dir)),
                    line=0,
                    message=f"파일명 '{py_file.name}'이 패턴 '{pattern}'을 따르지 않습니다.",
                    severity="warning",
                ))
        return violations

    def _check_required_files(self, rule: dict[str, Any]) -> list[StructureViolation]:
        """필수 파일 규칙: 특정 파일이 존재해야 한다."""
        violations: list[StructureViolation] = []
        for required in rule.get("files", []):
            if not (self.project_dir / required).exists():
                violations.append(StructureViolation(
                    rule_name=rule.get("name", "required_files"),
                    file=required,
                    line=0,
                    message=f"필수 파일 '{required}'이 존재하지 않습니다.",
                    severity="error",
                ))
        return violations

    def _check_forbidden_pattern(self, rule: dict[str, Any]) -> list[StructureViolation]:
        """금지 패턴 규칙: 특정 코드 패턴이 존재해서는 안 된다."""
        violations: list[StructureViolation] = []
        pattern = rule.get("pattern", "")
        directories = rule.get("directories", ["."])
        message = rule.get("message", f"금지된 패턴 '{pattern}' 발견")

        for directory in directories:
            target = self.project_dir / directory
            if not target.exists():
                continue
            for py_file in target.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                rel_path = str(py_file.relative_to(self.project_dir))
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line):
                        violations.append(StructureViolation(
                            rule_name=rule.get("name", "forbidden_pattern"),
                            file=rel_path,
                            line=i,
                            message=message,
                            severity=rule.get("severity", "error"),
                        ))
        return violations

    def get_adr_summary(self) -> str:
        """ADR 요약을 반환한다. 에이전트의 컨텍스트에 포함시킬 수 있는 짧은 형태."""
        if not self.adrs:
            return "ADR이 정의되어 있지 않습니다."

        lines = ["# Architecture Decision Records\n"]
        for adr in self.adrs:
            status_icon = {"accepted": "✅", "deprecated": "⚠️", "superseded": "🔄"}.get(
                adr.status, "❓"
            )
            lines.append(f"- {status_icon} **{adr.id}**: {adr.title} ({adr.status})")
            if adr.decision:
                first_line = adr.decision.splitlines()[0][:100]
                lines.append(f"  결정: {first_line}")
        return "\n".join(lines)

    def _build_summary(self, violations: list[StructureViolation]) -> str:
        if not violations:
            return "구조 분석 통과. 위반 없음."

        errors = [v for v in violations if v.severity == "error"]
        warnings = [v for v in violations if v.severity == "warning"]
        lines = [f"구조 분석: {len(errors)}개 에러, {len(warnings)}개 경고\n"]
        for v in violations[:20]:
            lines.append(
                f"- [{v.severity.upper()}] {v.file}:{v.line} ({v.rule_name}): {v.message}"
            )
        return "\n".join(lines)
