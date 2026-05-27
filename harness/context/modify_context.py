"""기존 코드베이스 수정 모드의 컨텍스트 수집기.

modify 모드에서 Planner에게 전달할 현재 프로젝트 상태를 수집한다.
"""

from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from harness.tools.adr import ADRLoader
from harness.tools.path_safety import sanitize_branch_name
from harness.tools.shell import run_argv_safe

if TYPE_CHECKING:
    from harness.context.project_policy import ProjectPolicy

logger = logging.getLogger(__name__)

_COLLECT_TIMEOUT = 30
_DIFF_PREVIEW_LIMIT = 5000
_CONVENTION_PREVIEW_LIMIT = 3000
_STRUCTURE_PREVIEW_LIMIT = 2000
_DEPENDENCY_FILE_LIMIT = 120_000
_SOURCE_SCAN_LIMIT = 200
_SOURCE_FILE_LIMIT = 200_000

_PROJECT_MARKERS = (
    "pyproject.toml",
    "setup.py",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
)

_LIBRARY_ALIASES = {
    "requests": "requests",
    "httpx": "httpx",
    "click": "click",
    "typer": "typer",
    "pytest": "pytest",
    "unittest": "unittest",
    "argparse": "argparse",
}


def _truncate_with_notice(text: str, limit: int) -> str:
    """텍스트를 제한 길이로 자르고 원본 길이를 표시한다."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n\n[잘림: 원본 {len(text)}자, 표시 {limit}자]"


@dataclass
class ModifyContext:
    """수정 모드에서 수집된 프로젝트 컨텍스트."""

    git_branch: str = ""
    git_diff: str = ""
    changed_files: list[str] = field(default_factory=list)
    design_intent: str = ""
    code_convention: str = ""
    adrs: list[dict[str, str]] = field(default_factory=list)
    structure_rules: str = ""
    recent_test_summary: str = ""
    project_policy: str = ""
    python_project_summary: str = ""

    def to_markdown(self) -> str:
        """수집된 컨텍스트를 마크다운으로 변환한다."""
        sections: list[str] = ["# 프로젝트 수정 컨텍스트\n"]

        sections.append(f"## Git 브랜치\n\n`{self.git_branch}`\n")

        if self.changed_files:
            sections.append("## 변경된 파일\n")
            for f in self.changed_files:
                sections.append(f"- `{f}`")
            sections.append("")

        if self.git_diff:
            sections.append("## Git Diff\n")
            diff_preview = _truncate_with_notice(self.git_diff, _DIFF_PREVIEW_LIMIT)
            sections.append(f"```diff\n{diff_preview}\n```\n")

        if self.design_intent:
            sections.append(f"## 설계 의도\n\n{self.design_intent}\n")

        if self.code_convention:
            conv_preview = _truncate_with_notice(
                self.code_convention, _CONVENTION_PREVIEW_LIMIT,
            )
            sections.append(f"## 코드 컨벤션\n\n```yaml\n{conv_preview}\n```\n")

        if self.adrs:
            sections.append("## 아키텍처 결정 (ADR)\n")
            for adr in self.adrs:
                source_tag = f" (외부: {adr['source']})" if adr.get("source") else ""
                sections.append(f"### {adr.get('filename', '')}: {adr.get('title', '')}{source_tag}")
                sections.append(f"상태: {adr.get('status', 'unknown')}\n")
            sections.append("")

        if self.structure_rules:
            rules_preview = _truncate_with_notice(
                self.structure_rules, _STRUCTURE_PREVIEW_LIMIT,
            )
            sections.append(f"## 구조 규칙\n\n```yaml\n{rules_preview}\n```\n")

        if self.recent_test_summary:
            sections.append(f"## 최근 검증 결과\n\n{self.recent_test_summary}\n")

        if self.project_policy:
            sections.append(f"## 프로젝트 정책\n\n```yaml\n{self.project_policy}\n```\n")

        if self.python_project_summary:
            sections.append(f"## Python 프로젝트 감지 요약\n\n{self.python_project_summary}\n")

        return "\n".join(sections)


class ModifyContextCollector:
    """modify 모드를 위한 프로젝트 컨텍스트 수집기."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)

    def collect(self, policy: ProjectPolicy | None = None) -> ModifyContext:
        """프로젝트 컨텍스트를 수집한다.

        Args:
            policy: 프로젝트 정책. None이면 기본 경로를 사용한다.
        """
        convention_path = (
            self.project_dir / policy.conventions_source
            if policy
            else self.project_dir / "docs" / "code-convention.yaml"
        )
        adr_dir = (
            self.project_dir / policy.adr_directory
            if policy
            else self.project_dir / "docs" / "adr"
        )
        structure_path = (
            self.project_dir / policy.structure_source
            if policy
            else self.project_dir / "harness_structure.yaml"
        )

        adrs = self._load_adrs(adr_dir)
        if policy and policy.external_adr_sources:
            adrs.extend(ADRLoader.load_from_external_sources(policy.external_adr_sources))

        ctx = ModifyContext(
            git_branch=self._get_git_branch(),
            git_diff=self._get_git_diff(),
            changed_files=self._get_changed_files(),
            design_intent=self._read_file_safe(
                self._find_latest_design_intent()
            ),
            code_convention=self._read_file_safe(convention_path),
            adrs=adrs,
            structure_rules=self._read_file_safe(structure_path),
            recent_test_summary=self._get_recent_test_summary(),
            project_policy=self._read_file_safe(
                self.project_dir / ".harness" / "project-policy.yaml"
            ),
            python_project_summary=self._collect_python_project_summary(),
        )
        logger.info(
            "수정 컨텍스트 수집 완료: branch=%s, changed_files=%d, adrs=%d",
            ctx.git_branch,
            len(ctx.changed_files),
            len(ctx.adrs),
        )
        return ctx

    def _get_git_branch(self) -> str:
        return self._run_git("branch", "--show-current") or "unknown"

    def _get_git_diff(self) -> str:
        staged = self._run_git("diff", "--cached")
        unstaged = self._run_git("diff")
        parts: list[str] = []
        if staged:
            parts.append(f"### Staged\n{staged}")
        if unstaged:
            parts.append(f"### Unstaged\n{unstaged}")
        return "\n\n".join(parts)

    def _get_changed_files(self) -> list[str]:
        output = self._run_git("status", "--porcelain")
        if not output:
            return []
        return [
            line[3:].strip()
            for line in output.splitlines()
            if line.strip()
        ]

    def _load_adrs(self, adr_dir: Path | None = None) -> list[dict[str, str]]:
        if adr_dir is None:
            adr_dir = self.project_dir / "docs" / "adr"
        if not adr_dir.exists():
            return []
        adrs: list[dict[str, str]] = []
        for path in sorted(adr_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            title = "제목 없음"
            status = "unknown"
            for line in content.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            match = re.search(r"status:\s*(\w+)", content)
            if match:
                status = match.group(1)
            adrs.append({
                "filename": path.name,
                "title": title,
                "status": status,
                "content": content,
            })
        return adrs

    def _find_latest_design_intent(self) -> Path:
        artifacts_dir = self.project_dir / ".harness" / "review-artifacts"
        if not artifacts_dir.exists():
            return artifacts_dir / "unknown-branch" / "design-intent.md"
        branch = self._get_git_branch()
        sanitized = sanitize_branch_name(branch)
        return artifacts_dir / sanitized / "design-intent.md"

    def _get_recent_test_summary(self) -> str:
        parts: list[str] = []
        ruff = self._run_cmd("ruff", "check", ".", "--quiet")
        if ruff is not None:
            parts.append(f"### Ruff\n{ruff or '에러 없음'}")
        mypy = self._run_cmd("mypy", "harness", "--no-error-summary")
        if mypy is not None:
            parts.append(f"### Mypy\n{mypy or '에러 없음'}")
        return "\n\n".join(parts) if parts else ""

    def _collect_python_project_summary(self) -> str:
        files = self._detect_project_files()
        dependencies = self._collect_dependency_names()
        imports = self._collect_import_names()
        libraries = self._detect_library_hints(dependencies, imports)
        lines = [
            f"- 프로젝트 파일: {', '.join(files) if files else '감지 없음'}",
            f"- package_manager: {self._detect_package_manager(files)}",
            f"- layout: {self._detect_layout()}",
            f"- 주요 라이브러리 힌트: {', '.join(libraries) if libraries else '감지 없음'}",
        ]
        recent_commits = self._get_recent_commit_messages()
        if recent_commits:
            lines.append("- 최근 커밋 메시지:")
            lines.extend(f"  - {message}" for message in recent_commits)
        return "\n".join(lines)

    def _detect_project_files(self) -> list[str]:
        files = [name for name in _PROJECT_MARKERS if (self.project_dir / name).exists()]
        files.extend(
            sorted(path.name for path in self.project_dir.glob("requirements*.txt"))
        )
        return files

    def _detect_package_manager(self, files: list[str]) -> str:
        if "uv.lock" in files:
            return "uv"
        if "poetry.lock" in files or self._pyproject_has_poetry():
            return "poetry"
        if "Pipfile" in files:
            return "pipenv"
        if any(name.startswith("requirements") and name.endswith(".txt") for name in files):
            return "pip"
        if "pyproject.toml" in files:
            return "pyproject"
        if "setup.py" in files:
            return "setuptools"
        return "unknown"

    def _detect_layout(self) -> str:
        src_dir = self.project_dir / "src"
        if src_dir.exists() and any(src_dir.glob("*/__init__.py")):
            return "src"
        flat_packages = [
            path.name
            for path in self.project_dir.iterdir()
            if path.is_dir()
            and not path.name.startswith(".")
            and path.name not in {"build", "dist", "docs", "src", "tests"}
            and (path / "__init__.py").exists()
        ]
        if flat_packages:
            return f"flat ({', '.join(sorted(flat_packages)[:5])})"
        return "unknown"

    def _collect_dependency_names(self) -> set[str]:
        names: set[str] = set()
        names.update(self._dependencies_from_pyproject())
        for path in sorted(self.project_dir.glob("requirements*.txt")):
            names.update(self._dependencies_from_requirements(path))
        return names

    def _dependencies_from_pyproject(self) -> set[str]:
        path = self.project_dir / "pyproject.toml"
        if not path.exists() or path.stat().st_size > _DEPENDENCY_FILE_LIMIT:
            return set()
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as e:
            logger.warning("pyproject.toml 요약 읽기 실패: %s", e)
            return set()

        raw_dependencies: list[object] = []
        project = data.get("project")
        if isinstance(project, dict):
            dependencies = project.get("dependencies")
            if isinstance(dependencies, list):
                raw_dependencies.extend(dependencies)
            optional = project.get("optional-dependencies")
            if isinstance(optional, dict):
                for group in optional.values():
                    if isinstance(group, list):
                        raw_dependencies.extend(group)

        tool = data.get("tool")
        if isinstance(tool, dict):
            poetry = tool.get("poetry")
            if isinstance(poetry, dict):
                dependencies = poetry.get("dependencies")
                if isinstance(dependencies, dict):
                    raw_dependencies.extend(self._poetry_dependency_specs(dependencies))
                groups = poetry.get("group")
                if isinstance(groups, dict):
                    for group in groups.values():
                        if isinstance(group, dict):
                            group_dependencies = group.get("dependencies")
                            if isinstance(group_dependencies, dict):
                                raw_dependencies.extend(
                                    self._poetry_dependency_specs(group_dependencies)
                                )

        return {self._normalize_dependency(str(dep)) for dep in raw_dependencies if dep}

    def _dependencies_from_requirements(self, path: Path) -> set[str]:
        if path.stat().st_size > _DEPENDENCY_FILE_LIMIT:
            return set()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            logger.warning("requirements 요약 읽기 실패 (%s): %s", path, e)
            return set()
        return {
            self._normalize_dependency(line)
            for line in lines
            if line.strip() and not line.lstrip().startswith(("#", "-"))
        }

    def _poetry_dependency_specs(self, dependencies: dict[object, object]) -> list[str]:
        specs: list[str] = []
        for name, version in dependencies.items():
            if not isinstance(name, str) or name.lower() == "python":
                continue
            if isinstance(version, str):
                specs.append(f"{name}{version}")
            else:
                specs.append(name)
        return specs

    def _collect_import_names(self) -> set[str]:
        imports: set[str] = set()
        scanned = 0
        for path in self.project_dir.rglob("*.py"):
            if scanned >= _SOURCE_SCAN_LIMIT:
                break
            if any(part in {".git", ".venv", "__pycache__", "build", "dist"} for part in path.parts):
                continue
            if path.stat().st_size > _SOURCE_FILE_LIMIT:
                continue
            scanned += 1
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            imports.update(re.findall(r"^\s*(?:from|import)\s+([a-zA-Z_][\w]*)", content, re.MULTILINE))
            if "pydantic.v1" in content:
                imports.add("pydantic.v1")
        return imports

    def _detect_library_hints(self, dependencies: set[str], imports: set[str]) -> list[str]:
        normalized = {name.lower() for name in dependencies | imports}
        hints: list[str] = []
        pydantic_hint = self._detect_pydantic_version(normalized)
        if pydantic_hint:
            hints.append(pydantic_hint)
        for raw, label in _LIBRARY_ALIASES.items():
            if raw in normalized:
                hints.append(label)
        return sorted(dict.fromkeys(hints))

    def _detect_pydantic_version(self, names: set[str]) -> str:
        if "pydantic.v1" in names:
            return "pydantic v1"
        if any(name.startswith("pydantic<2") or name.startswith("pydantic = <2") for name in names):
            return "pydantic v1"
        if any(
            name.startswith(("pydantic>=2", "pydantic^2", "pydantic~=2"))
            or name.startswith("pydantic = ^2")
            for name in names
        ):
            return "pydantic v2"
        if "pydantic" in names:
            return "pydantic"
        return ""

    def _normalize_dependency(self, value: str) -> str:
        stripped = value.strip().strip("'\"")
        if not stripped:
            return ""
        lower = stripped.lower()
        if lower.startswith("pydantic"):
            return re.split(r"\s|;", lower, maxsplit=1)[0]
        return re.split(r"\s|[<>=!~;\[]", stripped, maxsplit=1)[0].lower()

    def _pyproject_has_poetry(self) -> bool:
        path = self.project_dir / "pyproject.toml"
        if not path.exists() or path.stat().st_size > _DEPENDENCY_FILE_LIMIT:
            return False
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return False
        tool = data.get("tool")
        return isinstance(tool, dict) and isinstance(tool.get("poetry"), dict)

    def _get_recent_commit_messages(self) -> list[str]:
        output = self._run_git("log", "-5", "--pretty=format:%s")
        return [line.strip() for line in output.splitlines() if line.strip()][:5]

    def _run_git(self, *args: str) -> str:
        result = run_argv_safe(["git", *args], self.project_dir, timeout=_COLLECT_TIMEOUT)
        if result.error_message:
            logger.warning("git 명령 실행 실패 (%s): %s", " ".join(args), result.error_message)
            return ""
        if result.returncode != 0:
            logger.warning("git 명령 실패 (%s): %s", " ".join(args), result.stderr.strip())
            return ""
        return result.stdout.strip()

    def _run_cmd(self, *args: str) -> str | None:
        result = run_argv_safe(list(args), self.project_dir, timeout=_COLLECT_TIMEOUT)
        if result.error_message:
            logger.warning("명령 실행 실패 (%s): %s", " ".join(args), result.error_message)
            return None
        return result.stdout.strip() + result.stderr.strip()

    def _read_file_safe(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("파일 읽기 실패 (%s): %s", path, e)
            return ""
