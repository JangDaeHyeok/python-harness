# Python Harness Framework

AI 코딩 에이전트를 위한 하네스 엔지니어링 프레임워크.

## 기술 스택
- Python 3.11+
- pyyaml, pydantic
- pytest, ruff, mypy (dev)

## CRITICAL 규칙 (전체 세션 공통)
- 센서(`harness/sensors/`)는 에이전트(`harness/agents/`)에 의존 금지 (단방향).
- 모든 아키텍처 결정은 `docs/adr/`에 기록.
- `harness/` 내부에서 `print()` 사용 금지, `logging` 모듈 사용.
- 셸 명령은 `harness/tools/shell.py`의 `run_command_safe`, `validate_command` 사용.
- 파일 경로 접근은 `harness/tools/shell.py`의 `validate_path`로 프로젝트 디렉터리 봉쇄를 검증.
- LLM 응답 파싱 실패 시 안전한 기본값으로 폴백 (예외 전파 금지).
- 모든 public 함수에 타입 힌트 필수, `__init__`에서 부수 효과 금지.
- 헤드리스 Phase 실행에서는 문서 업데이트 Phase를 먼저 실행하고 docs-diff를 갱신한다.
- 수정 모드(`--mode modify`)는 기존 코드베이스 최소 변경, 기존 패턴 재사용, 프로젝트 정책 준수가 기본 원칙.

## 코드베이스 맵
```
harness/
├── agents/      # 3-에이전트 (Planner/Generator/Evaluator/Orchestrator) — 자세히는 harness/agents/CLAUDE.md
├── sensors/     # 연산적/추론적 센서 — harness/sensors/CLAUDE.md
├── pipeline/    # 통합 파이프라인 — harness/pipeline/CLAUDE.md
├── review/      # 리뷰 산출물·PR 자동화 — harness/review/CLAUDE.md
├── context/     # 체크포인트·modify·정책·Phase — harness/context/CLAUDE.md
├── guides/      # 시스템 프롬프트·RAG 필터 — harness/guides/CLAUDE.md
├── contracts/   # 스프린트 계약 모델/저장소 — harness/contracts/CLAUDE.md
├── bootstrap/   # harness-init 부트스트랩 — harness/bootstrap/CLAUDE.md
└── tools/       # 셸·경로·파일·API·ADR 유틸 — harness/tools/CLAUDE.md
```

## 문서 맵
- `docs/adr/` — Architecture Decision Records (0001~0014). 신규 작성 시 `.claude/skills/adr-author/SKILL.md` 참조.
- `docs/code-convention.yaml` — 코드 컨벤션 (ConventionLoader).
- `harness_structure.yaml` — 자동 검증되는 아키텍처 규칙.
- `docs/operations.md` — CLI 사용법·운영 가이드 (명령어/플래그 전반).
- `.harness/review-artifacts/{branch}/` — 브랜치별 리뷰 산출물.
- `.harness/project-policy.yaml` — modify 모드 프로젝트 정책 (선택).

## 품질 기준
- ruff 에러 0개, mypy 에러 0개 (strict), pytest 전체 통과, 구조 규칙 위반 0개.
- 검증 명령: `ruff check . && mypy harness && python3 scripts/check_structure.py && pytest`

## 리뷰/응답 언어 정책
- 코드 리뷰, PR 리뷰, 리뷰 코멘트 응답, ADR 본문은 한국어로 작성한다.
- 상세 PR 자동화 정책·CodeRabbit 처리 규칙은 `harness/review/CLAUDE.md` 참조.

## 자주 쓰는 명령 (요약)
- 초보자용 별칭: `harness doctor` / `harness init "설명"` / `harness fix "수정 요청"` / `harness ship "수정 요청"` / `harness pr` / `harness review` — 각각 `harness-doctor`·`harness-init`·`harness --mode modify`·PR 자동화(modify→PR→리뷰 반영)·`auto-pr-pipeline`·`auto-pr-pipeline --current-pr`로 위임. `harness fix --headless`는 헤드리스 Phase + docs-diff 완화. `harness ship`은 수정→PR→리뷰 반영까지 자동화하되, 머지/리뷰 답글은 정책상 사용자 확인(`--pr-confirm-github-writes`)을 별도로 요구한다.
- `harness "프롬프트"` — create 모드
- `harness --mode modify "수정 요청"` — modify 모드
- `harness --mode modify --use-headless-phases --auto-pr --pr-base main "수정 요청"` — End-to-End
- `auto-pr-pipeline --base main` / `create-pr-body --base main` / `harness-init --offline "프로젝트"`
- 전체 옵션·플래그 의미는 `docs/operations.md` 참조.

## CLI 엔트리포인트
- `harness` → `scripts.run_harness:main`
- `auto-pr-pipeline` → `scripts.auto_pr_pipeline:main`
- `create-pr-body` → `scripts.create_pr_body:main`
- `harness-init` → `scripts.init_harness:main`
- `harness-doctor` → `scripts.doctor:main`

## ADR 목록
0001 3-에이전트 / 0002 연산적 센서 우선 / 0003 ADR 기반 아키텍처 규칙 / 0004 리뷰 산출물 워크플로 / 0005 구조화 스프린트 계약 / 0006 체크포인트와 재개 / 0007 가이드 레지스트리 / 0008 수정 모드와 프로젝트 정책 / 0009 Phase 실행과 컨텍스트 격리 / 0010 외부 프로젝트 고정 구조 강제 / 0011 harness-init 마이그레이션 모드 / 0012 결정적 파이프라인 평가 게이트 / 0013 argv 명령 경계와 Phase 완료 게이트 / 0014 src 레이아웃과 project.source_root. 상세 내용은 `docs/adr/`.
