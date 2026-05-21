# ADR-0012: 결정적 파이프라인 평가 게이트

- **상태**: Accepted
- **날짜**: 2026-05-21
- **관련 ADR**: ADR-0002, ADR-0009, ADR-0010

## 배경

Evaluator는 LLM 기반 판단을 수행하지만, 린트, 타입 체크, 구조 검사, 테스트 결과는 결정적 검증 결과다.
LLM이 이 결과를 잘못 해석하거나 관대하게 뒤집으면 하네스가 품질 게이트로 동작하지 못한다.
특히 headless Phase 실행에서는 validation phase가 검증 명령을 안내하더라도, 최종 스프린트 판정이 동일한 결정적 결과를 기준으로 합산되어야 한다.

## 결정

스프린트 평가 직전에 `HarnessPipeline.run_all()`을 직접 실행한다.
반환된 `PipelineReport`를 `Evaluator.evaluate_sprint()` 입력에 포함하고, Evaluator 시스템 프롬프트에는 LLM이 결정적 결과를 임의로 뒤집을 수 없다고 명시한다.

최종 판정은 다음 규칙을 따른다.

- 결정적 파이프라인이 실패하면 LLM 평가가 pass여도 스프린트는 fail이다.
- 결정적 파이프라인이 pass여도 LLM 평가가 fail이면 스프린트는 fail이다.
- 두 결과가 모두 pass일 때만 스프린트가 pass다.

평가 리포트는 `결정적 결과:`와 `LLM 평가:` 섹션을 분리하여 남긴다.

## 결과

- 긍정적 결과: 품질 게이트의 최종 권한이 결정적 검사에 고정된다.
- 긍정적 결과: 사용자는 실패 원인이 도구 결과인지 LLM 판단인지 분리해서 볼 수 있다.
- 트레이드오프: 평가 직전에 전체 파이프라인을 한 번 더 실행하므로 스프린트 평가 시간이 늘어난다.

## 검증 방법

- 파이프라인 fail + LLM pass이면 최종 fail이어야 한다.
- 파이프라인 pass + LLM fail이면 최종 fail이어야 한다.
- 파이프라인 pass + LLM pass이면 최종 pass이어야 한다.
- `ruff check .`, `mypy harness`, `python3 scripts/check_structure.py`, `pytest`가 모두 통과해야 한다.
