# harness/guides — 가이드 레지스트리/컨텍스트 필터 로컬 규칙

## 책임
- `prompts.py` — 시스템 프롬프트 정의.
- `registry.py` — 가이드(ADR, 컨벤션, 구조 규칙) 중앙 레지스트리.
- `context_filter.py` — 유사 RAG 컨텍스트 필터 (작업 범위에 따라 ADR/컨벤션 청크를 선별).

## 로컬 규칙
- **`guides/`는 `agents/`와 `sensors/`를 import 하지 않는다** (구조 규칙으로 강제).
- 시스템 프롬프트는 이 패키지에서만 정의한다. 다른 패키지에서 인라인 작성 금지.
- 외부 ADR을 받을 때는 `harness/tools/adr.py`의 ADRLoader를 통해서 로드한다.
- 컨텍스트 필터는 토큰 한도를 인지하고 잘라낸다 (필터 통과 결과가 길어도 LLM 호출 한도를 넘기지 않도록).

## 관련 ADR
- 0007 가이드 레지스트리, 0009 Phase 실행과 컨텍스트 격리.
