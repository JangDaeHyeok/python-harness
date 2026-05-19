# harness/context — 세션/Phase/정책 로컬 규칙

## 책임
- `checkpoint.py` — 실행별 체크포인트 (`.harness/checkpoints/{run_id}.json`), `latest.json` 포인터.
- `modify_context.py` — modify 모드용 컨텍스트(브랜치, diff, ADR, 컨벤션, 구조, 정책).
- `project_policy.py` — `.harness/project-policy.yaml` 로더와 기본 정책.
- `phase_manager.py` — 헤드리스 Phase 인덱스/상태 관리.

## 로컬 규칙
- **`context/`는 `agents/`, `sensors/`, `review/`를 import 하지 않는다** (구조 규칙으로 강제). 컨텍스트는 입력 데이터 계층이다.
- 정책 파일이 없거나 파싱 실패해도 **기본 정책으로 폴백**한다. 예외 전파 금지.
- Phase 상태 전이는 `phase_manager.py`를 통해서만 수행한다. JSON 직접 편집 금지.
- 외부 ADR 소스(`adr.external_sources`) 경로가 없거나 디렉터리가 아니면 **조용히 건너뛴다** (오류 없음).
- 체크포인트 `run_id`는 항상 안전한 식별자 형식을 따른다 (UUID/sortable 타임스탬프).

## 헤드리스 Phase 운영 (요약, 상세는 docs/operations.md §3)
- 첫 Phase는 docs-update. 완료 시 `.harness/tasks/sprint-{N}/docs-diff.md` 갱신.
- 각 Phase는 `{phase_id}-handoff.md`(≤20줄)에 다음 Phase용 요약을 남긴다.
- 재시도 시 미완료 Phase만 pending으로 되돌린다. done Phase는 재실행하지 않는다.

## 관련 ADR
- 0006 체크포인트와 재개, 0008 수정 모드와 프로젝트 정책, 0009 Phase 실행과 컨텍스트 격리.
