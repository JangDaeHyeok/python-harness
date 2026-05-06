# Python Harness Framework — Agent Guide

이 문서는 하네스 프레임워크 내에서 동작하는 AI 에이전트(Planner, Generator, Evaluator)가 참조하는 런타임 컨텍스트입니다.

## 기술 스택
- Python 3.11+
- pyyaml, pydantic
- pytest, ruff, mypy (dev)

## 에이전트 역할

| 에이전트 | 역할 | 입력 | 출력 |
|----------|------|------|------|
| **Planner** | 사용자 프롬프트를 제품 스펙과 스프린트 계획으로 변환 | 사용자 프롬프트, (modify 시) 프로젝트 컨텍스트 | ProductSpec |
| **Generator** | 스프린트 계약에 따라 코드 생성·수정 | SprintContract, project_dir | 파일 변경 |
| **Evaluator** | 스프린트 결과가 계약·품질 기준을 만족하는지 평가 | SprintContract, project_dir | EvaluationResult |
| **Phase Worker** | Phase 파일 하나를 독립 세션에서 실행 | phase-*.md, docs-diff, handoff | 파일 변경, output, handoff |
| **Review Handler** | PR 리뷰 코멘트를 분류·반영·응답 | PR review comments | 반영 커밋, review-comments.md, 답글 |

## 에이전트 도구

Generator가 사용할 수 있는 도구:
- `write_file`: 파일 작성
- `read_file`: 파일 읽기
- `run_command`: 셸 명령 실행 (validate_command 통과 필수)
- `git_commit`: Git 커밋
- `list_files`: 파일 목록 조회

Evaluator가 사용할 수 있는 도구:
- `run_command`: 셸 명령 실행
- `read_file`: 파일 읽기
- `check_url`: URL 접근 확인

## 실행 모드별 동작

### create 모드
- Planner가 제품 스펙과 스프린트 계획을 처음부터 작성한다.
- Generator는 빈 디렉터리에 새 프로젝트를 생성한다.
- Evaluator는 기능 완성도와 품질 기준 충족을 평가한다.

### modify 모드
- Planner는 기존 코드베이스 컨텍스트(diff, ADR, 컨벤션, 구조 규칙, 정책)를 받는다. 정책에 외부 ADR 소스가 있으면 함께 로드된다.
- Generator는 기존 파일의 최소 변경에 집중하며, 기존 패턴을 재사용한다.
- Evaluator는 변경 정확성과 기존 기능 보존을 더 강하게 본다.

### headless phase 모드
- 오케스트레이터는 스프린트 계약 후 `.harness/tasks/sprint-<N>/task-index.json`과 `phase-*.md`를 생성한다.
- `phase-01-docs-update`를 먼저 실행하고 `.harness/tasks/sprint-<N>/docs-diff.md`를 갱신한다.
- 기본 정책은 docs-diff가 비어 있으면 실패하는 것이다.
- 문서 변경이 필요 없는 예외 작업은 `--allow-empty-docs-diff`로 명시해야 한다.
- 각 Phase Worker는 입력 파일, docs-diff, 이전 Phase handoff만 보고 자기 완결적으로 작업한다.
- 각 Phase Worker는 완료 후 `.harness/tasks/sprint-<N>/<phase_id>-handoff.md`에 다음 Phase가 알아야 할 내용을 20줄 이내로 기록한다.
- 재시도 시 done 상태의 Phase는 유지하고 running/failed/skipped Phase만 pending으로 되돌린다.

## 아키텍처 규칙 (에이전트 필수 준수)

1. **센서 독립성**: sensors/는 agents/를 임포트하지 않는다 (ADR-0001)
2. **검사 순서**: ruff → mypy → 구조 → pytest → AI 리뷰 (ADR-0002)
3. **ADR 기록**: 아키텍처 결정은 docs/adr/에 기록한다 (ADR-0003)
4. **타입 힌트**: 모든 public 함수에 타입 힌트 필수
5. **셸 안전**: 셸 명령은 harness/tools/shell.py 래퍼 사용
6. **print 금지**: harness/ 내부에서 print() 사용 금지, logging 사용
7. **파싱 안전**: LLM 응답 파싱 실패 시 안전한 기본값으로 폴백
8. **최소 변경**: modify 모드에서 불필요한 리팩터링, 추상화 금지
9. **docs-diff 우선**: headless phase 모드에서는 Phase 1 이후 생성된 docs-diff를 구현 기준으로 삼는다 (ADR-0009)
10. **Phase 계약 준수**: Phase 파일의 변경 허용 범위, 기대 산출물, 검증 방법을 지킨다
11. **리뷰 자동화 안전성**: PR 리뷰 자동화는 ACCEPT로 분류된 코멘트만 자동 반영한다
12. **경로 검증**: 파일 경로 접근은 `validate_path`로 검증한다
13. **초기화 안전성**: `__init__`에서 부수 효과를 만들지 않는다

## 코드 컨벤션 위치
- `docs/code-convention.yaml` — ConventionLoader로 로드
- `harness_structure.yaml` — StructureAnalyzer로 검증

## 프로젝트 구조

```
harness/
├── agents/        # Planner, Generator, Evaluator, Orchestrator
├── sensors/
│   ├── computational/  # 린터, 테스트, 타입체커, 구조분석
│   └── inferential/    # AI 코드 리뷰
├── pipeline/      # ruff → mypy → 구조 → pytest → AI 리뷰 통합 파이프라인
├── review/        # 리뷰 산출물, PR 본문, 반영 로그, docs-diff, 세션 포크
├── guides/        # 시스템 프롬프트, 가이드 레지스트리, 컨텍스트 필터
├── context/       # 세션 상태, 체크포인트, modify 컨텍스트, 프로젝트 정책, Phase 관리
├── contracts/     # SprintContract 모델과 저장소
└── tools/         # API 클라이언트, 파일 I/O, 셸 안전 래퍼, 경로 검증, ADR 로더
```

## 주요 명령어

`pip install -e .` 후 CLI 단축 명령을 사용할 수 있습니다. 모든 옵션은 `--help`로 확인합니다.

```bash
pip install -e ".[dev]"           # 개발 의존성 설치

# === harness (= python scripts/run_harness.py) ===
harness --help                                      # 전체 옵션 확인
harness "프롬프트"                                    # create 모드
harness --mode modify "수정 요청"                     # modify 모드
harness --mode modify --use-headless-phases "수정 요청"
harness --mode modify --use-headless-phases --allow-empty-docs-diff "문서 변경 없는 수정 요청"
harness --mode modify --use-headless-phases --auto-pr --pr-base main "수정 요청"
harness --mode modify --use-headless-phases --auto-pr --pr-base main --pr-auto-merge "수정 요청"
harness --resume
harness --run-id <run_id>

# === create-pr-body (= python scripts/create_pr_body.py) ===
create-pr-body --help
create-pr-body --base main
create-pr-body --base main --output pr-body.md

# === auto-pr-pipeline (= python scripts/auto_pr_pipeline.py) ===
auto-pr-pipeline --help
auto-pr-pipeline --base main
auto-pr-pipeline --base main --auto-merge

# === 스크립트 직접 실행 (CLI 단축 명령 없음) ===
python scripts/run_phases.py --sprint 1
python scripts/run_phases.py --sprint 1 --require-docs-diff
ruff check .
mypy harness
pytest
python scripts/check_structure.py
```

## CLI 엔트리포인트
`pip install -e .` 후 사용 가능한 CLI 커맨드:
- `harness` → `scripts.run_harness:main`
- `auto-pr-pipeline` → `scripts.auto_pr_pipeline:main`
- `create-pr-body` → `scripts.create_pr_body:main`

## 산출물 경로

에이전트 실행 중 생성되는 산출물:

```
.harness/
├── artifacts/
│   ├── spec.json                     # Planner 출력
│   ├── summary.json                  # 실행 요약
│   └── sprint_<N>_contract.md        # 스프린트 계약 원문
├── contracts/
│   └── sprint_<N>.json               # 구조화 계약 (JSON)
├── checkpoints/
│   ├── <run_id>.json                 # 실행별 체크포인트
│   └── latest.json                   # 최근 실행 포인터
├── review-artifacts/<branch>/
│   ├── design-intent.md              # 설계 의도
│   ├── code-quality-guide.md         # 평가 기준
│   ├── pr-body.md                    # PR 본문
│   ├── review-comments.md            # 리뷰 반영 판단 로그
│   └── docs-diff-sprint<N>.md        # 스프린트별 문서 변경 요약
└── tasks/
    └── sprint-<N>/
        ├── task-index.json           # Phase 인덱스와 상태
        ├── phase-*.md                # Phase별 자기 완결 프롬프트
        ├── docs-diff.md              # docs-update 이후 런타임 docs-diff
        ├── phase-*-output.md         # Phase 실행 출력
        └── phase-*-handoff.md        # 다음 Phase용 요약
```

## Phase 파일 규약

Phase 파일에는 다음 항목이 포함되어야 한다:
- 스프린트 계약
- 입력 파일 목록
- docs-diff 참조 경로
- 이전 Phase output/handoff 경로
- 변경 허용 범위
- 기대 산출물
- 검증 방법
- handoff 작성 지시

Phase Worker는 변경 허용 범위 밖의 파일을 수정하지 않는다. 필요한 경우 handoff에 이유를 남기고 다음 오케스트레이션 단계에서 결정하게 한다.

## docs-diff 규약

- docs-diff는 `docs/` 변경을 줄 단위로 요약한다.
- tracked diff, untracked 문서, 삭제된 문서 라인을 모두 포함한다.
- Phase 2 이후 구현은 전체 스펙보다 docs-diff의 변경 라인을 우선 참고한다.
- docs-diff가 비어 있는데 문서 업데이트가 필요한 작업이면 실패로 본다.

## PR 자동화 규약

`scripts/auto_pr_pipeline.py`는 다음 순서로 동작한다:
1. 현재 브랜치를 push한다.
2. PR 본문을 생성하고 PR을 연다.
3. PR 인라인 리뷰 코멘트를 수집한다.
4. 코멘트를 ACCEPT / DEFER / IGNORE로 분류한다.
5. ACCEPT 코멘트만 headless 반영 세션에 전달한다.
6. `review-comments.md`에 판정 로그를 저장한다.
7. 반영 커밋을 push한다.
8. 원본 리뷰 코멘트에 한국어 답글을 남긴다.
9. `--auto-merge`가 있으면 PR을 머지한다.

GitHub review thread resolve는 REST API 제약으로 답글 기반 확인으로 대체한다.

### End-to-End 연결 (`--auto-pr`)

`run_harness.py`에 `--auto-pr`을 붙이면 구현 성공 후 `auto_pr_pipeline.run_pipeline()`을 자동 호출한다.
- 통과한 스프린트가 1개 이상인 경우에만 PR 파이프라인이 실행된다.
- PR 파이프라인 실패는 구현 결과에 영향을 주지 않는다.
- `--pr-base`, `--pr-skip-review`, `--pr-auto-merge`로 PR 동작을 제어한다.

### CodeRabbit 연동 규약
- CodeRabbit은 하네스 내부 에이전트가 아니라 GitHub PR에 코멘트를 남기는 외부 리뷰어다.
- CodeRabbit이 남긴 PR 인라인 리뷰 코멘트는 일반 리뷰 코멘트와 동일하게 수집한다.
- 버그, 실패, 누락, 보안, 잘못된 동작 지적은 ACCEPT로 분류한다.
- optional, nit, looks good, 칭찬성 코멘트는 DEFER로 분류하고 자동 반영하지 않는다.
- ACCEPT 코멘트를 반영한 뒤 원본 코멘트에 한국어 답글을 남긴다.
- thread resolve는 답글 기반 확인으로 대체한다.
- CodeRabbit 자동 검증은 저장소에 CodeRabbit GitHub App이 설치되어 있고, `gh` CLI 인증이 되어 있다는 전제에서 동작한다.

## 품질 기준

에이전트가 생성한 코드는 다음 기준을 모두 통과해야 한다:

- ruff 에러 0개
- mypy 에러 0개 (strict 모드)
- pytest 전체 통과
- harness_structure.yaml 규칙 위반 0개

## 리뷰 정책
- 코드 리뷰, PR 리뷰, 리뷰 코멘트 응답은 한국어로 작성한다.
- PR 자동화 답글도 한국어로 작성한다.
- 자동 반영하지 않은 DEFER/IGNORE 코멘트는 `review-comments.md`에 사유를 남긴다.

## 프로젝트 정책
- `.harness/project-policy.yaml`이 있으면 컨벤션, ADR, 구조 규칙 경로와 프로젝트별 정책을 반영한다.
- 정책이 없으면 기본 경로(docs/code-convention.yaml, docs/adr/, harness_structure.yaml)를 사용한다.
- 정책 파일이 없거나 파싱에 실패하면 기본 정책으로 폴백한다.
- 기본 필수 검사는 ruff, mypy, pytest, structure이다.
- `review_language`는 리뷰/PR 답글 언어 기준이며 기본값은 `ko`다.
- `required_checks`는 Evaluator와 운영자가 확인해야 할 필수 검사 목록이다.
- `conventions.source`, `adr.directory`, `structure.source`는 modify 컨텍스트 수집 기준 경로다.
- `adr.external_sources`는 외부 프로젝트 ADR 디렉터리 절대 경로 목록이다. 경로가 존재하지 않으면 건너뛴다.
- 외부 ADR은 modify 컨텍스트, GuideRegistry, ContextFilter 모두에 반영된다.
- `artifacts`는 design-intent, code-quality-guide, review-comments, pr-body 산출물 생성 정책이다.
- `custom_rules`는 프로젝트별 암묵지/금지사항/검증 규칙을 적는 자유 영역이다.
- 정책 파일에는 비밀값이나 토큰을 넣지 않는다.
- 정책 변경 후에는 `ruff check`, `mypy harness`, `python scripts/check_structure.py`, `pytest`를 실행한다.

## 체크포인트 재개 규약
- `.harness/checkpoints/<run_id>.json`은 실행별 체크포인트다.
- `.harness/checkpoints/latest.json`은 최근 실행 포인터다.
- `--project-dir` 없이 `--resume` 또는 `--run-id`를 사용할 때 현재 디렉터리에 체크포인트가 있으면 현재 디렉터리의 modify 실행으로 재개한다.

## 수정 모드 컨텍스트
- 현재 git 브랜치, staged/unstaged diff, 변경 파일 목록을 수집한다.
- 설계 의도, 코드 컨벤션, ADR, 구조 규칙, 최근 ruff/mypy 요약을 Planner에게 전달한다.
- `.harness/project-policy.yaml`이 있으면 컨벤션·ADR·구조 규칙 경로와 프로젝트 정책을 반영한다.
- 정책의 `adr.external_sources`가 있으면 외부 프로젝트 ADR도 함께 로드하여 Planner 컨텍스트에 포함한다.

## ADR 목록

| ADR | 제목 | 핵심 결정 |
|-----|------|-----------|
| 0001 | 3-에이전트 아키텍처 | Planner→Generator→Evaluator 파이프라인, 계약 협상 |
| 0002 | 연산적 센서 우선 | 결정적 검사(ruff→mypy→구조→pytest) 후 AI 리뷰 |
| 0003 | ADR 기반 아키텍처 규칙 | ADR + harness_structure.yaml 검증 |
| 0004 | 리뷰 산출물 워크플로 | 브랜치별 설계 의도, 기준, PR 본문, 반영 로그 |
| 0005 | 구조화 스프린트 계약 | raw 텍스트 보존 + 구조화 파싱, JSON 저장 |
| 0006 | 체크포인트와 재개 | Phase enum, run_id 기반 세션 복원 |
| 0007 | 가이드 레지스트리 | 시스템 프롬프트/컨텍스트 중앙 관리 |
| 0008 | 수정 모드와 프로젝트 정책 | modify 구현, project-policy.yaml 정책 적용 |
| 0009 | Phase 실행과 컨텍스트 격리 | docs-diff, Phase 분할, 컨텍스트 필터, 헤드리스 실행, PR 자동화 |
