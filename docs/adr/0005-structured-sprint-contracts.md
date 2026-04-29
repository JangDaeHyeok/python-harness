---
status: accepted
date: 2026-04-28
enforced_by:
  - required_files
---

# ADR-0005: 구조화 스프린트 계약 도입

## Context

기존 스프린트 계약은 Evaluator가 반환하는 마크다운 문자열(raw_text)이며,
Orchestrator가 `sprint_N_contract.md`로 저장하고 Generator에 그대로 전달한다.
이 구조에서는:
- 계약에 포함된 기능 목록·검증 기준을 프로그래밍적으로 참조할 수 없고
- 스프린트 간 계약을 비교·집계하기 어렵고
- 추후 자동 검증 파이프라인에서 기준별 통과 여부를 기록할 수 없다.

## Decision

`harness/contracts/` 패키지에 구조화 계약 모델과 저장소를 구현한다:

1. **models.py** — `SprintContract`, `AcceptanceCriterion`, `ContractMetadata`
   - `raw_text`로 기존 문자열 계약을 그대로 보존
   - `features`, `acceptance_criteria` 등 구조화 필드를 점진적으로 사용
   - `from_raw_text()` 로 기존 마크다운에서 최선 노력 추출
   - JSON 직렬화/역직렬화 지원

2. **store.py** — `ContractStore`
   - `.harness/contracts/sprint_{N}.json` 에 저장
   - 스프린트 번호별 조회, 목록 조회 지원

3. **Orchestrator 연결**
   - 기존 `sprint_N_contract.md` 저장은 그대로 유지 (하위 호환)
   - 추가로 `ContractStore.save()`로 구조화 계약도 저장
   - `negotiate_contract()`의 문자열 반환 흐름은 변경하지 않음

### 아키텍처 원칙

- `harness/contracts/`는 순수 데이터 모델·저장소이므로 agents, sensors, review에 의존하지 않는다.
- agents는 contracts를 import하는 방향(agents → contracts)만 허용한다.
- sensors가 contracts에 의존하는 것은 허용하되, contracts가 sensors에 의존하는 것은 금지한다.

## Consequences

- **긍정**: 계약 필드를 프로그래밍적으로 참조·필터링 가능
- **긍정**: 기존 문자열 계약 흐름을 전혀 변경하지 않아 하위 호환 보장
- **긍정**: JSON 직렬화로 외부 도구·대시보드 연동 용이
- **부정**: raw_text 파싱이 최선 노력(best-effort)이므로 구조화 필드가 불완전할 수 있음
- **중립**: `.harness/contracts/` 디렉터리가 `.gitignore` 관리 대상 추가 필요
