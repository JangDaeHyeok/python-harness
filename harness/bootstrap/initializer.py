"""프로젝트 초기 환경 구성기.

대상 프로젝트 디렉터리에 다음 파일을 생성·관리한다.

- ``docs/adr/0001-initial-architecture.md``
- ``docs/code-convention.yaml``
- ``harness_structure.yaml``
- ``.harness/project-policy.yaml``
- ``CLAUDE.md`` (선택)

LLM 엔드포인트가 설정되어 있고 ``offline=False`` 인 경우, 자연어 요청을 기반으로
각 파일 내용을 LLM이 다듬도록 시도한다. 호출이 실패하거나 응답이 비정상이면
내장 템플릿으로 안전하게 폴백한다 (예외 전파 금지).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from harness.bootstrap.templates import (
    TemplateContext,
    render_adr,
    render_claude_md,
    render_convention,
    render_policy,
    render_structure,
)
from harness.tools.file_io import atomic_write_text

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


ALL_TARGETS: tuple[TargetKind, ...] = (
    TargetKind.ADR,
    TargetKind.CONVENTION,
    TargetKind.STRUCTURE,
    TargetKind.POLICY,
    TargetKind.CLAUDE,
)

_RELATIVE_PATHS: dict[TargetKind, Path] = {
    TargetKind.ADR: Path("docs/adr/0001-initial-architecture.md"),
    TargetKind.CONVENTION: Path("docs/code-convention.yaml"),
    TargetKind.STRUCTURE: Path("harness_structure.yaml"),
    TargetKind.POLICY: Path(".harness/project-policy.yaml"),
    TargetKind.CLAUDE: Path("CLAUDE.md"),
}

_LLM_VALIDATORS: dict[TargetKind, Callable[[str], bool]] = {}


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


_NAME_FALLBACK = "my-project"


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
    return isinstance(loaded.get("project"), dict) and isinstance(
        loaded.get("policies"), dict
    )


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
})


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
        "다음은 .harness/project-policy.yaml 초안입니다. 사용자의 의도에 맞춰 project.name, language, "
        "policies.required_checks, policies.custom_rules 등을 보강하세요. 최상위 키는 'project'와 'policies'입니다."
    ),
    TargetKind.CLAUDE: (
        "다음은 CLAUDE.md 초안입니다. 사용자의 의도와 운영 원칙, 품질 기준, 자주 쓰는 명령을 한국어로 정리해 보강하세요."
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

        ctx = self._build_template_context()
        renderers: dict[TargetKind, Callable[[TemplateContext], str]] = {
            TargetKind.ADR: render_adr,
            TargetKind.CONVENTION: render_convention,
            TargetKind.STRUCTURE: render_structure,
            TargetKind.POLICY: render_policy,
            TargetKind.CLAUDE: render_claude_md,
        }

        for kind in self.targets:
            target_path = self.project_dir / _RELATIVE_PATHS[kind]
            existed = target_path.exists()
            if existed and not self.force:
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

            template_text = renderers[kind](ctx)
            content, source = self._maybe_customize_with_llm(kind, template_text, ctx)

            plan = BootstrapPlan(
                kind=kind,
                target_path=target_path,
                content=content,
                existed_before=existed,
                will_write=True,
                source=source,
            )
            if not self.dry_run:
                self._write_file(target_path, content)
            result.plans.append(plan)

        return result

    def _build_template_context(self) -> TemplateContext:
        return TemplateContext(
            project_name=derive_project_name(self.prompt, self.project_dir),
            intent_summary=_summarize_intent(self.prompt),
        )

    def _maybe_customize_with_llm(
        self, kind: TargetKind, template_text: str, ctx: TemplateContext
    ) -> tuple[str, str]:
        """LLM이 사용 가능하면 템플릿을 다듬도록 시도한다. 실패 시 템플릿 사용."""
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
