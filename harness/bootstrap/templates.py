"""프로젝트 초기화에 사용할 기본 템플릿 모음.

LLM 호출이 불가하거나 실패했을 때 폴백으로 사용된다.
모든 템플릿은 단순 문자열 포맷팅(``str.format``)으로 ``project_name`` /
``intent_summary`` 만을 치환한다. 추가 변수는 ``str.format_map``으로 다룬다.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field


def _today_iso() -> str:
    """ADR 등에 기록될 오늘 날짜(ISO-8601)를 반환한다."""
    return _dt.date.today().isoformat()


@dataclass(frozen=True)
class TemplateContext:
    """템플릿 치환 컨텍스트."""

    project_name: str
    intent_summary: str
    language: str = "python"
    python_version: str = "3.11+"
    today: str = field(default_factory=_today_iso)

    def as_mapping(self) -> dict[str, str]:
        return {
            "project_name": self.project_name or "my-project",
            "intent_summary": self.intent_summary or "프로젝트 목적이 아직 정의되지 않았습니다.",
            "language": self.language,
            "python_version": self.python_version,
            "today": self.today or _today_iso(),
        }


_ADR_TEMPLATE = """\
---
status: accepted
date: {today}
---

# ADR-0001: {project_name} 프로젝트 초기 아키텍처 결정

## Context

{intent_summary}

본 프로젝트는 Python Harness 프레임워크의 규칙(ADR, code-convention, 구조 규칙)에
맞춰 운영되며, 변경 이력은 `docs/adr/` 하위에 ADR 단위로 기록한다.

## Decision

- 초기 아키텍처 결정은 본 ADR을 기준으로 시작한다.
- 추가 결정은 `docs/adr/000N-<주제>.md` 형태로 누적한다.
- `harness_structure.yaml`에 정의된 구조 규칙을 통해 ADR을 기계적으로 강제한다.

## Consequences

- 모든 아키텍처 변경은 ADR로 문서화되어야 한다.
- 변경 영향 범위는 PR 본문과 리뷰 산출물에서 추적된다.
- 신규 ADR을 추가할 때는 `harness_structure.yaml`의 `required_files` 또는
  `dependency_direction` 규칙을 함께 갱신할지 검토한다.
"""

_CONVENTION_TEMPLATE = """\
# {project_name} 코드 컨벤션
# 자동 생성된 기본 컨벤션이며 프로젝트 상황에 맞게 자유롭게 조정한다.

conventions:
  - id: type-hints-required
    description: "모든 public 함수·메서드에 타입 힌트를 추가한다."
    category: type-safety
    severity: error
    tags: [typing, public-api]

  - id: tests-required-for-public-api
    description: "외부 노출되는 모듈/함수는 단위 테스트를 동반한다."
    category: testing
    severity: warning
    tags: [testing, public-api]

  - id: no-print-debug
    description: "print() 디버깅 대신 logging 모듈을 사용한다."
    category: logging
    severity: warning
    tags: [logging]

  - id: secrets-not-in-repo
    description: "API 키, 토큰, 비밀번호 등 비밀값은 저장소에 커밋하지 않는다."
    category: security
    severity: error
    tags: [security, secrets]
"""

_STRUCTURE_TEMPLATE = """\
# {project_name} 구조 규칙
# harness 구조 분석기(scripts/check_structure.py)가 강제하는 규칙을 정의한다.

rules:
  - name: required_files
    type: required_files
    files:
      - CLAUDE.md
      - harness_structure.yaml
      - docs/adr/0001-initial-architecture.md
      - docs/code-convention.yaml
    description: "프로젝트 필수 파일이 존재해야 한다"

  - name: no_print_debug
    type: forbidden_pattern
    pattern: '^\\s*print\\('
    # directories를 생략하면 프로젝트 루트(".")부터 검사한다.
    # 검사 범위를 좁히려면 ["src", "app"] 처럼 명시적으로 지정한다.
    message: "print() 대신 logging을 사용하세요"
    severity: warning
"""

_POLICY_TEMPLATE = """\
project:
  name: {project_name}
  language: {language}
  python_version: '{python_version}'
policies:
  review_language: ko
  required_checks:
    - ruff
    - mypy
    - pytest
    - structure
  conventions:
    source: docs/code-convention.yaml
  adr:
    directory: docs/adr/
    external_sources: []
  structure:
    source: harness_structure.yaml
  artifacts:
    design_intent: true
    code_quality_guide: true
    review_comments: true
    pr_body: true
"""

_CLAUDE_TEMPLATE = """\
# {project_name}

{intent_summary}

## 운영 원칙
- 모든 아키텍처 결정은 `docs/adr/`에 ADR로 기록한다.
- 코드 컨벤션은 `docs/code-convention.yaml`을 따른다.
- 구조 규칙은 `harness_structure.yaml`에서 정의·강제한다.
- 프로젝트 정책은 `.harness/project-policy.yaml`에서 오버라이드한다.

## 품질 기준
- ruff 에러 0개
- mypy 에러 0개
- pytest 전체 통과
- 구조 규칙 위반 0개

## 운영 명령
```bash
ruff check .
mypy .
pytest
python scripts/check_structure.py  # harness 저장소 기준
```
"""


def render_adr(ctx: TemplateContext) -> str:
    """기본 ADR 마크다운을 렌더링한다."""
    return _ADR_TEMPLATE.format_map(ctx.as_mapping())


def render_convention(ctx: TemplateContext) -> str:
    """기본 코드 컨벤션 YAML을 렌더링한다."""
    return _CONVENTION_TEMPLATE.format_map(ctx.as_mapping())


def render_structure(ctx: TemplateContext) -> str:
    """기본 구조 규칙 YAML을 렌더링한다."""
    return _STRUCTURE_TEMPLATE.format_map(ctx.as_mapping())


def render_policy(ctx: TemplateContext) -> str:
    """기본 프로젝트 정책 YAML을 렌더링한다."""
    return _POLICY_TEMPLATE.format_map(ctx.as_mapping())


def render_claude_md(ctx: TemplateContext) -> str:
    """기본 CLAUDE.md를 렌더링한다."""
    return _CLAUDE_TEMPLATE.format_map(ctx.as_mapping())
