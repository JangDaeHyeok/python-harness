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
- 모든 public 함수에 타입 힌트 필수
- 셸 명령은 반드시 harness/tools/shell.py의 run_command_safe, validate_command 사용
- 파일 경로 접근은 validate_path로 검증
- LLM 응답 파싱 실패 시 안전한 기본값으로 폴백 (예외 전파 금지)
- __init__에서 부수 효과 금지
- 수정 모드(`--mode modify`)는 기존 코드베이스 최소 변경, 기존 패턴 재사용, 프로젝트 정책 준수를 기본 원칙으로 한다

## 프로젝트 구조
```
harness/
├── agents/        # 3-에이전트: Planner, Generator, Evaluator, Orchestrator
├── sensors/
│   ├── computational/  # 린터, 테스트, 타입체커, 구조분석
│   └── inferential/    # AI 코드 리뷰
├── pipeline/      # 통합 파이프라인 (ruff→mypy→구조→pytest→AI리뷰)
├── review/        # 리뷰 워크플로: 산출물, 컨벤션, 기준, 설계의도, PR본문, 반영로그, worktree
├── guides/        # 시스템 프롬프트, 가이드 레지스트리 (ADR/컨벤션 컨텍스트 조립)
├── context/       # 세션 상태, 체크포인트, modify 컨텍스트, 프로젝트 정책
├── contracts/     # 스프린트 계약 모델(SprintContract)과 저장소(ContractStore)
└── tools/         # API 클라이언트, 파일 I/O, 셸 안전 래퍼, 경로 검증, 타입 변환
```

## 문서 맵
- `docs/adr/` — Architecture Decision Records (0001~0008)
- `docs/code-convention.yaml` — 코드 컨벤션 규칙 (ConventionLoader로 로드)
- `harness_structure.yaml` — 자동 검증되는 아키텍처 규칙 (10개 규칙)
- `.harness/review-artifacts/{branch}/` — 브랜치별 리뷰 산출물
- `.harness/project-policy.yaml` — modify 모드 프로젝트 정책(선택)

## 명령어
```bash
pip install -e ".[dev]"           # 개발 의존성 설치
python scripts/run_harness.py "프롬프트"  # create 모드: 새 프로젝트 생성
python scripts/run_harness.py --mode modify "수정 요청"  # modify 모드: 현재 코드베이스 수정
python scripts/run_harness.py --resume  # 현재 디렉터리 체크포인트가 있으면 modify 실행 재개
python scripts/run_harness.py --run-id <run_id>  # 특정 체크포인트에서 재개
python scripts/create_pr_body.py --base main  # PR 본문 생성
python scripts/create_pr_body.py --base main --output pr-body.md
ruff check .                      # 린트
mypy harness                      # 타입 체크
pytest                            # 테스트
python scripts/check_structure.py # 구조 분석
```

## CLI 엔트리포인트
pyproject.toml에 등록된 CLI 커맨드:
- `harness` → `scripts.run_harness:main`
- `create-pr-body` → `scripts.create_pr_body:main`

## 리뷰 산출물 경로
- `.harness/review-artifacts/{branch}/design-intent.md` — 설계 의도
- `.harness/review-artifacts/{branch}/code-quality-guide.md` — 평가 기준
- `.harness/review-artifacts/{branch}/pr-body.md` — PR 본문
- `.harness/review-artifacts/{branch}/review-comments.md` — 리뷰 반영 판단 로그

## 리뷰 정책
- 코드 리뷰, PR 리뷰, 리뷰 코멘트 응답은 한국어로 작성한다.

## 계약 저장 경로
- `.harness/contracts/sprint_{N}.json` — 스프린트별 구조화 계약 (JSON)

## 체크포인트 경로
- `.harness/checkpoints/{run_id}.json` — 실행별 체크포인트
- `.harness/checkpoints/latest.json` — 최근 실행 포인터
- `--project-dir` 없이 `--resume`/`--run-id`를 사용할 때 현재 디렉터리에 체크포인트가 있으면 현재 디렉터리의 modify 실행으로 재개한다

## 수정 모드 컨텍스트
- 현재 git 브랜치, staged/unstaged diff, 변경 파일 목록을 수집한다
- 설계 의도, 코드 컨벤션, ADR, 구조 규칙, 최근 ruff/mypy 요약을 Planner에게 전달한다
- `.harness/project-policy.yaml`이 있으면 컨벤션·ADR·구조 규칙 경로와 프로젝트 정책을 반영한다

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
