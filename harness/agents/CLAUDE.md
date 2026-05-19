# harness/agents — 3-에이전트 로컬 규칙

## 책임
- `planner.py` — 사용자 프롬프트 + (modify 시) 컨텍스트 → ProductSpec/SprintContract 초안.
- `generator.py` — SprintContract에 따라 파일 변경.
- `evaluator.py` — 스프린트 결과가 계약·품질 기준을 만족하는지 평가.
- `orchestrator.py` — Planner→Generator→Evaluator 사이클과 재시도/체크포인트 연결.
- `base_agent.py` — 공통 베이스 클래스.

## 로컬 규칙
- 에이전트는 **`harness/sensors/`에 의존해도 되지만 반대 방향은 금지**다 (ADR-0001, ADR-0009의 단방향 규칙).
- LLM 호출은 `harness/tools/api_client.py`의 `HarnessClient`를 통하고, 응답 파싱 실패 시 안전 기본값으로 폴백한다 (예외 전파 금지).
- 시스템 프롬프트는 `harness/guides/prompts.py`/`registry.py`에서 가져온다. 에이전트 코드에 인라인 하드코딩 금지.
- 셸 실행은 직접 `subprocess`를 부르지 말고 `harness/tools/shell.py`를 통한다.
- modify 모드에서 Planner는 `harness/context/modify_context.py`가 만든 컨텍스트만 신뢰한다.

## 관련 ADR
- 0001 3-에이전트 아키텍처, 0005 구조화 스프린트 계약, 0006 체크포인트와 재개, 0008 수정 모드와 프로젝트 정책.
