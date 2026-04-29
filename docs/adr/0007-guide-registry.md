---
status: accepted
date: 2026-04-28
enforced_by:
  - required_guide_files
  - guides_dependency_direction
---

# ADR-0007: 얇은 GuideRegistry 도입

## Context

Planner, Generator, Evaluator의 시스템 프롬프트가 각 에이전트 모듈에 직접 고정되어 있다.
기존 동작은 안정적이지만, ADR·코드 컨벤션·평가 기준처럼 문서 기반 가이드를 에이전트에
점진적으로 주입할 공통 진입점이 없다. 반대로 초기부터 복잡한 규칙 엔진을 만들면 테스트와
운영 부담이 커진다.

## Decision

`harness/guides`에 얇은 `GuideRegistry`를 둔다:

1. 기본 시스템 프롬프트는 `harness/guides/prompts.py`에 보관한다.
2. 에이전트의 `get_system_prompt()`는 기존 출력 문자열을 유지하되 registry 조회를 거친다.
3. `GuideRegistry.build_context()`는 ADR, `docs/code-convention.yaml`, 평가 기준 마크다운을
   `GuideContext`로 조립한다.
4. 규칙 평가나 LLM 기반 판단은 registry 책임에 포함하지 않는다.

### 아키텍처 원칙

- `harness/guides/`는 에이전트와 센서에 의존하지 않는다.
- ADR·평가 기준 조립을 위해 `harness/review`의 결정적 로더를 재사용하는 것은 허용한다.
- agents는 guides를 import하는 방향(agents → guides)만 허용한다.

## Consequences

- 기존 에이전트 출력 형식을 깨지 않고 프롬프트 출처를 점진적으로 분리할 수 있다.
- 문서 기반 가이드를 작은 단위로 테스트할 수 있다.
- 향후 에이전트별 가이드 확장은 registry API 뒤에서 진행할 수 있다.
- 복잡한 rule engine은 아직 도입하지 않는다.
