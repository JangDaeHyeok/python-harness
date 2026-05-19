# harness/pipeline — 통합 파이프라인 로컬 규칙

## 책임
- `harness_pipeline.py` — `ruff → mypy → 구조분석 → pytest → AI 리뷰` 순서의 통합 실행기.

## 로컬 규칙
- **검사 순서는 ADR-0002에 따라 결정적(deterministic) 단계가 먼저, AI 추론 단계가 마지막이다.** 순서 변경 시 ADR 갱신 필요.
- 각 단계는 `harness/sensors/`의 해당 센서를 호출하고, 결과를 표준 데이터 모델로 합친다.
- 셸 호출은 모두 `harness/tools/shell.py` 경유.
- 한 단계 실패가 다음 단계를 막을지 여부는 정책(`.harness/project-policy.yaml`)을 따른다. 인라인 하드코딩 금지.

## 관련 ADR
- 0002 연산적 센서 우선.
