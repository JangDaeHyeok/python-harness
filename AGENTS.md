# Python Harness Framework — Agent Guide

이 문서는 하네스 프레임워크 내에서 동작하는 AI 에이전트(Planner, Generator, Evaluator)가 참조하는 런타임 컨텍스트입니다.

## 에이전트 역할

| 에이전트 | 역할 | 입력 | 출력 |
|----------|------|------|------|
| **Planner** | 사용자 프롬프트를 제품 스펙과 스프린트 계획으로 변환 | 사용자 프롬프트, (modify 시) 프로젝트 컨텍스트 | ProductSpec |
| **Generator** | 스프린트 계약에 따라 코드 생성·수정 | SprintContract, project_dir | 파일 변경 |
| **Evaluator** | 스프린트 결과가 계약·품질 기준을 만족하는지 평가 | SprintContract, project_dir | EvaluationResult |

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
- Planner는 기존 코드베이스 컨텍스트(diff, ADR, 컨벤션, 구조 규칙, 정책)를 받는다.
- Generator는 기존 파일의 최소 변경에 집중하며, 기존 패턴을 재사용한다.
- Evaluator는 변경 정확성과 기존 기능 보존을 더 강하게 본다.

## 아키텍처 규칙 (에이전트 필수 준수)

1. **센서 독립성**: sensors/는 agents/를 임포트하지 않는다 (ADR-0001)
2. **검사 순서**: ruff → mypy → 구조 → pytest → AI 리뷰 (ADR-0002)
3. **ADR 기록**: 아키텍처 결정은 docs/adr/에 기록한다 (ADR-0003)
4. **타입 힌트**: 모든 public 함수에 타입 힌트 필수
5. **셸 안전**: 셸 명령은 harness/tools/shell.py 래퍼 사용
6. **print 금지**: harness/ 내부에서 print() 사용 금지, logging 사용
7. **파싱 안전**: LLM 응답 파싱 실패 시 안전한 기본값으로 폴백
8. **최소 변경**: modify 모드에서 불필요한 리팩터링, 추상화 금지

## 코드 컨벤션 위치
- `docs/code-convention.yaml` — ConventionLoader로 로드
- `harness_structure.yaml` — StructureAnalyzer로 검증

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
└── review-artifacts/<branch>/
    ├── design-intent.md              # 설계 의도
    ├── code-quality-guide.md         # 평가 기준
    ├── pr-body.md                    # PR 본문
    └── review-comments.md            # 리뷰 반영 판단 로그
```

## 품질 기준

에이전트가 생성한 코드는 다음 기준을 모두 통과해야 한다:

- ruff 에러 0개
- mypy 에러 0개 (strict 모드)
- pytest 전체 통과
- harness_structure.yaml 규칙 위반 0개

## 리뷰 정책
- 코드 리뷰, PR 리뷰, 리뷰 코멘트 응답은 한국어로 작성한다.

## 프로젝트 정책
- `.harness/project-policy.yaml`이 있으면 컨벤션, ADR, 구조 규칙 경로와 프로젝트별 정책을 반영한다.
- 정책이 없으면 기본 경로(docs/code-convention.yaml, docs/adr/, harness_structure.yaml)를 사용한다.
