# Python Harness Framework

AI 코딩 에이전트를 위한 하네스 엔지니어링 프레임워크.

## 기술 스택
- Python 3.11+
- pyyaml, pydantic
- pytest, ruff, mypy (dev)

## 아키텍처 규칙
- CRITICAL: 센서(sensors/)는 에이전트(agents/)에 의존 금지 (단방향)
- CRITICAL: 모든 아키텍처 결정은 docs/adr/에 기록
- CRITICAL: harness/ 내부에서 print() 사용 금지, logging 모듈 사용
- CRITICAL: 헤드리스 Phase 실행에서는 문서 업데이트 Phase를 먼저 실행하고 docs-diff를 갱신한다
- 모든 public 함수에 타입 힌트 필수
- 셸 명령은 반드시 harness/tools/shell.py의 run_command_safe, validate_command 사용
- 파일 경로 접근은 validate_path로 검증
- LLM 응답 파싱 실패 시 안전한 기본값으로 폴백 (예외 전파 금지)
- __init__에서 부수 효과 금지
- 수정 모드(`--mode modify`)는 기존 코드베이스 최소 변경, 기존 패턴 재사용, 프로젝트 정책 준수를 기본 원칙으로 한다
- PR 자동화는 리뷰 코멘트를 분류한 뒤 ACCEPT 항목만 반영한다

## 프로젝트 구조
```
harness/
├── agents/        # 3-에이전트: Planner, Generator, Evaluator, Orchestrator
├── sensors/
│   ├── computational/  # 린터, 테스트, 타입체커, 구조분석
│   └── inferential/    # AI 코드 리뷰
├── pipeline/      # 통합 파이프라인 (ruff→mypy→구조→pytest→AI리뷰)
├── review/        # 리뷰 워크플로: 산출물, 컨벤션, 기준, 설계의도, PR본문, 반영로그, worktree, docs-diff, 세션포크
├── guides/        # 시스템 프롬프트, 가이드 레지스트리, 유사 RAG 컨텍스트 필터 (ADR/컨벤션 컨텍스트 조립)
├── context/       # 세션 상태, 체크포인트, modify 컨텍스트, 프로젝트 정책, Phase 관리
├── contracts/     # 스프린트 계약 모델(SprintContract)과 저장소(ContractStore)
└── tools/         # API 클라이언트, 파일 I/O, 셸 안전 래퍼, 경로 검증, 타입 변환, ADR 로더
```

## 문서 맵
- `docs/adr/` — Architecture Decision Records (0001~0009)
- `docs/code-convention.yaml` — 코드 컨벤션 규칙 (ConventionLoader로 로드)
- `harness_structure.yaml` — 자동 검증되는 아키텍처 규칙 (12개 규칙)
- `.harness/review-artifacts/{branch}/` — 브랜치별 리뷰 산출물
- `.harness/project-policy.yaml` — modify 모드 프로젝트 정책(선택)

## 명령어
```bash
pip install -e ".[dev]"           # 개발 의존성 설치
python scripts/run_harness.py "프롬프트"  # create 모드: 새 프로젝트 생성
python scripts/run_harness.py --mode modify "수정 요청"  # modify 모드: 현재 코드베이스 수정
python scripts/run_harness.py --mode modify --use-headless-phases "수정 요청"  # Phase별 claude --print 실행
python scripts/run_harness.py --mode modify --use-headless-phases --allow-empty-docs-diff "문서 변경 없는 수정 요청"
python scripts/run_harness.py --mode modify --use-headless-phases --auto-pr --pr-base main "수정 요청"  # 구현→PR→리뷰 반영 End-to-End
python scripts/run_harness.py --mode modify --use-headless-phases --auto-pr --pr-base main --pr-auto-merge "수정 요청"  # 머지까지 한 번에
python scripts/run_harness.py --resume  # 현재 디렉터리 체크포인트가 있으면 modify 실행 재개
python scripts/run_harness.py --run-id <run_id>  # 특정 체크포인트에서 재개
python scripts/create_pr_body.py --base main  # PR 본문 생성
python scripts/create_pr_body.py --base main --output pr-body.md
python scripts/run_phases.py --sprint 1  # Phase별 헤드리스 실행
python scripts/run_phases.py --sprint 1 --require-docs-diff  # docs-update 이후 docs-diff 필수
python scripts/auto_pr_pipeline.py --base main  # PR 자동화 파이프라인
python scripts/auto_pr_pipeline.py --base main --auto-merge  # 리뷰 반영 후 자동 머지
ruff check .                      # 린트
mypy harness                      # 타입 체크
pytest                            # 테스트
python scripts/check_structure.py # 구조 분석
```

## CLI 엔트리포인트
pyproject.toml에 등록된 CLI 커맨드:
- `harness` → `scripts.run_harness:main`
- `auto-pr-pipeline` → `scripts.auto_pr_pipeline:main`
- `create-pr-body` → `scripts.create_pr_body:main`

## 리뷰 산출물 경로
- `.harness/review-artifacts/{branch}/design-intent.md` — 설계 의도
- `.harness/review-artifacts/{branch}/code-quality-guide.md` — 평가 기준
- `.harness/review-artifacts/{branch}/pr-body.md` — PR 본문
- `.harness/review-artifacts/{branch}/review-comments.md` — 리뷰 반영 판단 로그
- `.harness/review-artifacts/{branch}/docs-diff-sprint{N}.md` — docs-diff (스펙 변경 추적)

## 리뷰 정책
- 코드 리뷰, PR 리뷰, 리뷰 코멘트 응답은 한국어로 작성한다.
- PR 자동화 파이프라인은 리뷰 코멘트를 ACCEPT/DEFER/IGNORE로 분류하고 ACCEPT만 반영한다.
- 리뷰 반영 후 원본 리뷰 코멘트에 한국어 답글을 남긴다.
- GitHub review thread resolve는 API 제약 때문에 답글 기반 확인으로 대체한다.

## 계약 저장 경로
- `.harness/contracts/sprint_{N}.json` — 스프린트별 구조화 계약 (JSON)

## Task/Phase 경로
- `.harness/tasks/sprint-{N}/task-index.json` — 스프린트별 Phase 인덱스
- `.harness/tasks/sprint-{N}/phase-{NN}-{name}.md` — Phase별 자기 완결적 프롬프트
- `.harness/tasks/sprint-{N}/docs-diff.md` — `phase-01-docs-update` 완료 후 갱신되는 런타임 docs-diff
- `.harness/tasks/sprint-{N}/phase-{NN}-{name}-handoff.md` — 각 Phase가 다음 Phase에 남기는 20줄 이내 핸드오프 요약

## 헤드리스 Phase 운영
- `--use-headless-phases`를 사용하면 오케스트레이터가 기존 Generator 직접 구현 대신 `scripts/run_phases.py`를 호출한다
- 기본 정책은 첫 Phase에서 문서가 업데이트되어 docs-diff가 생겨야 한다는 것이다
- 문서 변경이 필요 없는 예외 작업은 `--allow-empty-docs-diff`로 명시한다
- Phase 프롬프트에는 입력 파일, 변경 허용 범위, 기대 산출물, 검증 방법, 핸드오프 요구사항이 포함된다
- 각 Phase는 `.harness/tasks/sprint-{N}/{phase_id}-handoff.md`에 다음 Phase용 요약을 남긴다
- 재시도 시 완료되지 않은 Phase만 pending으로 되돌리고, done Phase는 재실행하지 않는다

## PR 자동화 운영
- `run_harness.py --auto-pr`을 사용하면 구현 성공 후 PR 파이프라인을 자동으로 이어서 실행한다
- `--pr-base`, `--pr-skip-review`, `--pr-auto-merge`로 PR 동작을 제어한다
- 통과한 스프린트가 0개이면 PR 파이프라인을 건너뛴다
- PR 파이프라인 실패는 구현 결과에 영향을 주지 않는다
- `scripts/auto_pr_pipeline.py`는 단독으로도 실행 가능하며, 현재 브랜치 push → PR 생성 → 리뷰 수집 → 리뷰 반영 → 답글 → 선택적 머지 순서로 동작한다
- 리뷰 코멘트 판정은 `ACCEPT`, `DEFER`, `IGNORE` 중 하나다
- `ACCEPT` 코멘트만 `claude --print` 리뷰 반영 세션에 전달한다
- 판정 로그는 `.harness/review-artifacts/{branch}/review-comments.md`에 저장한다
- 반영 커밋이 성공적으로 push된 경우에만 원본 PR 리뷰 코멘트에 한국어 답글을 남긴다
- GitHub review thread resolve는 답글 기반 확인으로 대체한다
- CodeRabbit은 외부 리뷰어로 취급한다. CodeRabbit이 남긴 PR 인라인 코멘트도 동일하게 수집·분류·반영한다
- CodeRabbit 자동 검증은 저장소에 CodeRabbit GitHub App이 설치되어 있고, `gh` CLI 인증이 되어 있다는 전제에서 동작한다
- optional/nit/칭찬성 CodeRabbit 코멘트는 DEFER로 남기고 자동 반영하지 않는다

## 프로젝트 정책 파일 운영
- 정책 파일 위치는 `.harness/project-policy.yaml`이다
- 파일이 없거나 파싱에 실패하면 기본 정책을 사용한다
- 기본 필수 검사는 `ruff`, `mypy`, `pytest`, `structure`이다
- 기본 문서 경로는 `docs/code-convention.yaml`, `docs/adr/`, `harness_structure.yaml`이다
- `custom_rules`는 Planner와 Evaluator가 참고하는 프로젝트별 판단 기준이다
- `adr.external_sources`로 외부 프로젝트의 ADR 디렉터리 경로를 지정할 수 있다
- 외부 ADR 소스 경로가 존재하지 않거나 디렉터리가 아니면 건너뛴다 (오류 없음)
- 외부 ADR은 modify 컨텍스트, GuideRegistry, ContextFilter 모두에 반영된다
- 정책 파일에는 토큰, 비밀값, 개인 계정 정보를 넣지 않는다
- 정책 변경 후에는 `ruff check`, `mypy harness`, `python3 scripts/check_structure.py`, `pytest`를 실행한다

## 체크포인트 경로
- `.harness/checkpoints/{run_id}.json` — 실행별 체크포인트
- `.harness/checkpoints/latest.json` — 최근 실행 포인터
- `--project-dir` 없이 `--resume`/`--run-id`를 사용할 때 현재 디렉터리에 체크포인트가 있으면 현재 디렉터리의 modify 실행으로 재개한다

## 수정 모드 컨텍스트
- 현재 git 브랜치, staged/unstaged diff, 변경 파일 목록을 수집한다
- 설계 의도, 코드 컨벤션, ADR, 구조 규칙, 최근 ruff/mypy 요약을 Planner에게 전달한다
- `.harness/project-policy.yaml`이 있으면 컨벤션·ADR·구조 규칙 경로와 프로젝트 정책을 반영한다
- 정책의 `adr.external_sources`가 있으면 외부 프로젝트 ADR도 함께 로드하여 Planner 컨텍스트에 포함한다

## 품질 기준
- ruff 에러 0개
- mypy 에러 0개 (strict 모드)
- pytest 전체 통과
- 구조 규칙 위반 0개

## ADR 목록
| ADR | 제목 | 핵심 결정 |
|-----|------|-----------|
| 0001 | 3-에이전트 아키텍처 | Planner→Generator→Evaluator 파이프라인, 계약 협상 |
| 0002 | 연산적 센서 우선 | 결정적 검사(lint→type→structure→test) 후 AI 리뷰 |
| 0003 | ADR 기반 아키텍처 규칙 | ADR + harness_structure.yaml 검증 |
| 0004 | 리뷰 산출물 워크플로 | 브랜치별 설계 의도, 기준, PR 본문, 반영 로그 |
| 0005 | 구조화 스프린트 계약 | raw 텍스트 보존 + 구조화 파싱, JSON 저장 |
| 0006 | 체크포인트와 재개 | Phase enum, run_id 기반 세션 복원 |
| 0007 | 가이드 레지스트리 | 시스템 프롬프트/컨텍스트 중앙 관리 |
| 0008 | 수정 모드와 프로젝트 정책 | modify 구현, project-policy.yaml 정책 적용 |
| 0009 | Phase 실행과 컨텍스트 격리 | docs-diff, Phase 분할, 유사 RAG 필터, 헤드리스 실행, PR 자동화, 세션 포크 |
