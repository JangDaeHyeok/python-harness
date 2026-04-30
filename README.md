# Python Harness Framework

AI 코딩 에이전트를 위한 하네스 엔지니어링 프레임워크입니다.

사용자는 만들고 싶은 제품을 자연어로 설명하고, 하네스는 그 설명을 실행 가능한 계획으로 바꾼 뒤 코드 생성, 품질 검사, 평가, 리뷰 산출물 생성을 하나의 흐름으로 묶어 실행합니다.

## 목차

- [하네스가 하는 일](#하네스가-하는-일)
- [현재 기능 표](#현재-기능-표)
- [설치](#설치)
- [환경변수](#환경변수)
- [사용법](#사용법)
  - [새 프로젝트 생성 (create 모드)](#새-프로젝트-생성-create-모드)
  - [기존 코드베이스 수정 (modify 모드)](#기존-코드베이스-수정-modify-모드)
  - [중단된 실행 재개](#중단된-실행-재개)
  - [Worktree 격리 실행](#worktree-격리-실행)
  - [PR 본문 생성](#pr-본문-생성)
  - [품질 검사](#품질-검사)
  - [구조 규칙 검사](#구조-규칙-검사)
- [CLI 옵션 레퍼런스](#cli-옵션-레퍼런스)
  - [run_harness.py](#run_harnesspy)
  - [create_pr_body.py](#create_pr_bodypy)
- [프로젝트 정책 파일](#프로젝트-정책-파일)
- [동작 방식](#동작-방식)
- [프로젝트 구조](#프로젝트-구조)
- [산출물](#산출물)
- [주요 API 사용법](#주요-api-사용법)
- [CI/CD 통합](#cicd-통합)
- [아키텍처 원칙](#아키텍처-원칙)
- [라이선스](#라이선스)

## 하네스가 하는 일

하네스는 세 가지 역할의 에이전트를 중심으로 동작합니다.

- **Planner**: 사용자 프롬프트를 제품 스펙과 스프린트 계획으로 변환합니다.
- **Generator**: 각 스프린트의 목표에 따라 프로젝트 파일을 작성하고 필요한 명령을 실행합니다.
- **Evaluator**: 생성된 결과가 계약, 품질 기준, 테스트 조건을 만족하는지 평가합니다.

이 흐름 위에 Ruff, mypy, pytest, 구조 규칙 검사, AI 코드 리뷰를 센서처럼 연결해 빠른 검증부터 의미 기반 리뷰까지 단계적으로 수행합니다.

## 현재 기능 표

| 영역 | 현재 상태 | 구현 위치 |
|------|-----------|-----------|
| 3-에이전트 실행 | Planner, Generator, Evaluator, Orchestrator 스프린트 루프 | `harness/agents/` |
| 연산적 센서 | Ruff, mypy, pytest, 구조 규칙 검사 | `harness/sensors/computational/`, `harness/pipeline/` |
| AI 코드 리뷰 | 현재 브랜치 diff 기반 리뷰, 평가 기준 포함 리뷰 | `harness/sensors/inferential/code_reviewer.py`, `scripts/pr_review.py` |
| 리뷰 산출물 | 설계 의도, 평가 기준, PR 본문, 리뷰 반영 판단 로그 | `harness/review/` |
| worktree 안전화 | 임시 git worktree 격리 실행, 로컬 변경 충돌 감지, 생성 실패 시 fallback 금지 | `harness/review/worktree.py`, `harness/agents/orchestrator.py` |
| 구조화 계약 | raw 계약 보존, 기능/검증 기준 최선 노력 파싱, JSON 저장 | `harness/contracts/` |
| 체크포인트 | 실행 상태 저장, latest 포인터, `--resume`/`--run-id` 재개 | `harness/context/checkpoint.py`, `scripts/run_harness.py` |
| 수정 모드 | 기존 코드베이스 컨텍스트 수집, modify 전용 프롬프트, 프로젝트 정책 반영 | `harness/context/modify_context.py`, `harness/context/project_policy.py` |
| 가이드 레지스트리 | 에이전트 시스템 프롬프트 조회, 필요 시 ADR/컨벤션 컨텍스트 조립 | `harness/guides/` |
| 구조 규칙 | ADR 연계 의존성/필수 파일/금지 패턴 검사 | `harness_structure.yaml`, `scripts/check_structure.py` |

## 설치

### 요구 사항

- Python 3.11 이상
- Git (worktree 격리 및 diff 기반 기능에 필요)

### 기본 설치

```bash
git clone <repo-url>
cd python-harness

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

### 개발 의존성 포함 설치

개발, 테스트, 린트, 타입 체크를 위한 도구를 함께 설치합니다.

```bash
pip install -e ".[dev]"
```

설치되는 개발 도구:
- `pytest` (>=8.0): 테스트 실행
- `pytest-cov` (>=5.0): 커버리지 측정
- `ruff` (>=0.11.0): 린터
- `mypy` (>=1.15): 타입 체커 (strict 모드)
- `types-PyYAML` (>=6.0): PyYAML 타입 스텁

### 설치 후 CLI 확인

`pip install -e .`로 설치하면 두 개의 CLI 커맨드가 등록됩니다.

```bash
harness "프로젝트 설명"           # scripts/run_harness.py의 래퍼
create-pr-body --base main       # scripts/create_pr_body.py의 래퍼
```

`python scripts/run_harness.py` 대신 `harness` 명령을 사용해도 동일합니다.

## 환경변수

| 이름 | 설명 | 필수 여부 |
|------|------|-----------|
| `HARNESS_API_ENDPOINT` | Planner, Generator, Evaluator, AI 리뷰가 호출할 비공개 API 엔드포인트 | AI 호출 기능 사용 시 필수 |

AI 호출이 필요한 기능을 사용하려면 엔드포인트를 환경변수로 주입합니다. 실제 엔드포인트 값은 저장소에 커밋하지 않고 로컬 셸, CI secret, 배포 환경에서만 설정합니다.

```bash
export HARNESS_API_ENDPOINT="https://your-private-endpoint.example.com"
```

환경변수 대신 실행 시 `--api-endpoint` 옵션으로 직접 넘길 수도 있습니다.

`HARNESS_API_ENDPOINT`가 설정되지 않은 상태에서 AI 호출이 필요한 기능을 실행하면 하네스는 명확한 설정 오류를 반환합니다.

## 사용법

### 새 프로젝트 생성 (create 모드)

가장 기본적인 사용법입니다. 자연어로 만들고 싶은 프로젝트를 설명하면 됩니다.

```bash
python scripts/run_harness.py "브라우저에서 동작하는 간단한 ToDo 앱을 만들어주세요"
```

`--mode create`가 기본값이므로 생략할 수 있습니다. 출력 디렉터리를 지정하지 않으면 `./project`에 생성됩니다.

**출력 디렉터리 지정:**

```bash
python scripts/run_harness.py \
  --project-dir ./my-todo-app \
  "React와 FastAPI로 ToDo 앱을 만들어주세요"
```

**모델과 스프린트 수 조절:**

```bash
python scripts/run_harness.py \
  --project-dir ./my-app \
  --model claude-sonnet-4-6 \
  --max-sprints 10 \
  --max-retries 5 \
  "실시간 채팅 앱을 만들어주세요"
```

**API 엔드포인트를 직접 지정:**

```bash
python scripts/run_harness.py \
  --api-endpoint "https://your-private-endpoint.example.com" \
  "브라우저에서 동작하는 간단한 ToDo 앱을 만들어주세요"
```

**상세 로그 출력:**

```bash
python scripts/run_harness.py -v "프로젝트 설명"
```

### 기존 코드베이스 수정 (modify 모드)

기존 저장소를 수정하려면 저장소 루트에서 `--mode modify`를 사용합니다.

```bash
python scripts/run_harness.py \
  --mode modify \
  "로그인 실패 시 사용자에게 더 명확한 에러 메시지를 보여주세요"
```

modify 모드에서 `--project-dir`을 생략하면 현재 디렉터리가 수정 대상입니다. 다른 디렉터리를 수정하려면 명시적으로 지정합니다.

```bash
python scripts/run_harness.py \
  --mode modify \
  --project-dir ../my-existing-app \
  "결제 취소 플로우의 테스트를 보강하고 실패 케이스를 수정해주세요"
```

**modify 모드가 Planner에게 전달하는 컨텍스트:**

| 컨텍스트 | 출처 |
|----------|------|
| 현재 git 브랜치 | `git rev-parse --abbrev-ref HEAD` |
| staged/unstaged diff | `git diff`, `git diff --cached` |
| 변경된 파일 목록 | `git status` |
| 설계 의도 | `.harness/review-artifacts/<branch>/design-intent.md` |
| 코드 컨벤션 | `docs/code-convention.yaml` |
| ADR 목록 | `docs/adr/` |
| 구조 규칙 | `harness_structure.yaml` |
| 최근 검증 요약 | `ruff`, `mypy` 실행 결과 |
| 프로젝트 정책 | `.harness/project-policy.yaml` (선택) |

Generator와 Evaluator도 modify 전용 시스템 프롬프트를 사용합니다. Generator는 새 프로젝트를 만들지 않고 기존 파일의 최소 변경에 집중하며, Evaluator는 변경 정확성과 기존 기능 보존을 더 강하게 봅니다.

**modify 모드 예시 — 작은 버그 수정:**

```bash
python scripts/run_harness.py \
  --mode modify \
  "체크포인트 재개 시 project-dir 기본값이 잘못 잡히는 문제를 수정하고 테스트를 추가해주세요"
```

**modify 모드 예시 — worktree 격리와 함께:**

```bash
python scripts/run_harness.py \
  --mode modify \
  --use-worktree \
  --worktree-sync-exclude .pytest_cache \
  "리뷰 산출물 생성 로직의 에러 처리를 강화해주세요"
```

### 중단된 실행 재개

중단된 실행은 최근 체크포인트 또는 특정 run_id로 재개할 수 있습니다. 체크포인트는 실행 대상 프로젝트의 `.harness/checkpoints/` 아래에 저장됩니다.

**최근 체크포인트에서 재개:**

```bash
# create 모드 프로젝트 재개 (프로젝트 디렉터리 명시)
python scripts/run_harness.py --project-dir ./project --resume

# modify 모드 프로젝트 재개 (현재 디렉터리에 체크포인트가 있을 때)
python scripts/run_harness.py --resume
```

**특정 run_id에서 재개:**

```bash
python scripts/run_harness.py --project-dir ./project --run-id abc123def456
python scripts/run_harness.py --run-id abc123def456
```

**재개 동작 규칙:**

- `--project-dir`이 명시되면 해당 디렉터리의 체크포인트를 찾습니다 (항상 우선).
- `--project-dir` 없이 `--resume`/`--run-id`를 사용하면:
  - 현재 디렉터리에 `.harness/checkpoints/latest.json` 또는 해당 run_id 파일이 있으면 현재 디렉터리를 modify 프로젝트로 재개합니다.
  - 없으면 기본 `./project` 디렉터리의 체크포인트를 찾습니다.

### Worktree 격리 실행

`--use-worktree` 옵션을 켜면 스프린트 구현 시도를 임시 git worktree에서 수행한 뒤, 변경된 파일만 메인 프로젝트로 동기화합니다.

```bash
python scripts/run_harness.py \
  --use-worktree \
  --worktree-sync-exclude tmp \
  --worktree-sync-exclude cache \
  "만들고 싶은 프로젝트 설명"
```

동기화 규칙:
- 추가, 수정, 삭제를 모두 반영합니다.
- 같은 경로에 로컬 변경이 있으면 덮어쓰거나 삭제하지 않고 중단합니다.
- `--worktree-sync-exclude`로 지정한 경로는 동기화에서 제외됩니다 (반복 지정 가능).

### PR 본문 생성

현재 브랜치의 변경 내용을 바탕으로 PR 본문을 자동 생성합니다.

```bash
# 표준 출력으로 출력
python scripts/create_pr_body.py --base main

# 파일로 저장
python scripts/create_pr_body.py --base main --output pr-body.md

# 브랜치명 오버라이드
python scripts/create_pr_body.py --base main --branch feature/my-feature

# worktree 격리 실행
python scripts/create_pr_body.py --base main --use-worktree
```

### 품질 검사

로컬에서 개별 품질 검사를 실행할 수 있습니다.

```bash
# 린트 (ruff)
ruff check .

# 타입 체크 (mypy, strict 모드)
mypy harness

# 테스트 (pytest)
pytest

# 전체 검사를 한 번에
ruff check . && mypy harness && pytest && python scripts/check_structure.py
```

### 구조 규칙 검사

`harness_structure.yaml`에 정의된 아키텍처 규칙 위반을 검사합니다.

```bash
python scripts/check_structure.py
```

검사 항목:
- 센서 → 에이전트 의존성 금지 (ADR-0001)
- 필수 파일 존재 여부
- 리뷰 모듈의 에이전트 독립성
- 계약 모듈의 격리
- 가이드 레지스트리 제약
- 컨텍스트 모듈 독립성
- `harness/` 내 `print()` 사용 금지
- modify 모드 필수 파일 존재

## CLI 옵션 레퍼런스

### run_harness.py

```
python scripts/run_harness.py [OPTIONS] [PROMPT]
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `prompt` | `""` | 프로젝트 설명 (1~4문장). 새 실행에는 필요하며, 재개 시에는 생략 가능 |
| `--project-dir` | 모드별 기본값 | 대상 디렉터리. create=`./project`, modify=현재 디렉터리 |
| `--model` | `claude-sonnet-4-6` | Planner/Generator/Evaluator가 사용할 모델명 |
| `--api-endpoint` | `$HARNESS_API_ENDPOINT` | API 엔드포인트. 지정하면 환경변수를 덮어씀 |
| `--mode` | `create` | 실행 모드. `create` 또는 `modify` |
| `--max-retries` | `3` | 스프린트당 최대 구현 재시도 횟수 |
| `--max-sprints` | `15` | 실행할 최대 스프린트 수 |
| `--app-url` | `http://localhost:3000` | Evaluator가 확인할 앱 URL |
| `--no-context-reset` | `false` | 재시도 사이 Generator 컨텍스트 리셋 비활성화 |
| `--run-id` | `""` | 지정한 체크포인트 run_id에서 재개 |
| `--resume` | `false` | `.harness/checkpoints/latest.json`이 가리키는 실행 재개 |
| `--use-worktree` | `false` | 스프린트 구현을 임시 git worktree에서 격리 실행 |
| `--worktree-sync-exclude` | `[]` | worktree 동기화 제외 경로 (반복 지정 가능) |
| `-v`, `--verbose` | `false` | 상세 로그 출력 |

### create_pr_body.py

```
python scripts/create_pr_body.py [OPTIONS]
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--base` | `main` | 기준 브랜치 |
| `--project-dir` | `.` | 프로젝트 루트 디렉터리 |
| `--summary` | `""` | PR 요약 텍스트 |
| `--output` | `None` | 출력 파일 경로. 미지정 시 표준 출력 |
| `--branch` | `None` | 산출물 브랜치명 오버라이드 |
| `--use-worktree` | `false` | worktree 격리 실행 |

## 프로젝트 정책 파일

프로젝트별 정책은 `.harness/project-policy.yaml`에 둘 수 있습니다. 파일이 없으면 기본값을 사용합니다.

```yaml
project:
  name: python-harness
  language: python
  python_version: "3.11+"
policies:
  review_language: ko
  required_checks:
    - ruff
    - mypy
    - pytest
    - structure
  conventions:
    source: docs/code-convention.yaml
  adr:
    directory: docs/adr/
  structure:
    source: harness_structure.yaml
  artifacts:
    design_intent: true
    code_quality_guide: true
    review_comments: true
    pr_body: true
```

정책 파일은 modify 컨텍스트 수집 시 컨벤션, ADR, 구조 규칙 위치를 결정하는 데 사용됩니다. 정책 파일 자체도 Planner에게 전달되어 프로젝트별 리뷰 언어와 필수 검사 기준을 참고할 수 있게 합니다.

## 동작 방식

### 실행 흐름

```text
사용자 프롬프트
  -> create: Planner가 제품 스펙과 스프린트 계획 작성
  -> modify: 현재 프로젝트 컨텍스트 수집 후 Planner가 수정 계획 작성
  -> Generator와 Evaluator가 스프린트 계약 협의
  -> Generator가 스프린트 결과 생성
  -> Evaluator가 결과 평가
  -> 실패 시 피드백을 반영해 재시도 (최대 max-retries)
  -> 모든 스프린트 결과와 요약 산출
```

### 품질 검사 파이프라인

빠르고 결정적인 검사부터 실행됩니다.

```text
ruff (린트)
  -> mypy (타입 체크)
  -> 구조 규칙 검사
  -> pytest (테스트)
  -> AI 코드 리뷰
```

이 순서는 명확한 오류를 먼저 잡아내고, 비용이 큰 AI 리뷰는 필요한 시점에만 사용하기 위한 것입니다 (ADR-0002).

## 프로젝트 구조

```
python-harness/
├── harness/                    # 메인 프레임워크 패키지
│   ├── agents/                 # 3-에이전트: Planner, Generator, Evaluator, Orchestrator
│   │   ├── base_agent.py       #   BaseAgent (ABC), AgentMessage, AgentConfig
│   │   ├── planner.py          #   PlannerAgent → ProductSpec
│   │   ├── generator.py        #   GeneratorAgent (스프린트 구현, 파일/셸/Git 도구)
│   │   ├── evaluator.py        #   EvaluatorAgent → EvaluationResult
│   │   └── orchestrator.py     #   HarnessOrchestrator (스프린트 루프, 체크포인트, worktree)
│   ├── sensors/
│   │   ├── computational/      # 결정적 센서
│   │   │   ├── linter.py       #   LinterSensor (ruff)
│   │   │   ├── type_checker.py #   TypeCheckerSensor (mypy strict)
│   │   │   ├── test_runner.py  #   TestRunnerSensor (pytest)
│   │   │   └── structure_test.py #  StructureAnalyzer (harness_structure.yaml)
│   │   └── inferential/        # AI 기반 센서
│   │       └── code_reviewer.py #  CodeReviewer (diff 기반 AI 리뷰)
│   ├── pipeline/               # 통합 파이프라인
│   │   └── harness_pipeline.py #   HarnessPipeline (ruff→mypy→구조→pytest→AI리뷰)
│   ├── review/                 # 리뷰 워크플로
│   │   ├── artifacts.py        #   ReviewArtifactManager (브랜치별 산출물)
│   │   ├── conventions.py      #   ConventionLoader (code-convention.yaml)
│   │   ├── criteria.py         #   CriteriaGenerator, ADRLoader
│   │   ├── intent.py           #   IntentGenerator (설계 의도)
│   │   ├── reflection.py       #   ReviewReflection (리뷰 반영 판단)
│   │   ├── pr_body.py          #   PRBodyGenerator
│   │   ├── pipeline_integration.py # 리뷰 파이프라인 헬퍼
│   │   └── worktree.py         #   WorktreeManager (git worktree 격리)
│   ├── guides/                 # 가이드 레지스트리
│   │   ├── registry.py         #   GuideRegistry (시스템 프롬프트, ADR/컨벤션 컨텍스트)
│   │   └── prompts.py          #   create/modify 모드별 시스템 프롬프트
│   ├── contracts/              # 스프린트 계약
│   │   ├── models.py           #   SprintContract, AcceptanceCriterion
│   │   └── store.py            #   ContractStore (JSON 저장)
│   ├── context/                # 세션/프로젝트 컨텍스트
│   │   ├── checkpoint.py       #   CheckpointStore, SessionState, Phase
│   │   ├── modify_context.py   #   ModifyContextCollector
│   │   └── project_policy.py   #   ProjectPolicyManager
│   └── tools/                  # 유틸리티 도구
│       ├── api_client.py       #   HarnessClient (Claude API HTTP 클라이언트)
│       ├── shell.py            #   run_command_safe, validate_command, validate_path
│       ├── file_io.py          #   atomic_write_text
│       ├── path_safety.py      #   sanitize_branch_name, validate_run_id
│       └── json_types.py       #   타입 변환 유틸리티
├── scripts/                    # CLI 스크립트
│   ├── run_harness.py          #   메인 하네스 실행 (create/modify/resume)
│   ├── create_pr_body.py       #   PR 본문 생성
│   ├── check_structure.py      #   구조 규칙 검사
│   └── pr_review.py            #   GitHub Actions PR AI 리뷰
├── tests/                      # 테스트 (24개 모듈)
├── docs/
│   ├── adr/                    # Architecture Decision Records (0001~0008)
│   └── code-convention.yaml    # 코드 컨벤션 규칙
├── harness_structure.yaml      # 아키텍처 구조 검증 규칙
├── pyproject.toml              # 패키지 설정
├── CLAUDE.md                   # AI 에이전트 개발 가이드
└── AGENTS.md                   # 에이전트 런타임 컨텍스트
```

## 산출물

하네스 실행 중 생성되는 주요 산출물은 프로젝트 디렉터리 아래에 저장됩니다.

```text
.harness/
├── artifacts/
│   ├── spec.json                     # 제품 스펙 (Planner 출력)
│   ├── summary.json                  # 실행 요약
│   └── sprint_<N>_contract.md        # 스프린트 계약 원문
├── contracts/
│   └── sprint_<N>.json               # 구조화된 스프린트 계약 (JSON)
├── checkpoints/
│   ├── <run_id>.json                 # 실행별 체크포인트
│   └── latest.json                   # 최근 실행 포인터
└── review-artifacts/<branch>/
    ├── design-intent.md              # 설계 의도
    ├── code-quality-guide.md         # 평가 기준
    ├── pr-body.md                    # PR 본문
    └── review-comments.md            # 리뷰 반영 판단 로그
```

## 주요 API 사용법

### 평가 기준 생성

```python
from pathlib import Path
from harness.review.criteria import CriteriaGenerator

gen = CriteriaGenerator(Path("."))
criteria = gen.generate(task_description="인증 모듈 리팩터링")
md = gen.to_markdown(criteria)  # list[EvalCriterion]을 마크다운으로 변환
```

### Worktree 격리 실행

```python
from pathlib import Path
from harness.review.worktree import WorktreeManager

mgr = WorktreeManager(Path("."))

def my_task(work_dir: Path) -> list[Path]:
    output = work_dir / "result.md"
    output.write_text("# Result", encoding="utf-8")
    return [output]

mgr.run_isolated(my_task, preserve_to=Path(".harness/review-artifacts/my-branch"))
```

### 리뷰 산출물 관리

```python
from pathlib import Path
from harness.review.artifacts import ReviewArtifactManager

manager = ReviewArtifactManager(Path("."))
manager.save("design-intent.md", "# 설계 의도\n...")
content = manager.load("design-intent.md")
```

### Modify 컨텍스트 수집

```python
from pathlib import Path
from harness.context.modify_context import ModifyContextCollector

collector = ModifyContextCollector(Path("."))
ctx = collector.collect()
# ctx.branch, ctx.staged_diff, ctx.unstaged_diff, ctx.changed_files, ...
```

## CI/CD 통합

### GitHub Actions

`.github/workflows/pr-check.yml`이 PR에 대해 자동으로 실행됩니다.

| Job | 설명 | 의존성 |
|-----|------|--------|
| `lint` | Ruff 린트 검사 | - |
| `type-check` | mypy 타입 검사 | - |
| `test` | pytest 테스트 실행 | - |
| `structure` | 구조 규칙 검사 | - |
| `ai-review` | AI 코드 리뷰 | lint, type-check, test, structure 모두 통과 후 |
| `pr-body` | PR 본문 자동 생성 | lint |

AI 리뷰를 사용하려면 저장소 secret에 `HARNESS_API_ENDPOINT`를 등록합니다. Secret이 없으면 AI 리뷰 단계는 건너뜁니다.

### 독립 PR 리뷰 스크립트

`scripts/pr_review.py`는 GitHub Actions 환경에서 PR diff를 가져와 AI 리뷰를 수행합니다. `GITHUB_TOKEN`, `PR_NUMBER`, `HARNESS_API_ENDPOINT` 환경변수가 필요합니다.

## 아키텍처 원칙

- 센서는 에이전트에 의존하지 않습니다 (ADR-0001).
- 빠른 결정론적 검사를 먼저 실행하고, AI 리뷰는 뒤에서 보조합니다 (ADR-0002).
- 중요한 아키텍처 결정은 ADR로 남깁니다 (ADR-0003).
- ADR은 기본적으로 결정 기록과 구조 검증의 기준입니다. 모든 ADR 원문을 에이전트 런타임 프롬프트에 자동 주입하지는 않으며, 필요한 경우 `GuideRegistry.build_context()`로 컨텍스트를 조립해 사용할 수 있습니다 (ADR-0007).
- 모든 public 함수는 타입 힌트를 갖습니다.
- 수정 모드는 최소 변경, 기존 패턴 재사용, 프로젝트 정책 준수를 기본 원칙으로 합니다 (ADR-0008).

## 라이선스

내부 프레임워크입니다.
