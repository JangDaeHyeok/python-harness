"""프로젝트 초기 환경 구성기.

대상 프로젝트 디렉터리에 다음 파일을 생성·관리한다.

- ``docs/adr/0001-initial-architecture.md``
- ``docs/code-convention.yaml``
- ``harness_structure.yaml``
- ``.harness/project-policy.yaml``
- ``CLAUDE.md`` (선택)
- ``.claude/settings.json``과 Stop 훅 스크립트

LLM 엔드포인트가 설정되어 있고 ``offline=False`` 인 경우, 자연어 요청을 기반으로
각 파일 내용을 LLM이 다듬도록 시도한다. 호출이 실패하거나 응답이 비정상이면
내장 템플릿으로 안전하게 폴백한다 (예외 전파 금지).
"""

from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from harness.bootstrap.templates import (
    TemplateContext,
    render_adr,
    render_ci,
    render_claude_md,
    render_claude_settings,
    render_coderabbit_config,
    render_convention,
    render_gitignore,
    render_migration_structure,
    render_package_init,
    render_policy,
    render_post_session_checks,
    render_pyproject,
    render_smoke_test,
    render_structure,
)
from harness.tools.file_io import atomic_write_text
from harness.tools.shell import validate_path

if TYPE_CHECKING:
    from collections.abc import Callable

    from harness.tools.api_client import HarnessClient

logger = logging.getLogger(__name__)


class TargetKind(Enum):
    """초기화 대상 파일의 종류."""

    ADR = "adr"
    CONVENTION = "convention"
    STRUCTURE = "structure"
    POLICY = "policy"
    CLAUDE = "claude"
    CLAUDE_CONFIG = "claude-config"
    CODERABBIT = "coderabbit"
    PYPROJECT = "pyproject"
    GITIGNORE = "gitignore"
    CI = "ci"
    SMOKE_TEST = "smoke"
    PACKAGE_INIT = "package-init"


ALL_TARGETS: tuple[TargetKind, ...] = (
    TargetKind.ADR,
    TargetKind.CONVENTION,
    TargetKind.STRUCTURE,
    TargetKind.POLICY,
    TargetKind.CLAUDE,
    TargetKind.CLAUDE_CONFIG,
)

# 새 Python 프로젝트 골격 (opt-in: --scaffold 또는 --only로만 생성).
SCAFFOLD_TARGETS: tuple[TargetKind, ...] = (
    TargetKind.PYPROJECT,
    TargetKind.PACKAGE_INIT,
    TargetKind.SMOKE_TEST,
    TargetKind.GITIGNORE,
    TargetKind.CI,
)

OPTIONAL_TARGETS: tuple[TargetKind, ...] = (TargetKind.CODERABBIT, *SCAFFOLD_TARGETS)

SUPPORTED_TARGETS: tuple[TargetKind, ...] = ALL_TARGETS + OPTIONAL_TARGETS

_RELATIVE_PATHS: dict[TargetKind, Path] = {
    TargetKind.ADR: Path("docs/adr/0001-initial-architecture.md"),
    TargetKind.CONVENTION: Path("docs/code-convention.yaml"),
    TargetKind.STRUCTURE: Path("harness_structure.yaml"),
    TargetKind.POLICY: Path(".harness/project-policy.yaml"),
    TargetKind.CLAUDE: Path("CLAUDE.md"),
    TargetKind.CLAUDE_CONFIG: Path(".claude/settings.json"),
    TargetKind.CODERABBIT: Path(".coderabbit.yaml"),
    TargetKind.PYPROJECT: Path("pyproject.toml"),
    TargetKind.GITIGNORE: Path(".gitignore"),
    TargetKind.CI: Path(".github/workflows/ci.yml"),
    TargetKind.SMOKE_TEST: Path("tests/test_smoke.py"),
    # PACKAGE_INIT는 ctx.package_dir에 따라 동적으로 결정된다 (_target_relative_path 참조).
}

_LLM_VALIDATORS: dict[TargetKind, Callable[[str], bool]] = {}

_POLICY_CODERABBIT_FLAG_PATTERN = re.compile(
    r"^(?P<indent>[ \t]*)coderabbit:[ \t]*(?P<value>false|true)[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)


def relative_path_for(kind: TargetKind) -> Path:
    """대상 종류에 대응하는 상대 경로를 반환한다."""
    return _RELATIVE_PATHS[kind]


@dataclass(frozen=True)
class BootstrapPlan:
    """단일 파일에 대한 초기화 계획."""

    kind: TargetKind
    target_path: Path
    content: str
    existed_before: bool
    will_write: bool
    skipped_reason: str = ""
    source: str = "template"  # "template" | "llm"

    @property
    def status(self) -> str:
        if not self.will_write:
            return "skipped"
        return "updated" if self.existed_before else "created"


@dataclass
class BootstrapResult:
    """전체 초기화 결과."""

    project_dir: Path
    plans: list[BootstrapPlan] = field(default_factory=list)
    dry_run: bool = False
    messages: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        prefix = "[DRY-RUN] " if self.dry_run else ""
        for plan in self.plans:
            tag = plan.status.upper()
            extra = f" (source={plan.source})" if plan.will_write else ""
            reason = f" — {plan.skipped_reason}" if plan.skipped_reason else ""
            lines.append(f"{prefix}{tag:<8} {plan.target_path}{extra}{reason}")
        return lines

    @property
    def created_count(self) -> int:
        return sum(1 for p in self.plans if p.status == "created")

    @property
    def updated_count(self) -> int:
        return sum(1 for p in self.plans if p.status == "updated")

    @property
    def skipped_count(self) -> int:
        return sum(1 for p in self.plans if p.status == "skipped")


@dataclass(frozen=True)
class MigrationOptions:
    """기존 프로젝트 마이그레이션 옵션."""

    package: str | None = None


@dataclass(frozen=True)
class PackageLocation:
    """패키지 디렉터리 위치. source_root가 비면 flat, 'src'면 src 레이아웃."""

    package: str
    source_root: str = ""

    @property
    def display(self) -> str:
        root = self.source_root.strip().strip("/")
        return f"{root}/{self.package}" if root else self.package


_NAME_FALLBACK = "my-project"
_MIGRATION_TARGETS: tuple[TargetKind, ...] = (
    TargetKind.ADR,
    TargetKind.CONVENTION,
    TargetKind.STRUCTURE,
    TargetKind.POLICY,
)
_MIGRATION_REQUIRED_DIRS: tuple[Path, ...] = (
    Path("docs"),
    Path("docs/adr"),
    Path(".harness"),
    Path("tests"),
    Path("scripts"),
)
_PACKAGE_EXCLUDE_DIRS: frozenset[str] = frozenset({
    ".claude",
    ".git",
    ".harness",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "docs",
    "scripts",
    "src",
    "tests",
})


def derive_project_name(prompt: str, project_dir: Path) -> str:
    """자연어 프롬프트와 디렉터리명에서 프로젝트 이름을 추정한다."""
    quoted = re.search(r"[\"'`]([\w\-]{2,40})[\"'`]", prompt)
    if quoted:
        return quoted.group(1)
    if project_dir and project_dir.name and project_dir.name not in {".", ""}:
        cleaned = re.sub(r"[^\w\-]", "-", project_dir.name).strip("-")
        if cleaned:
            return cleaned
    return _NAME_FALLBACK


def derive_package_name(project_name: str) -> str:
    """프로젝트 이름에서 Python 패키지 디렉터리명을 추정한다."""
    normalized = re.sub(r"\W+", "_", project_name.strip().lower()).strip("_")
    if not normalized:
        return "harness"
    if normalized[0].isdigit():
        normalized = f"pkg_{normalized}"
    return normalized


def _summarize_intent(prompt: str) -> str:
    """프롬프트를 ADR/CLAUDE.md에 사용할 짧은 요약으로 정리한다."""
    text = prompt.strip()
    if not text:
        return "프로젝트 목적이 아직 정의되지 않았습니다."
    if len(text) > 280:
        return text[:277] + "..."
    return text


_DEFAULT_LLM_SYSTEM = (
    "당신은 Python Harness 프레임워크의 초기 환경 구성 도우미입니다. "
    "사용자가 제공한 프로젝트 목적을 바탕으로 ADR, 코드 컨벤션, 구조 규칙, "
    "프로젝트 정책 파일을 한국어로 작성합니다. 응답에는 코드 펜스 없이 파일 본문만 포함합니다."
)


def _strip_code_fence(text: str) -> str:
    """LLM 응답이 코드 펜스(```)로 감싸져 있으면 제거한다."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2:
        return stripped
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body).strip()


def _validate_yaml(text: str) -> bool:
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    return isinstance(loaded, dict)


def _validate_convention_yaml(text: str) -> bool:
    """conventions 리스트가 존재하는지 검증한다."""
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    if not isinstance(loaded, dict):
        return False
    conventions = loaded.get("conventions")
    return isinstance(conventions, list) and len(conventions) > 0


def _validate_structure_yaml(text: str) -> bool:
    """rules 리스트가 존재하는지 검증한다."""
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    if not isinstance(loaded, dict):
        return False
    rules = loaded.get("rules")
    return isinstance(rules, list) and len(rules) > 0


def _validate_policy_yaml(text: str) -> bool:
    """project와 policies 딕셔너리가 존재하는지 검증한다."""
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    if not isinstance(loaded, dict):
        return False
    project = loaded.get("project")
    if not isinstance(project, dict):
        return False
    package = project.get("package")
    if not isinstance(package, str) or not package.strip():
        return False
    return isinstance(loaded.get("policies"), dict)


def _validate_markdown(text: str) -> bool:
    """마크다운 응답을 검증한다.

    YAML frontmatter(``--- ... ---``)로 시작하는 ADR도 허용해야 하므로,
    "첫 줄이 ``#``로 시작" 대신 "본문 어딘가에 ``#`` 헤딩이 한 줄 이상 존재"를
    검사한다. 빈 응답은 거부한다.
    """
    if not text.strip():
        return False
    return any(line.lstrip().startswith("#") for line in text.splitlines())


_LLM_VALIDATORS.update({
    TargetKind.ADR: _validate_markdown,
    TargetKind.CONVENTION: _validate_convention_yaml,
    TargetKind.STRUCTURE: _validate_structure_yaml,
    TargetKind.POLICY: _validate_policy_yaml,
    TargetKind.CLAUDE: lambda t: bool(t.strip()),
    TargetKind.CODERABBIT: _validate_yaml,
})


# LLM 커스터마이즈를 건너뛰고 항상 템플릿을 사용할 대상 목록.
# `.claude/settings.json`은 구조가 엄격하고 보안에 직결되므로 LLM에 위임하지 않는다.
# 이 목록에 든 대상은 _LLM_VALIDATORS / _LLM_INSTRUCTIONS 에 등록할 필요가 없다.
_LLM_SKIP_KINDS: frozenset[TargetKind] = frozenset(
    {TargetKind.CLAUDE_CONFIG, *SCAFFOLD_TARGETS}
)


_LLM_INSTRUCTIONS: dict[TargetKind, str] = {
    TargetKind.ADR: (
        "다음은 새 프로젝트의 첫 번째 ADR 초안 템플릿입니다. 사용자의 의도에 맞게 Context, "
        "Decision, Consequences 섹션을 보강하세요. 마크다운 머리말(--- ... ---)과 # 제목 형식을 유지합니다."
    ),
    TargetKind.CONVENTION: (
        "다음은 코드 컨벤션 YAML 초안입니다. 사용자가 명시한 언어/도구/도메인에 맞게 conventions 항목을 "
        "보강하거나 다듬으세요. 최상위 키는 반드시 'conventions' 리스트여야 합니다."
    ),
    TargetKind.STRUCTURE: (
        "다음은 구조 규칙 YAML 초안입니다. 'rules' 리스트를 사용자의 프로젝트 구조에 맞게 다듬으세요. "
        "각 규칙은 name, type, description 키를 가지고, type은 required_files / forbidden_pattern / "
        "dependency_direction 중 하나여야 합니다."
    ),
    TargetKind.POLICY: (
        "다음은 .harness/project-policy.yaml 초안입니다. 사용자의 의도에 맞춰 project.name, "
        "project.package, language, policies.required_checks, policies.custom_rules 등을 보강하세요. "
        "최상위 키는 'project'와 'policies'입니다. project.package는 메인 Python 패키지 디렉터리명입니다."
    ),
    TargetKind.CLAUDE: (
        "다음은 CLAUDE.md 초안입니다. 사용자의 의도와 운영 원칙, 품질 기준, 자주 쓰는 명령을 한국어로 정리해 보강하세요."
    ),
    TargetKind.CODERABBIT: (
        "다음은 .coderabbit.yaml 초안입니다. Python 프로젝트와 GitHub PR 리뷰 자동화에 맞게 다듬으세요. "
        "최상위 YAML 매핑이어야 하며, GitHub App 설치가 별도로 필요하다는 주석은 유지하세요."
    ),
}


class BootstrapInitializer:
    """프로젝트 초기 환경 구성을 수행한다."""

    def __init__(
        self,
        project_dir: Path,
        *,
        prompt: str = "",
        client: HarnessClient | None = None,
        model: str = "claude-sonnet-4-6",
        force: bool = False,
        offline: bool = False,
        dry_run: bool = False,
        targets: list[TargetKind] | None = None,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.prompt = prompt
        self.client = client
        self.model = model
        self.force = force
        self.offline = offline
        self.dry_run = dry_run
        self.targets = list(targets) if targets else list(ALL_TARGETS)

    def run(self) -> BootstrapResult:
        """초기화를 실행한다. dry_run인 경우 파일을 쓰지 않는다."""
        result = BootstrapResult(project_dir=self.project_dir, dry_run=self.dry_run)

        ctx = self._build_template_context(
            package=self._read_policy_package(),
            source_root=self._read_policy_source_root(),
        )
        self._apply_plans(result, ctx, self.targets)

        return result

    def migrate_existing(self, options: MigrationOptions | None = None) -> BootstrapResult:
        """기존 Python 프로젝트를 하네스 강제 구조에 맞게 보강한다."""
        migrate_options = options or MigrationOptions()
        policy_package = self._read_policy_package()
        policy_source_root = self._read_policy_source_root()
        candidates = self._detect_package_candidates()
        location = self._resolve_migration_package(
            candidates,
            migrate_options.package or policy_package,
            policy_source_root,
        )

        result = BootstrapResult(project_dir=self.project_dir, dry_run=self.dry_run)
        result.messages.append(f"[MIGRATE] 패키지 자동 채택: {location.display}")

        if not self.dry_run:
            self._ensure_migration_dirs()

        path_overrides = self._migration_path_overrides()
        adr_path = path_overrides.get(TargetKind.ADR, _RELATIVE_PATHS[TargetKind.ADR])
        ctx = self._build_template_context(
            package=location.package,
            source_root=location.source_root,
            adr_path=str(adr_path),
        )
        content_overrides = self._migration_content_overrides(location, ctx)
        self._apply_plans(
            result,
            ctx,
            [kind for kind in self.targets if kind in _MIGRATION_TARGETS],
            structure_renderer=render_migration_structure,
            path_overrides=path_overrides,
            content_overrides=content_overrides,
        )

        if not (self.project_dir / ".claude/skills").exists():
            result.messages.append(
                "[MIGRATE] Claude Code를 쓰면 .claude/skills 복사를 고려하세요."
            )
        return result

    def _apply_plans(
        self,
        result: BootstrapResult,
        ctx: TemplateContext,
        targets: list[TargetKind],
        *,
        structure_renderer: Callable[[TemplateContext], str] = render_structure,
        path_overrides: dict[TargetKind, Path] | None = None,
        content_overrides: dict[TargetKind, str] | None = None,
    ) -> None:
        """대상 목록에 대한 파일 쓰기 계획을 만들고 필요 시 실행한다."""
        paths = path_overrides or {}
        overrides = content_overrides or {}
        renderers: dict[TargetKind, Callable[[TemplateContext], str]] = {
            TargetKind.ADR: render_adr,
            TargetKind.CONVENTION: render_convention,
            TargetKind.STRUCTURE: structure_renderer,
            TargetKind.POLICY: render_policy,
            TargetKind.CLAUDE: render_claude_md,
            TargetKind.CLAUDE_CONFIG: render_claude_settings,
            TargetKind.CODERABBIT: render_coderabbit_config,
            TargetKind.PYPROJECT: render_pyproject,
            TargetKind.GITIGNORE: render_gitignore,
            TargetKind.CI: render_ci,
            TargetKind.SMOKE_TEST: render_smoke_test,
            TargetKind.PACKAGE_INIT: render_package_init,
        }
        coderabbit_selected = TargetKind.CODERABBIT in targets

        for kind in targets:
            relative = paths.get(kind) or self._target_relative_path(kind, ctx)
            is_safe, reason = validate_path(str(relative), self.project_dir)
            if not is_safe:
                raise ValueError(f"부트스트랩 대상 경로 거부: {reason}")
            target_path = self.project_dir / relative
            existed = target_path.exists()
            if existed and not self.force and kind not in overrides:
                if kind is TargetKind.CLAUDE_CONFIG:
                    self._append_missing_claude_hook_plan(result, ctx)
                plan = BootstrapPlan(
                    kind=kind,
                    target_path=target_path,
                    content="",
                    existed_before=True,
                    will_write=False,
                    skipped_reason="이미 존재함 (--force로 덮어쓰기 가능)",
                )
                result.plans.append(plan)
                continue

            if kind in overrides:
                content = overrides[kind]
                source = "template"
            else:
                template_text = renderers[kind](ctx)
                if kind is TargetKind.POLICY and coderabbit_selected:
                    template_text, _ = self._apply_coderabbit_flag(template_text)
                content, source = self._maybe_customize_with_llm(kind, template_text, ctx)

            main_plan = BootstrapPlan(
                kind=kind,
                target_path=target_path,
                content=content,
                existed_before=existed,
                will_write=True,
                source=source,
            )

            if kind is TargetKind.CLAUDE_CONFIG:
                # sidecar hook 도 항상 별도 plan으로 기록한다 (요약 가시성 일관화).
                # 쓰기 순서는 hook → settings 순으로 두어, 중간 실패 시 다음 실행이
                # 빈 settings.json을 만나지 않고 fresh 경로로 깔끔히 복구되게 한다.
                hook_path = self._claude_hook_path()
                hook_plan = BootstrapPlan(
                    kind=TargetKind.CLAUDE_CONFIG,
                    target_path=hook_path,
                    content=render_post_session_checks(ctx),
                    existed_before=hook_path.exists(),
                    will_write=True,
                    source="template",
                )
                if not self.dry_run:
                    self._write_claude_hook_sidecar(ctx)
                    self._write_file(target_path, content)
                result.plans.append(main_plan)
                result.plans.append(hook_plan)
            else:
                if not self.dry_run:
                    self._write_file(target_path, content)
                result.plans.append(main_plan)

        if coderabbit_selected:
            self._sync_existing_policy_coderabbit_flag(result)

    @staticmethod
    def _apply_coderabbit_flag(policy_text: str) -> tuple[str, bool]:
        """정책 텍스트의 ``review_tools.coderabbit`` 플래그를 ``true``로 켠다.

        반환값은 ``(새 텍스트, 변경 여부)``. 라인 단위 정규식으로 동작해
        템플릿 주석과 사용자 hand-edit을 모두 보존한다. 매치가 없으면
        원본을 그대로 돌려준다.
        """
        matches = list(_POLICY_CODERABBIT_FLAG_PATTERN.finditer(policy_text))
        if not matches:
            return policy_text, False
        if all(m.group("value").lower() == "true" for m in matches):
            return policy_text, False
        new_text = _POLICY_CODERABBIT_FLAG_PATTERN.sub(
            lambda m: f"{m.group('indent')}coderabbit: true", policy_text
        )
        return new_text, new_text != policy_text

    def _sync_existing_policy_coderabbit_flag(self, result: BootstrapResult) -> None:
        """기존 정책 파일이 있다면 ``coderabbit`` 플래그를 ``true``로 동기화한다.

        이 실행에서 정책 파일이 새로 (재)작성됐다면 렌더 단계에서 이미
        플래그가 반영됐으므로 건너뛴다.
        """
        policy_path = self.project_dir / _RELATIVE_PATHS[TargetKind.POLICY]
        already_written = any(
            p.kind is TargetKind.POLICY and p.will_write for p in result.plans
        )
        if already_written or not policy_path.exists():
            return

        try:
            original = policy_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("정책 파일 읽기 실패, CodeRabbit 플래그 동기화 생략: %s", e)
            return

        patched, changed = self._apply_coderabbit_flag(original)
        if not changed:
            return

        plan = BootstrapPlan(
            kind=TargetKind.POLICY,
            target_path=policy_path,
            content=patched,
            existed_before=True,
            will_write=True,
            source="patch",
        )
        if not self.dry_run:
            self._write_file(policy_path, patched)
        result.plans.append(plan)

    def _append_missing_claude_hook_plan(
        self, result: BootstrapResult, ctx: TemplateContext
    ) -> None:
        """CLAUDE_CONFIG sidecar hook이 누락된 경우 복구 계획을 추가한다."""
        hook_path = self._claude_hook_path()
        if hook_path.exists():
            return

        content = render_post_session_checks(ctx)
        plan = BootstrapPlan(
            kind=TargetKind.CLAUDE_CONFIG,
            target_path=hook_path,
            content=content,
            existed_before=False,
            will_write=True,
            source="template",
        )
        if not self.dry_run:
            self._write_claude_hook_sidecar(ctx)
        result.plans.append(plan)

    def _build_template_context(
        self,
        package: str | None = None,
        adr_path: str | None = None,
        source_root: str = "",
    ) -> TemplateContext:
        project_name = derive_project_name(self.prompt, self.project_dir)
        return TemplateContext(
            project_name=project_name,
            package=package or derive_package_name(project_name),
            source_root=source_root,
            adr_path=adr_path or str(_RELATIVE_PATHS[TargetKind.ADR]),
            intent_summary=_summarize_intent(self.prompt),
        )

    @staticmethod
    def _target_relative_path(kind: TargetKind, ctx: TemplateContext) -> Path:
        """대상 종류의 상대 경로를 반환한다. PACKAGE_INIT는 레이아웃에 따라 동적."""
        if kind is TargetKind.PACKAGE_INIT:
            return Path(ctx.package_dir) / "__init__.py"
        return _RELATIVE_PATHS[kind]

    def _read_policy_package(self) -> str | None:
        policy_path = self.project_dir / _RELATIVE_PATHS[TargetKind.POLICY]
        if not policy_path.exists():
            return None
        try:
            loaded = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return None
        if not isinstance(loaded, dict):
            return None
        direct_package = loaded.get("package")
        if isinstance(direct_package, str) and direct_package.strip():
            return direct_package.strip()
        project = loaded.get("project")
        if not isinstance(project, dict):
            return None
        package = project.get("package")
        if isinstance(package, str) and package.strip():
            return package.strip()
        return None

    def _read_policy_source_root(self) -> str:
        policy_path = self.project_dir / _RELATIVE_PATHS[TargetKind.POLICY]
        if not policy_path.exists():
            return ""
        try:
            loaded = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return ""
        if not isinstance(loaded, dict):
            return ""
        project = loaded.get("project")
        if not isinstance(project, dict):
            return ""
        source_root = project.get("source_root")
        if isinstance(source_root, str):
            return source_root.strip().strip("/")
        return ""

    def _detect_package_candidates(self) -> list[PackageLocation]:
        candidates: set[PackageLocation] = set()
        candidates.update(self._pyproject_package_candidates())

        if self.project_dir.exists():
            for child in self.project_dir.iterdir():
                if not child.is_dir() or child.name in _PACKAGE_EXCLUDE_DIRS:
                    continue
                if (child / "__init__.py").exists():
                    candidates.add(PackageLocation(child.name, ""))

            src_dir = self.project_dir / "src"
            if src_dir.is_dir():
                for child in src_dir.iterdir():
                    if not child.is_dir() or child.name in _PACKAGE_EXCLUDE_DIRS:
                        continue
                    if (child / "__init__.py").exists():
                        candidates.add(PackageLocation(child.name, "src"))

        return sorted(candidates, key=lambda loc: (loc.source_root, loc.package))

    def _pyproject_package_candidates(self) -> set[PackageLocation]:
        pyproject_path = self.project_dir / "pyproject.toml"
        if not pyproject_path.exists():
            return set()
        try:
            loaded = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            return set()
        project = loaded.get("project")
        if not isinstance(project, dict):
            return set()
        name = project.get("name")
        if not isinstance(name, str) or not name.strip():
            return set()
        package = derive_package_name(name)
        locations: set[PackageLocation] = set()
        if (self.project_dir / package / "__init__.py").exists():
            locations.add(PackageLocation(package, ""))
        if (self.project_dir / "src" / package / "__init__.py").exists():
            locations.add(PackageLocation(package, "src"))
        return locations

    def _resolve_migration_package(
        self,
        candidates: list[PackageLocation],
        policy_package: str | None,
        policy_source_root: str = "",
    ) -> PackageLocation:
        if policy_package:
            # 정책이 source_root를 명시하면 자동 탐지보다 우선한다.
            # (루트·src 동시 존재 시 루트로 잘못 채택되는 것을 방지)
            search_roots = (policy_source_root,) if policy_source_root else ("", "src")
            for source_root in search_roots:
                base = self.project_dir / source_root if source_root else self.project_dir
                if (base / policy_package / "__init__.py").exists():
                    return PackageLocation(policy_package, source_root)
            location_hint = (
                f"{policy_source_root}/ 아래"
                if policy_source_root
                else "루트 또는 src/ 아래"
            )
            raise ValueError(
                f"[MIGRATE] 정책 package를 찾을 수 없습니다: {policy_package}\n"
                f"이유: 고정 구조 게이트는 {location_hint}의 <package>/ 디렉터리를 요구합니다.\n"
                f"조치: {location_hint}에 패키지를 두거나 package/source_root를 올바르게 명시하세요."
            )
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            displays = [loc.display for loc in candidates]
            raise ValueError(
                f"[MIGRATE] 패키지 후보가 여러 개입니다: {displays}\n"
                "이유: 자동으로 하나를 고르면 잘못된 패키지를 구조 규칙에 고정할 수 있습니다.\n"
                "조치: .harness/project-policy.yaml에 package: <이름>을 명시한 후 다시 --migrate 하세요."
            )
        raise ValueError(
            "[MIGRATE] 패키지 후보를 찾지 못했습니다.\n"
            "이유: 루트 또는 src/ 아래에서 <package>/__init__.py를 찾지 못했습니다.\n"
            "조치: 루트 또는 src/ 아래에 Python 패키지를 만들거나, 패키지명을 "
            ".harness/project-policy.yaml의 package에 명시한 후 다시 --migrate 하세요."
        )

    def _ensure_migration_dirs(self) -> None:
        for relative_dir in _MIGRATION_REQUIRED_DIRS:
            target_dir = self.project_dir / relative_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            if (
                relative_dir in {Path("tests"), Path("scripts")}
                and not any(target_dir.iterdir())
            ):
                (target_dir / ".gitkeep").write_text("", encoding="utf-8")

    def _migration_path_overrides(self) -> dict[TargetKind, Path]:
        adr_dir = self.project_dir / "docs/adr"
        if not adr_dir.exists():
            return {}
        existing_adr = next(iter(sorted(adr_dir.glob("0001-*.md"))), None)
        if existing_adr is None:
            return {}
        return {TargetKind.ADR: existing_adr.relative_to(self.project_dir)}

    def _migration_content_overrides(
        self, location: PackageLocation, ctx: TemplateContext
    ) -> dict[TargetKind, str]:
        policy_path = self.project_dir / _RELATIVE_PATHS[TargetKind.POLICY]
        if self.force or not policy_path.exists():
            return {}
        content = self._render_existing_policy_with_package(policy_path, location, ctx)
        if content is None:
            return {}
        return {TargetKind.POLICY: content}

    def _render_existing_policy_with_package(
        self, policy_path: Path, location: PackageLocation, ctx: TemplateContext
    ) -> str | None:
        try:
            loaded = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return render_policy(ctx)
        if not isinstance(loaded, dict):
            return render_policy(ctx)

        project = loaded.get("project")
        if not isinstance(project, dict):
            project = {}
            loaded["project"] = project
        existing_source_root = str(project.get("source_root", "")).strip().strip("/")
        if (
            project.get("package") == location.package
            and existing_source_root == location.source_root
            and "package" not in loaded
        ):
            return None

        project["package"] = location.package
        if location.source_root:
            project["source_root"] = location.source_root
        else:
            project.pop("source_root", None)
        loaded.pop("package", None)
        return yaml.dump(
            loaded,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    def _maybe_customize_with_llm(
        self, kind: TargetKind, template_text: str, ctx: TemplateContext
    ) -> tuple[str, str]:
        """LLM이 사용 가능하면 템플릿을 다듬도록 시도한다. 실패 시 템플릿 사용."""
        if kind in _LLM_SKIP_KINDS:
            return template_text, "template"
        if self.offline or self.client is None or not self.prompt.strip():
            return template_text, "template"

        instructions = _LLM_INSTRUCTIONS[kind]
        user_message = (
            f"# 프로젝트 의도\n{ctx.intent_summary}\n\n"
            f"# 프로젝트 이름\n{ctx.project_name}\n\n"
            f"# 작업 지침\n{instructions}\n\n"
            f"# 초안\n```\n{template_text}\n```\n\n"
            "초안을 사용자 의도에 맞게 보강한 최종 본문만 응답하세요. "
            "코드 펜스로 감싸지 말고 본문만 출력합니다."
        )
        try:
            response = self.client.create_message(
                model=self.model,
                system=_DEFAULT_LLM_SYSTEM,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=4096,
                temperature=0.3,
            )
        except Exception as e:
            logger.warning("%s LLM 커스터마이즈 실패: %s — 템플릿 사용", kind.value, e)
            return template_text, "template"

        text_parts: list[str] = []
        for block in response.content:
            block_text = getattr(block, "text", None)
            if isinstance(block_text, str):
                text_parts.append(block_text)
        merged = _strip_code_fence("\n".join(text_parts))
        default_validator: Callable[[str], bool] = lambda _t: True  # noqa: E731
        validator = _LLM_VALIDATORS.get(kind, default_validator)
        if not merged or not validator(merged):
            logger.warning("%s LLM 응답 검증 실패 — 템플릿 사용", kind.value)
            return template_text, "template"
        return merged + ("\n" if not merged.endswith("\n") else ""), "llm"

    def _write_file(self, target_path: Path, content: str) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # atomic_write_text는 임시 파일에 쓰고 os.replace로 교체하므로
        # 대상 파일이 미리 존재할 필요가 없다. touch()를 호출하면
        # 쓰기 도중 실패 시 빈 파일이 잔류해 다음 실행에서 "이미 존재함"으로
        # 잘못 스킵될 수 있어 제거했다.
        atomic_write_text(target_path, content, prefix=".bootstrap-")

    def _claude_hook_path(self) -> Path:
        return self.project_dir / ".claude/hooks/post_session_checks.sh"

    def _write_claude_hook_sidecar(self, ctx: TemplateContext) -> None:
        hook_path = self._claude_hook_path()
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            hook_path,
            render_post_session_checks(ctx),
            prefix=".bootstrap-",
        )
        hook_path.chmod(0o755)
