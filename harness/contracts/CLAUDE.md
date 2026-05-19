# harness/contracts — 스프린트 계약 로컬 규칙

## 책임
- `models.py` — `SprintContract` Pydantic 모델.
- `store.py` — `.harness/contracts/sprint_{N}.json` 저장/로드.

## 로컬 규칙
- **`contracts/`는 leaf 모듈이다.** `agents/`, `sensors/`, `review/`를 import 하지 않는다 (구조 규칙으로 강제).
- 계약 JSON은 항상 `atomic_write_text`로 원자적 저장 (`harness/tools/file_io.py`).
- 계약 모델 변경 시 ADR-0005를 갱신한다.
- raw 텍스트는 보존하고 구조화 필드와 함께 저장한다 (LLM 응답 재현 가능성을 위해).

## 관련 ADR
- 0005 구조화 스프린트 계약.
