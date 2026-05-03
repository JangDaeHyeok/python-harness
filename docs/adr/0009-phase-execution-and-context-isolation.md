# ADR-0009: Phase 기반 실행, docs-diff, 컨텍스트 격리

status: accepted

## 컨텍스트

하네스가 다른 프로젝트에 실전 투입될 때 다음 문제들이 발생한다:

1. **컨텍스트 오염**: 스프린트가 늘어나면 에이전트의 대화 기록이 누적되어 포커스가 흐려진다.
2. **스펙 해석 어긋남**: 스펙 문서가 변경되었을 때 에이전트가 어떤 부분이 바뀌었는지 정확히 파악하지 못한다.
3. **평가 기준 비대화**: ADR/컨벤션 문서가 커지면 전체를 주입할 수 없고, 전체를 주입하면 포커스가 안 된다.
4. **PR 자동화 미비**: 커밋부터 머지까지 수동 단계가 많다.
5. **설계 의도 손실**: 메인 세션의 대화 맥락에서 도출된 설계 의도가 구현 세션에 전달되지 않는다.

## 결정

### 1. Task/Phase 분할 시스템

스프린트를 5개 Phase로 세분화한다:
- `phase-01-docs-update`: 스펙 문서 업데이트 + docs-diff 생성
- `phase-02-core-impl`: 핵심 로직 구현
- `phase-03-integration`: 기존 시스템 통합
- `phase-04-tests`: 테스트 작성
- `phase-05-validation`: 품질 검증 (ruff, mypy, pytest)

각 Phase 파일은 자기 완결적(self-contained)이어서 독립 세션에서 실행 가능하다.
Phase 정의에는 입력 파일, docs-diff 참조 경로, 변경 허용 범위, 기대 산출물, 검증 명령, 핸드오프 요약 경로를 포함한다.
각 Phase는 완료 후 `.harness/tasks/sprint-{N}/{phase_id}-handoff.md`에 다음 Phase가 볼 20줄 이내 요약을 남긴다.

### 2. docs-diff 시스템

모든 작업의 첫 번째 단계를 "문서 업데이트"로 고정한다.
`git diff --unified=0 -- docs/` 출력을 파싱하여 추가/삭제된 줄을 구조화된 형태로 생성한다.
이후 Phase들이 이 diff를 참조하여 정확한 스펙 변경점만 구현한다.
헤드리스 실행에서는 `phase-01-docs-update` 완료 직후 `.harness/tasks/sprint-{N}/docs-diff.md`를 재생성한다.
기본 정책은 docs-update 이후 docs-diff가 비어 있으면 실패시키는 것이다. 단, 운영자가 `--allow-empty-docs-diff`를 지정하면 예외적으로 계속 진행할 수 있다.

### 3. 유사 RAG 컨텍스트 필터링

방대한 ADR/컨벤션 문서에서 현재 작업에 관련된 항목만 추출하는 필터를 도입한다.
키워드·태그 기반 점수 매칭으로 동작하며, 추출 결과를 구현과 리뷰에 동일하게 적용한다.

### 4. 헤드리스 Phase 실행

`claude --print` 모드로 Phase별 독립 세션을 서브프로세스로 실행한다.
메인 세션의 컨텍스트를 보존하면서 구현 컨텍스트는 하위 세션에 격리한다.
오케스트레이터는 기본적으로 기존 Generator 경로를 유지하되, `use_headless_phases=True` 또는 CLI `--use-headless-phases`가 지정되면 Phase 실행기를 구현 경로로 사용한다.

### 5. PR 자동화 파이프라인

Git push → PR 생성 → 리뷰 수집 → 에이전트 반영 → 머지까지 전 과정을 자동화한다.
리뷰 코멘트는 자동 반영 대상(ACCEPT), 보류(DEFER), 무시(IGNORE)로 먼저 분류한다.
ACCEPT 코멘트만 헤드리스 에이전트에 전달하고, 판정 로그를 `review-comments.md`에 저장한다.
반영 커밋이 생성되면 원본 PR 리뷰 코멘트에 한국어 답글을 남긴다.
GitHub REST API만으로 안정적인 review thread resolve가 불가능한 경우가 있으므로, resolve 처리는 답글 기반 확인으로 대체한다.

CodeRabbit은 PR에 리뷰 코멘트를 남기는 외부 리뷰어로 취급한다.
하네스는 CodeRabbit 실행 자체를 제어하지 않고, CodeRabbit이 남긴 PR 인라인 코멘트를 GitHub CLI/API로 수집한다.
버그, 실패, 누락, 보안, 잘못된 동작 지적은 ACCEPT로 자동 반영 대상에 포함하고,
optional/nit/칭찬성 코멘트는 DEFER로 기록만 남긴다.

### 6. 세션 포크 설계 의도 문서화

메인 세션의 대화 컨텍스트를 요약하여 별도 세션에서 설계 의도 문서를 작성한다.
문서만 남기고 세션은 폐기하여 메인 세션의 컨텍스트를 보존한다.

## 이유

- 컨텍스트는 제한된 리소스이므로 불필요한 정보를 최대한 줄여야 한다.
- 에이전트가 스펙을 제멋대로 해석하여 어긋나게 구현하는 것을 방지하려면 정확한 diff가 필요하다.
- 복잡한 RAG 시스템 없이 서브에이전트(필터)만으로도 충분한 관련도 필터링이 가능하다.
- 순차 호출 책임과 상태 추적은 스크립트가 담당하고, 에이전트는 창의적 판단에만 집중해야 한다.

## 영향

### 새 파일
- `harness/review/docs_diff.py` — docs-diff 생성
- `harness/context/phase_manager.py` — Task/Phase 분할 관리
- `harness/guides/context_filter.py` — 유사 RAG 컨텍스트 필터
- `harness/review/session_fork.py` — 세션 포크 설계 의도
- `scripts/run_phases.py` — 헤드리스 Phase 실행기
- `scripts/auto_pr_pipeline.py` — PR 자동화 파이프라인

### 수정 파일
- `harness/agents/orchestrator.py` — Phase 분할, docs-diff, 컨텍스트 필터 통합
- `scripts/run_harness.py` — 헤드리스 Phase 실행 옵션 노출

### 의존성 규칙
- `harness/review/docs_diff.py`는 `harness.agents`에 의존하지 않는다.
- `harness/context/phase_manager.py`는 `harness.agents`, `harness.sensors`, `harness.review`에 의존하지 않는다.
- `harness/guides/context_filter.py`는 `harness.agents`, `harness.sensors`에 의존하지 않는다.
- `harness/review/session_fork.py`는 `harness.agents`에 의존하지 않는다.
