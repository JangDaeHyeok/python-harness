# Python Harness Framework

AI 코딩 에이전트를 위한 하네스 엔지니어링 프레임워크.

## 기술 스택
- Python 3.11+
- Anthropic SDK (Claude API)
- pytest, ruff, mypy

## 아키텍처 규칙
- CRITICAL: 센서(sensors/)는 에이전트(agents/)에 의존 금지 (단방향)
- CRITICAL: 모든 아키텍처 결정은 docs/adr/에 기록
- 모든 public 함수에 타입 힌트 필수

## 프로젝트 구조
```
harness/
├── agents/        # 3-에이전트: Planner, Generator, Evaluator, Orchestrator
├── sensors/
│   ├── computational/  # 린터, 테스트, 타입체커, 구조분석
│   └── inferential/    # AI 코드 리뷰
├── pipeline/      # 통합 파이프라인
├── review/        # 리뷰 워크플로: 산출물, 컨벤션, 기준, 설계의도, PR본문, 반영로그, worktree
├── guides/        # 시스템 프롬프트, 규칙 엔진
├── context/       # 세션 상태, 체크포인트, 컨텍스트 관리
├── contracts/     # 스프린트 계약 모델(SprintContract)과 저장소(ContractStore)
└── tools/         # 파일/셸/Git 도구
```

## 문서 맵
- `docs/adr/` — Architecture Decision Records (0001~0007)
- `docs/code-convention.yaml` — 코드 컨벤션 규칙 (ConventionLoader로 로드)
- `harness_structure.yaml` — 자동 검증되는 아키텍처 규칙
- `.harness/review-artifacts/{branch}/` — 브랜치별 리뷰 산출물

## 명령어
```bash
pip install -e ".[dev]"           # 개발 의존성 설치
python scripts/run_harness.py "프롬프트"  # 하네스 실행
python scripts/create_pr_body.py --base main  # PR 본문 생성
python scripts/create_pr_body.py --base main --output pr-body.md
ruff check .                      # 린트
mypy harness                      # 타입 체크
pytest                            # 테스트
python scripts/check_structure.py # 구조 분석
```

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

## 품질 기준
- ruff 에러 0개
- mypy 에러 0개 (strict 모드)
- pytest 전체 통과
- 구조 규칙 위반 0개
