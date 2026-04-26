---
status: accepted
date: 2026-04-26
enforced_by:
  - required_files
  - dependency_direction
---

# ADR-0003: ADR 기반 아키텍처 규칙 강제

## Context

"에이전트에게 보이지 않는 지식은 존재하지 않는 것과 같다."
(OpenAI Codex 팀)

Slack에서 합의한 결정, 시니어 개발자 머릿속의 지식은
에이전트가 접근할 수 없다. 아키텍처 결정이 문서화되지 않으면
에이전트가 반복적으로 동일한 위반을 저지른다.

## Decision

모든 중요한 아키텍처 결정은:
1. `docs/adr/` 디렉터리에 ADR로 기록한다
2. ADR의 `enforced_by` 필드로 자동 검증 규칙과 연결한다
3. `harness_structure.yaml`에 기계적으로 강제 가능한 규칙을 정의한다
4. 구조 분석기가 매 파이프라인 실행 시 규칙을 검증한다

## Consequences

- 암묵적 지식이 명시적 아티팩트로 변환됨
- 에이전트가 아키텍처 규칙을 자동으로 준수
- 새 팀원(인간 또는 AI)이 빠르게 프로젝트 컨텍스트를 파악 가능
- ADR 유지보수 오버헤드가 발생하지만 장기적으로 가치 있음
