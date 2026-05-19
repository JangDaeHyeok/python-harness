# harness/sensors — 센서 로컬 규칙

## 책임
- `computational/` — 결정적(deterministic) 검사: 린터(ruff), 타입체커(mypy), 구조분석, pytest 러너.
- `inferential/` — LLM 기반 AI 코드 리뷰.

## 로컬 규칙 (CRITICAL)
- **센서는 `harness/agents/`를 import 하지 않는다.** 단방향 의존성. `harness_structure.yaml`의 `dependency_direction` 규칙으로 자동 강제됨.
- 새 검사 종류를 추가할 때는 우선 **연산적 센서**로 만든다. AI 호출이 필요한 검사는 `inferential/`에만 둔다 (ADR-0002).
- 외부 도구(ruff, mypy, pytest) 호출은 반드시 `harness/tools/shell.py`의 `run_command_safe`/`validate_command`를 거친다.
- 센서는 결과를 데이터 모델(dataclass/pydantic)로 반환하고, 에이전트 직접 호출은 하지 않는다.
- LLM 응답 파싱 실패 시 안전 기본값 반환 (예외 전파 금지).

## 관련 ADR
- 0002 연산적 센서 우선, 0003 ADR 기반 아키텍처 규칙.
