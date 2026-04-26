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
├── guides/        # 시스템 프롬프트, 규칙 엔진
├── context/       # 세션 상태, 컨텍스트 관리
├── contracts/     # 스프린트 계약
└── tools/         # 파일/셸/Git 도구
```

## 문서 맵
- `docs/adr/` — Architecture Decision Records
- `harness_structure.yaml` — 자동 검증되는 아키텍처 규칙
- `docs/design-decisions/` — 설계 결정 상세

## 명령어
```bash
pip install -e ".[dev]"           # 개발 의존성 설치
python scripts/run_harness.py "프롬프트"  # 하네스 실행
ruff check .                      # 린트
mypy harness                      # 타입 체크
pytest                            # 테스트
python scripts/check_structure.py # 구조 분석
```

## 품질 기준
- ruff 에러 0개
- mypy 에러 0개 (strict 모드)
- pytest 전체 통과
- 구조 규칙 위반 0개
