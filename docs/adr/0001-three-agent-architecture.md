---
status: accepted
date: 2026-04-26
enforced_by:
  - dependency_direction
---

# ADR-0001: 3-에이전트 아키텍처 채택

## Context

AI 코딩 에이전트가 단독으로 실행될 때 자기 평가 편향, 컨텍스트 불안, 일관성 상실 등의
고유한 실패 모드를 보인다. Anthropic의 실험에서 단독 실행 대비 하네스 적용 시
핵심 기능 작동률과 완성도가 크게 향상되었다.

## Decision

Anthropic의 GAN 영감 3-에이전트 아키텍처를 채택한다:
- **Planner**: 사용자 프롬프트를 상세 제품 스펙으로 확장
- **Generator**: 스프린트 단위로 기능 구현
- **Evaluator**: 결과물을 독립적으로 평가하고 피드백 제공

에이전트 간 통신은 스프린트 계약(Sprint Contract)을 통해 이루어진다.

## Consequences

- Generator의 자기 평가 편향이 독립된 Evaluator에 의해 교정된다
- 스프린트 단위 실행으로 컨텍스트 불안이 완화된다
- API 비용이 증가하지만 결과물 품질이 크게 향상된다
- 각 에이전트를 독립적으로 테스트하고 개선할 수 있다
