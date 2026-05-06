# Python Harness Framework

AI 코딩 에이전트를 위한 하네스 엔지니어링 프레임워크입니다.

사용자는 만들고 싶은 제품을 자연어로 설명하고, 하네스는 그 설명을 실행 가능한 계획으로 바꾼 뒤 코드 생성, 품질 검사, 평가, 리뷰 산출물 생성을 하나의 흐름으로 묶어 실행합니다.

## 목차

- [하네스가 하는 일](#하네스가-하는-일)
- [현재 기능 표](#현재-기능-표)
- [설치](#설치)
- [환경변수](#환경변수)
- [빠른 시작](#빠른-시작)
- [운영 시나리오](#운영-시나리오)
- [사용법](#사용법)
  - [구현부터 PR 리뷰 반영까지 한 번에 (End-to-End)](#구현부터-pr-리뷰-반영까지-한-번에-end-to-end)
  - [새 프로젝트 생성 (create 모드)](#새-프로젝트-생성-create-모드)
  - [기존 코드베이스 수정 (modify 모드)](#기존-코드베이스-수정-modify-모드)
  - [중단된 실행 재개](#중단된-실행-재개)
  - [Worktree 격리 실행](#worktree-격리-실행)
  - [헤드리스 Phase 실행](#헤드리스-phase-실행)
  - [PR 본문 생성](#pr-본문-생성)
  - [PR 자동화 파이프라인](#pr-자동화-파이프라인)
  - [품질 검사](#품질-검사)
  - [구조 규칙 검사](#구조-규칙-검사)
- [CLI 옵션 레퍼런스](#cli-옵션-레퍼런스)
  - [도움말 확인 (`--help`)](#도움말-확인---help)
  - [run_harness.py / harness](#run_harnesspy--harness)
  - [auto_pr_pipeline.py / auto-pr-pipeline](#auto_pr_pipelinepy--auto-pr-pipeline)
  - [create_pr_body.py / create-pr-body](#create_pr_bodypy--create-pr-body)
- [프로젝트 정책 파일](#프로젝트-정책-파일)
  - [정책 파일 위치와 기본값](#정책-파일-위치와-기본값)
  - [정책 파일 예시](#정책-파일-예시)
  - [정책 적용 시점](#정책-적용-시점)
  - [프로젝트별 운영 패턴](#프로젝트별-운영-패턴)
- [동작 방식](#동작-방식)
  - [create/modify 공통 실행 흐름](#createmodify-공통-실행-흐름)
  - [End-to-End 흐름 (`--auto-pr`)](#end-to-end-흐름---auto-pr)
  - [헤드리스 Phase 내부 흐름](#헤드리스-phase-내부-흐름)
  - [docs-diff 생성 방식](#docs-diff-생성-방식)
  - [유사 RAG 컨텍스트 필터링](#유사-rag-컨텍스트-필터링)
  - [PR 자동화 내부 흐름](#pr-자동화-내부-흐름)
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
| Phase/docs-diff 실행 | Phase 계약 생성, docs-update 후 docs-diff 갱신, 헤드리스 실행 | `harness/context/phase_manager.py`, `harness/review/docs_diff.py`, `scripts/run_phases.py` |
| PR 자동화 | push, PR 생성, 리뷰 수집, headless 리뷰 반영, 선택적 머지 | `scripts/auto_pr_pipeline.py` |
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

`pip install -e .`로 설치하면 세 개의 CLI 커맨드가 등록됩니다.

| CLI 단축 명령 | 대응하는 스크립트 | 설명 |
|---------------|-------------------|------|
| `harness` | `python scripts/run_harness.py` | 메인 하네스 실행 (create/modify/resume) |
| `auto-pr-pipeline` | `python scripts/auto_pr_pipeline.py` | PR 자동화 파이프라인 |
| `create-pr-body` | `python scripts/create_pr_body.py` | PR 본문 생성 |

모든 옵션과 인자는 동일하게 사용할 수 있습니다. 이후 문서의 모든 `python scripts/...` 예시는 CLI 단축 명령으로 대체할 수 있습니다.

```bash
# 동일한 명령의 두 가지 형태
python scripts/run_harness.py --mode modify --use-headless-phases "수정 요청"
harness --mode modify --use-headless-phases "수정 요청"

python scripts/auto_pr_pipeline.py --base main --auto-merge
auto-pr-pipeline --base main --auto-merge

python scripts/create_pr_body.py --base main --output pr-body.md
create-pr-body --base main --output pr-body.md
```

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

## 빠른 시작

기존 저장소에서 작은 수정 작업을 맡기는 가장 일반적인 흐름입니다.

```bash
cd /path/to/existing-repo

# Python 스크립트 실행
python scripts/run_harness.py \
  --mode modify \
  --use-headless-phases \
  "로그인 실패 시 에러 메시지를 명확히 하고 관련 테스트를 보강해주세요"

# CLI 단축 명령 (동일)
harness --mode modify --use-headless-phases \
  "로그인 실패 시 에러 메시지를 명확히 하고 관련 테스트를 보강해주세요"
```

위 명령은 다음 일을 합니다.

1. 현재 저장소의 diff, ADR, 컨벤션, 구조 규칙을 읽습니다.
2. Planner가 수정용 스펙과 스프린트 계획을 만듭니다.
3. 스프린트 계약, 설계 의도, 평가 기준, Phase 파일을 생성합니다.
4. `phase-01-docs-update`를 먼저 실행하고 docs-diff를 갱신합니다.
5. 이후 Phase를 `claude --print` 독립 세션으로 순차 실행합니다.
6. Evaluator가 계약과 품질 기준으로 결과를 평가합니다.

### 구현부터 PR 리뷰 반영까지 한 번에 (End-to-End)

`--auto-pr` 플래그를 붙이면 구현 성공 후 PR 자동화 파이프라인까지 이어서 실행합니다.

```bash
# Python 스크립트
python scripts/run_harness.py \
  --mode modify \
  --use-headless-phases \
  --auto-pr --pr-base main \
  "로그인 실패 시 에러 메시지를 명확히 하고 관련 테스트를 보강해주세요"

# CLI 단축 명령 (동일)
harness --mode modify --use-headless-phases \
  --auto-pr --pr-base main \
  "로그인 실패 시 에러 메시지를 명확히 하고 관련 테스트를 보강해주세요"
```

이 한 줄이 수행하는 전체 흐름:

```text
1. 컨텍스트 수집 (diff, ADR, 컨벤션, 구조 규칙)
2. Planner → 수정 계획 생성
3. Phase별 구현 (docs-update → core-impl → integration → tests → validation)
4. Evaluator 평가 (ruff, mypy, pytest, 구조 검사)
5. ──── 여기까지가 기존 구현 단계 ────
6. git push → PR 생성
7. 리뷰 코멘트 수집 (CodeRabbit 등)
8. ACCEPT/DEFER/IGNORE 분류 → ACCEPT만 자동 반영
9. 반영 커밋 push → 리뷰 답글
```

리뷰 반영 후 자동 머지까지 하려면:

```bash
# Python 스크립트
python scripts/run_harness.py \
  --mode modify \
  --use-headless-phases \
  --auto-pr --pr-base main --pr-auto-merge \
  "결제 취소 플로우의 테스트를 보강해주세요"

# CLI 단축 명령 (동일)
harness --mode modify --use-headless-phases \
  --auto-pr --pr-base main --pr-auto-merge \
  "결제 취소 플로우의 테스트를 보강해주세요"
```

> **참고**: `--auto-pr`은 구현이 성공한 경우(통과한 스프린트가 1개 이상)에만 PR 파이프라인을 실행합니다. 구현이 실패하면 PR을 만들지 않고 구현 결과만 출력합니다.

문서 변경이 필요 없는 아주 작은 수정이라면 명시적으로 예외를 열 수 있습니다.

```bash
python scripts/run_harness.py \
  --mode modify \
  --use-headless-phases \
  --allow-empty-docs-diff \
  "타이포 하나를 수정해주세요"

# CLI 단축 명령 (동일)
harness --mode modify --use-headless-phases --allow-empty-docs-diff \
  "타이포 하나를 수정해주세요"
```

PR 파이프라인만 별도로 실행할 수도 있습니다.

```bash
python scripts/auto_pr_pipeline.py --base main

# CLI 단축 명령 (동일)
auto-pr-pipeline --base main
```

## 운영 시나리오

| 상황 | 스크립트 명령 | CLI 단축 명령 | 설명 |
|------|-------------|---------------|------|
| 옵션 확인 | `python scripts/run_harness.py --help` | `harness --help` | 사용 가능한 전체 옵션 출력 |
| 새 프로젝트 생성 | `python scripts/run_harness.py "..."` | `harness "..."` | `./project`에 새 프로젝트 생성 |
| 기존 코드 수정 | `python scripts/run_harness.py --mode modify "..."` | `harness --mode modify "..."` | 기존 Generator 경로로 수정 |
| 헤드리스 Phase 실행 | `python scripts/run_harness.py --mode modify --use-headless-phases "..."` | `harness --mode modify --use-headless-phases "..."` | 문서/Phase/독립 세션 중심 운영 |
| **구현→PR→리뷰 한 번에** | `... --auto-pr --pr-base main "..."` | `harness ... --auto-pr --pr-base main "..."` | **구현 성공 시 PR 자동화까지 연결** |
| 구현→PR→머지 한 번에 | `... --auto-pr --pr-base main --pr-auto-merge "..."` | `harness ... --auto-pr --pr-base main --pr-auto-merge "..."` | 리뷰 반영 후 자동 머지까지 |
| 문서 변경 없는 예외 작업 | `--allow-empty-docs-diff` 추가 | `harness ... --allow-empty-docs-diff "..."` | docs-diff 필수 정책을 예외 처리 |
| Phase 파일만 재실행 | `python scripts/run_phases.py --sprint 1 --require-docs-diff` | — | 이미 생성된 Phase 인덱스 기준 실행 |
| PR 생성/리뷰 반영 | `python scripts/auto_pr_pipeline.py --base main` | `auto-pr-pipeline --base main` | push, PR, 리뷰 수집, 반영, 답글 |
| 자동 머지까지 | `python scripts/auto_pr_pipeline.py --base main --auto-merge` | `auto-pr-pipeline --base main --auto-merge` | 리뷰 반영 후 PR merge |
| PR 본문 생성 | `python scripts/create_pr_body.py --base main` | `create-pr-body --base main` | diff 기반 PR 본문 자동 생성 |
| 중단 후 재개 | `python scripts/run_harness.py --resume` | `harness --resume` | 현재 디렉터리의 latest 체크포인트 재개 |

## 사용법

### 새 프로젝트 생성 (create 모드)

가장 기본적인 사용법입니다. 자연어로 만들고 싶은 프로젝트를 설명하면 됩니다.

```bash
python scripts/run_harness.py "브라우저에서 동작하는 간단한 ToDo 앱을 만들어주세요"

# CLI 단축 명령 (동일)
harness "브라우저에서 동작하는 간단한 ToDo 앱을 만들어주세요"
```

`--mode create`가 기본값이므로 생략할 수 있습니다. 출력 디렉터리를 지정하지 않으면 `./project`에 생성됩니다.

**출력 디렉터리 지정:**

```bash
python scripts/run_harness.py \
  --project-dir ./my-todo-app \
  "React와 FastAPI로 ToDo 앱을 만들어주세요"

harness --project-dir ./my-todo-app \
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

harness --project-dir ./my-app \
  --model claude-sonnet-4-6 \
  --max-sprints 10 --max-retries 5 \
  "실시간 채팅 앱을 만들어주세요"
```

**API 엔드포인트를 직접 지정:**

```bash
python scripts/run_harness.py \
  --api-endpoint "https://your-private-endpoint.example.com" \
  "브라우저에서 동작하는 간단한 ToDo 앱을 만들어주세요"

harness --api-endpoint "https://your-private-endpoint.example.com" \
  "브라우저에서 동작하는 간단한 ToDo 앱을 만들어주세요"
```

**상세 로그 출력:**

```bash
python scripts/run_harness.py -v "프로젝트 설명"

harness -v "프로젝트 설명"
```

### 기존 코드베이스 수정 (modify 모드)

기존 저장소를 수정하려면 저장소 루트에서 `--mode modify`를 사용합니다.

```bash
python scripts/run_harness.py \
  --mode modify \
  "로그인 실패 시 사용자에게 더 명확한 에러 메시지를 보여주세요"

# CLI 단축 명령 (동일)
harness --mode modify "로그인 실패 시 사용자에게 더 명확한 에러 메시지를 보여주세요"
```

modify 모드에서 `--project-dir`을 생략하면 현재 디렉터리가 수정 대상입니다. 다른 디렉터리를 수정하려면 명시적으로 지정합니다.

```bash
python scripts/run_harness.py \
  --mode modify \
  --project-dir ../my-existing-app \
  "결제 취소 플로우의 테스트를 보강하고 실패 케이스를 수정해주세요"

harness --mode modify --project-dir ../my-existing-app \
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
| ADR 목록 | `docs/adr/` + 정책의 `adr.external_sources` |
| 구조 규칙 | `harness_structure.yaml` |
| 최근 검증 요약 | `ruff`, `mypy` 실행 결과 |
| 프로젝트 정책 | `.harness/project-policy.yaml` (선택) |

Generator와 Evaluator도 modify 전용 시스템 프롬프트를 사용합니다. Generator는 새 프로젝트를 만들지 않고 기존 파일의 최소 변경에 집중하며, Evaluator는 변경 정확성과 기존 기능 보존을 더 강하게 봅니다.

**modify 모드 예시 — 작은 버그 수정:**

```bash
python scripts/run_harness.py \
  --mode modify \
  "체크포인트 재개 시 project-dir 기본값이 잘못 잡히는 문제를 수정하고 테스트를 추가해주세요"

harness --mode modify \
  "체크포인트 재개 시 project-dir 기본값이 잘못 잡히는 문제를 수정하고 테스트를 추가해주세요"
```

**modify 모드 예시 — worktree 격리와 함께:**

```bash
python scripts/run_harness.py \
  --mode modify \
  --use-worktree \
  --worktree-sync-exclude .pytest_cache \
  "리뷰 산출물 생성 로직의 에러 처리를 강화해주세요"

harness --mode modify --use-worktree \
  --worktree-sync-exclude .pytest_cache \
  "리뷰 산출물 생성 로직의 에러 처리를 강화해주세요"
```

### 중단된 실행 재개

중단된 실행은 최근 체크포인트 또는 특정 run_id로 재개할 수 있습니다. 체크포인트는 실행 대상 프로젝트의 `.harness/checkpoints/` 아래에 저장됩니다.

**최근 체크포인트에서 재개:**

```bash
# create 모드 프로젝트 재개 (프로젝트 디렉터리 명시)
python scripts/run_harness.py --project-dir ./project --resume
harness --project-dir ./project --resume

# modify 모드 프로젝트 재개 (현재 디렉터리에 체크포인트가 있을 때)
python scripts/run_harness.py --resume
harness --resume
```

**특정 run_id에서 재개:**

```bash
python scripts/run_harness.py --project-dir ./project --run-id abc123def456
harness --project-dir ./project --run-id abc123def456

python scripts/run_harness.py --run-id abc123def456
harness --run-id abc123def456
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

harness --use-worktree \
  --worktree-sync-exclude tmp \
  --worktree-sync-exclude cache \
  "만들고 싶은 프로젝트 설명"
```

동기화 규칙:
- 추가, 수정, 삭제를 모두 반영합니다.
- 같은 경로에 로컬 변경이 있으면 덮어쓰거나 삭제하지 않고 중단합니다.
- `--worktree-sync-exclude`로 지정한 경로는 동기화에서 제외됩니다 (반복 지정 가능).

### 헤드리스 Phase 실행

`--use-headless-phases`를 켜면 오케스트레이터가 기존 Generator 직접 구현 대신 `.harness/tasks/sprint-{N}/phase-*.md`를 `claude --print` 독립 세션으로 순차 실행합니다.

```bash
python scripts/run_harness.py \
  --mode modify \
  --use-headless-phases \
  "인증 오류 메시지 스펙을 문서화하고 구현과 테스트를 보강해주세요"

harness --mode modify --use-headless-phases \
  "인증 오류 메시지 스펙을 문서화하고 구현과 테스트를 보강해주세요"
```

운영 규칙:
- Phase 1은 문서 업데이트입니다.
- Phase 1 완료 직후 `.harness/tasks/sprint-{N}/docs-diff.md`가 재생성됩니다.
- 기본적으로 docs-diff가 비어 있으면 실패합니다.
- 문서 변경이 필요 없는 예외 작업은 `--allow-empty-docs-diff`를 명시합니다.
- 각 Phase는 다음 Phase를 위해 `.harness/tasks/sprint-{N}/{phase_id}-handoff.md`에 20줄 이내 요약을 남겨야 합니다.

Phase 파일에는 다음 정보가 들어갑니다.

| 항목 | 의미 |
|------|------|
| 스프린트 계약 | Generator/Evaluator가 합의한 작업 범위 |
| 입력 파일 | 계약 JSON, task-index, 이전 Phase 산출물, docs-diff |
| Docs Diff 참조 | Phase 1 이후 갱신되는 스펙 변경 요약 |
| 변경 허용 범위 | Phase가 수정해도 되는 경로 패턴 |
| 기대 산출물 | 해당 Phase가 끝났을 때 남겨야 할 결과 |
| 검증 방법 | 관련 테스트 또는 전체 품질 검사 명령 |
| 핸드오프 요구사항 | 다음 Phase가 볼 짧은 요약 파일 작성 지시 |

생성된 Phase 파일만 별도로 실행할 수도 있습니다.

```bash
python scripts/run_phases.py --sprint 1 --require-docs-diff
```

### PR 본문 생성

현재 브랜치의 변경 내용을 바탕으로 PR 본문을 자동 생성합니다.

```bash
# 표준 출력으로 출력
python scripts/create_pr_body.py --base main
create-pr-body --base main

# 파일로 저장
python scripts/create_pr_body.py --base main --output pr-body.md
create-pr-body --base main --output pr-body.md

# 브랜치명 오버라이드
python scripts/create_pr_body.py --base main --branch feature/my-feature
create-pr-body --base main --branch feature/my-feature

# worktree 격리 실행
python scripts/create_pr_body.py --base main --use-worktree
create-pr-body --base main --use-worktree

# PR 요약 텍스트 직접 지정
create-pr-body --base main --summary "인증 모듈 리팩터링" --output pr-body.md

# 다른 프로젝트 디렉터리 지정
create-pr-body --base main --project-dir ../my-app
```

### PR 자동화 파이프라인

현재 브랜치를 push하고 PR을 생성한 뒤, PR 리뷰 코멘트를 수집해 자동 반영 대상을 선별합니다.

```bash
python scripts/auto_pr_pipeline.py --base main

# CLI 단축 명령 (동일)
auto-pr-pipeline --base main
```

자동화 흐름:
- 현재 브랜치를 `origin`에 push합니다.
- 리뷰 산출물 기반 PR 본문을 생성하고 PR을 엽니다.
- PR 인라인 리뷰 코멘트를 수집합니다.
- 코멘트를 `ACCEPT`, `DEFER`, `IGNORE`로 분류합니다.
- `ACCEPT` 코멘트만 `claude --print` 반영 세션에 전달합니다.
- 판정 로그를 `.harness/review-artifacts/<branch>/review-comments.md`에 저장합니다.
- 반영 커밋을 push한 뒤 원본 리뷰 코멘트에 한국어 답글을 남깁니다.

자동 머지까지 수행하려면 다음 옵션을 사용합니다.

```bash
python scripts/auto_pr_pipeline.py --base main --auto-merge

# CLI 단축 명령 (동일)
auto-pr-pipeline --base main --auto-merge
```

GitHub review thread resolve는 REST API만으로 안정적으로 처리하기 어렵기 때문에, 현재 구현은 답글 기반 확인을 기본으로 합니다.

리뷰 코멘트 분류 기준은 다음과 같습니다.

| 판정 | 처리 | 예시 |
|------|------|------|
| `ACCEPT` | 자동 반영 세션에 전달 | bug, fix, missing, 오류, 누락, 파일/라인이 지정된 인라인 코멘트 |
| `DEFER` | 로그에 남기고 자동 반영하지 않음 | optional, nit, looks good, 칭찬성 코멘트 |
| `IGNORE` | 빈 댓글 등 처리 불가 항목 | 본문이 없는 코멘트 |

판정 결과는 `.harness/review-artifacts/<branch>/review-comments.md`에 저장됩니다.

### CodeRabbit 기반 자동 PR 검증

CodeRabbit은 하네스 내부 컴포넌트가 아니라 GitHub PR에 연결되는 외부 리뷰어입니다. 하네스의 역할은 CodeRabbit이 남긴 PR 인라인 리뷰 코멘트를 수집하고, 자동 반영 가능한 항목만 선별해 후속 작업을 수행하는 것입니다.

전제 조건:
- 저장소에 CodeRabbit GitHub App이 설치되어 있어야 합니다.
- CodeRabbit이 PR 리뷰 코멘트를 남길 수 있어야 합니다.
- 로컬 또는 실행 환경에 `gh` CLI 인증이 되어 있어야 합니다.
- 현재 브랜치가 push 가능한 원격 브랜치여야 합니다.
- 리뷰 반영에는 `claude --print` CLI가 필요합니다.

권장 흐름:

```bash
# 1. 하네스 또는 수동 작업으로 변경 생성
python scripts/run_harness.py --mode modify --use-headless-phases "수정 요청"
harness --mode modify --use-headless-phases "수정 요청"

# 2. PR 생성 + CodeRabbit 리뷰 수집 + 반영
python scripts/auto_pr_pipeline.py --base main
auto-pr-pipeline --base main

# 3. 리뷰 반영 후 자동 머지까지 원하면
python scripts/auto_pr_pipeline.py --base main --auto-merge
auto-pr-pipeline --base main --auto-merge
```

상세 동작:

```text
auto_pr_pipeline.py
  -> git branch --show-current
  -> git push -u origin <current-branch>
  -> gh pr create
  -> CodeRabbit이 PR에 리뷰 코멘트 작성
  -> gh api repos/{owner}/{repo}/pulls/{pr_number}/comments
  -> 리뷰 코멘트 수집
  -> ACCEPT / DEFER / IGNORE 분류
  -> ACCEPT만 claude --print에 전달
  -> git add -A
  -> git commit -m "fix: apply review comments"
  -> git push
  -> 원본 리뷰 코멘트에 한국어 답글
  -> --auto-merge가 있으면 gh pr merge
```

CodeRabbit 코멘트 처리 기준:

| CodeRabbit 코멘트 유형 | 하네스 판정 | 이후 동작 |
|------------------------|-------------|-----------|
| 버그, 실패, 누락, 보안, 잘못된 동작 지적 | `ACCEPT` | headless 반영 세션에 전달 |
| 파일/라인이 지정된 인라인 코멘트 | `ACCEPT` | 기본적으로 반영 대상으로 처리 |
| optional, nit, looks good, 칭찬성 코멘트 | `DEFER` | 로그만 남기고 자동 반영하지 않음 |
| 빈 코멘트 또는 처리 불가 코멘트 | `IGNORE` | 로그만 남김 |

결과 산출물:
- `.harness/review-artifacts/<branch>/review-comments.md`: ACCEPT/DEFER/IGNORE 판정 로그
- `fix: apply review comments` 커밋: ACCEPT 코멘트 반영 결과
- PR 리뷰 코멘트 답글: “자동 리뷰 반영 파이프라인에서 반영했다”는 한국어 응답

현재 한계:
- GitHub REST API만으로 CodeRabbit review thread resolve를 안정적으로 닫기 어렵습니다.
- 따라서 현재 구현은 “반영 답글 작성”을 기본 확인 방식으로 사용합니다.
- GraphQL review thread id를 별도로 수집하는 기능을 추가하면 resolve 자동화까지 확장할 수 있습니다.

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

### 도움말 확인 (`--help`)

모든 CLI 명령에 `--help`를 붙이면 사용 가능한 옵션과 설명을 출력합니다.

```bash
harness --help
auto-pr-pipeline --help
create-pr-body --help

# Python 스크립트로도 동일하게 동작
python scripts/run_harness.py --help
python scripts/auto_pr_pipeline.py --help
python scripts/create_pr_body.py --help
```

### run_harness.py / harness

```
python scripts/run_harness.py [OPTIONS] [PROMPT]
harness [OPTIONS] [PROMPT]
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
| `--use-headless-phases` | `false` | 스프린트 구현을 Phase별 `claude --print` 독립 세션으로 실행 |
| `--headless-phase-timeout` | `600` | 헤드리스 Phase당 타임아웃(초) |
| `--allow-empty-docs-diff` | `false` | 헤드리스 실행에서 docs-update 이후 docs-diff가 비어 있어도 계속 진행 |
| `--auto-pr` | `false` | 구현 성공 후 PR 자동화 파이프라인(push→PR→리뷰 반영)을 이어서 실행 |
| `--pr-base` | `main` | PR 대상 브랜치 (`--auto-pr` 사용 시) |
| `--pr-skip-review` | `false` | PR 생성 후 리뷰 수집/반영 건너뛰기 (`--auto-pr` 사용 시) |
| `--pr-auto-merge` | `false` | 리뷰 반영 후 PR 자동 머지 (`--auto-pr` 사용 시) |
| `-v`, `--verbose` | `false` | 상세 로그 출력 |

### auto_pr_pipeline.py / auto-pr-pipeline

```
python scripts/auto_pr_pipeline.py [OPTIONS]
auto-pr-pipeline [OPTIONS]
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--base` | `main` | PR 기준 브랜치 |
| `--project-dir` | `.` | 프로젝트 루트 디렉터리 |
| `--title` | `""` | PR 제목. 미지정 시 현재 브랜치명 기반 생성 |
| `--skip-review` | `false` | 리뷰 수집/반영 단계 건너뛰기 |
| `--auto-merge` | `false` | 리뷰 반영 후 PR 자동 머지 |
| `--no-poll` | `false` | 리뷰 댓글 대기 폴링 비활성화 |
| `-v`, `--verbose` | `false` | 상세 로그 출력 |

### create_pr_body.py / create-pr-body

```
python scripts/create_pr_body.py [OPTIONS]
create-pr-body [OPTIONS]
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

정책 파일은 하네스가 “이 저장소에서는 어떤 문서를 기준으로 보고, 어떤 검사를 필수로 보고, 어떤 산출물을 만들지”를 결정하는 얇은 설정 파일입니다. create 모드보다 modify 모드에서 특히 중요합니다.

### 정책 파일 위치와 기본값

기본 위치:

```text
.harness/project-policy.yaml
```

정책 파일이 없으면 다음 기본 정책을 사용합니다.

| 항목 | 기본값 | 의미 |
|------|--------|------|
| `review_language` | `ko` | 리뷰, PR 답글, 판단 로그 언어 |
| `required_checks` | `ruff`, `mypy`, `pytest`, `structure` | 필수 품질 검사 |
| `conventions.source` | `docs/code-convention.yaml` | 코드 컨벤션 파일 |
| `adr.directory` | `docs/adr/` | ADR 디렉터리 |
| `adr.external_sources` | `[]` | 외부 프로젝트 ADR 디렉터리 경로 목록 (절대 경로 또는 `~` 확장 경로) |
| `structure.source` | `harness_structure.yaml` | 구조 분석 규칙 파일 |
| `artifacts.design_intent` | `true` | 설계 의도 산출물 생성 여부 |
| `artifacts.code_quality_guide` | `true` | 평가 기준 산출물 생성 여부 |
| `artifacts.review_comments` | `true` | 리뷰 판단 로그 생성 여부 |
| `artifacts.pr_body` | `true` | PR 본문 생성 여부 |

정책 파일 파싱에 실패하거나 최상위 값이 YAML mapping이 아니면 경고를 남기고 기본 정책으로 폴백합니다. 저장은 atomic write로 수행되어 쓰기 중 실패해도 기존 파일 손상을 줄입니다.

### 정책 파일 예시

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
    external_sources:
      - /path/to/shared-project/docs/adr
  structure:
    source: harness_structure.yaml
  artifacts:
    design_intent: true
    code_quality_guide: true
    review_comments: true
    pr_body: true
  custom_rules:
    max_complexity: 10
    test_policy: "변경된 public API는 반드시 테스트를 추가한다"
```

필드 설명:

| 필드 | 설명 |
|------|------|
| `project.name` | 프로젝트 표시 이름 |
| `project.language` | 주요 언어. 예: `python`, `typescript` |
| `project.python_version` | Python 프로젝트일 때 기준 버전 |
| `policies.review_language` | 리뷰/PR 답글 언어. 현재 기본 정책은 한국어 |
| `policies.required_checks` | 이 프로젝트에서 반드시 통과해야 하는 검사 목록 |
| `policies.conventions.source` | 컨벤션 YAML 경로 |
| `policies.adr.directory` | ADR 문서 디렉터리 |
| `policies.adr.external_sources` | 외부 프로젝트 ADR 디렉터리 절대 경로 목록. 경로가 없거나 디렉터리가 아니면 건너뜀 |
| `policies.structure.source` | 구조 규칙 YAML 경로 |
| `policies.artifacts` | 산출물 생성 여부 |
| `policies.custom_rules` | 프로젝트별 자유 규칙. Planner 컨텍스트에 포함되어 판단 기준으로 사용 |

### 정책 적용 시점

정책 파일은 다음 흐름에서 사용됩니다.

```text
run_harness.py --mode modify
  -> ProjectPolicyManager.load()
  -> ModifyContextCollector.collect(policy=policy)
  -> Planner에게 프로젝트 컨텍스트로 전달
  -> ContextFilter / CriteriaGenerator가 ADR, 컨벤션 기준 구성
  -> Evaluator가 criteria_md와 필수 검사 기준 참고
```

구체적으로는 다음 영향을 줍니다.

- Planner는 정책에 적힌 리뷰 언어, 필수 검사, 문서 경로, custom_rules를 참고해 수정 계획을 세웁니다.
- ModifyContextCollector는 정책 경로를 기준으로 컨벤션/ADR/구조 규칙을 수집합니다. `adr.external_sources`가 있으면 외부 ADR도 함께 로드합니다.
- Evaluator는 생성된 `code-quality-guide.md`와 필수 검사 기준을 품질 판단에 사용합니다.
- PR 자동화와 리뷰 답글은 `review_language` 정책과 저장소의 리뷰 정책에 맞춰 한국어를 기본으로 사용합니다.

### 프로젝트별 운영 패턴

새 프로젝트에 정책 파일을 처음 만들 때:

```python
from pathlib import Path
from harness.context.project_policy import ProjectPolicyManager

mgr = ProjectPolicyManager(Path("."))
mgr.init_default(project_name="my-service", language="python")
```

직접 작성할 때는 최소한 다음만 두어도 됩니다.

```yaml
project:
  name: my-service
  language: python
policies:
  review_language: ko
  required_checks:
    - ruff
    - mypy
    - pytest
    - structure
```

여러 프로젝트를 운영할 때 권장 방식:

| 프로젝트 유형 | 정책 설정 포인트 |
|---------------|------------------|
| Python 라이브러리 | `python_version`, `required_checks`, `docs/code-convention.yaml` 유지 |
| 프론트엔드 앱 | `language: typescript`, custom_rules에 UI/접근성/빌드 규칙 추가 |
| 백엔드 서비스 | custom_rules에 마이그레이션, API 호환성, 로그 정책 추가 |
| 레거시 프로젝트 | `required_checks`를 현재 가능한 수준으로 좁히고 점진적으로 강화 |
| 문서 중심 프로젝트 | artifacts와 docs-diff 정책을 강화 |
| 공유 ADR 참조 프로젝트 | `adr.external_sources`에 공유 ADR 디렉터리 경로 추가 |

주의사항:
- 정책 파일은 저장소에 커밋하는 것을 권장합니다.
- 비밀값, 토큰, 개인 계정 정보는 넣지 않습니다.
- 정책 파일은 “검사 명령 자체”를 실행하는 스크립트가 아니라, 에이전트와 하네스가 참고하는 프로젝트별 기준입니다.
- 정책을 바꾼 뒤에는 `python3 scripts/check_structure.py`와 전체 테스트를 실행해 문서/구조 규칙과 어긋나지 않는지 확인합니다.

## 동작 방식

### create/modify 공통 실행 흐름

```text
사용자 프롬프트
  -> create: Planner가 제품 스펙과 스프린트 계획 작성
  -> modify: 현재 프로젝트 컨텍스트 수집 후 Planner가 수정 계획 작성
  -> Generator와 Evaluator가 스프린트 계약 협의
  -> docs-diff, 설계 의도, 작업 관련 평가 기준, Phase 계약 생성
  -> Generator가 스프린트 결과 생성
     또는 --use-headless-phases: phase-01-docs-update -> docs-diff 갱신 -> phase-02..N 독립 실행
  -> Evaluator가 결과 평가
  -> 실패 시 피드백을 반영해 재시도 (최대 max-retries)
  -> 모든 스프린트 결과와 요약 산출
```

### End-to-End 흐름 (`--auto-pr`)

`--auto-pr`을 사용하면 구현과 PR 자동화가 하나의 실행으로 이어집니다.

```text
run_harness.py --auto-pr --pr-base main
  ┌─ 구현 단계 ──────────────────────────────────────────┐
  │ 1. 컨텍스트 수집 (diff, ADR, 컨벤션, 구조 규칙)     │
  │ 2. Planner → 스펙, 스프린트 계획                     │
  │ 3. Generator/Phase Worker → 구현                     │
  │ 4. Evaluator → 평가 (실패 시 재시도)                 │
  └──────────────────────────────────────────────────────┘
                        │ 통과한 스프린트 ≥ 1
                        ▼
  ┌─ PR 자동화 단계 ─────────────────────────────────────┐
  │ 5. git push -u origin <branch>                       │
  │ 6. gh pr create (PR 본문 자동 생성)                  │
  │ 7. 리뷰 코멘트 수집 (CodeRabbit 등)                  │
  │ 8. ACCEPT/DEFER/IGNORE 분류 → ACCEPT만 반영          │
  │ 9. 반영 커밋 push → 한국어 답글                      │
  │10. --pr-auto-merge → gh pr merge                     │
  └──────────────────────────────────────────────────────┘
```

구현 단계에서 통과한 스프린트가 0개이면 PR 자동화를 건너뜁니다. PR 자동화가 실패해도 구현 결과는 보존됩니다.

### 헤드리스 Phase 내부 흐름

```text
HarnessOrchestrator
  -> SprintContract 저장
  -> design-intent-sprint<N>.md 생성
  -> code-quality-guide-sprint<N>.md 생성
  -> task-index.json + phase-*.md 생성
  -> scripts/run_phases.py 호출
      -> phase-01-docs-update 실행
      -> docs-diff.md 재생성
      -> phase-02-core-impl 실행
      -> phase-03-integration 실행
      -> phase-04-tests 실행
      -> phase-05-validation 실행
  -> Evaluator 평가
```

재시도 시에는 완료되지 않은 Phase 상태만 `pending`으로 되돌립니다. 이미 `done`인 Phase는 다시 실행하지 않습니다.

### docs-diff 생성 방식

`DocsDiffGenerator`는 `docs/` 경로를 기준으로 다음 변경을 수집합니다.

- `git diff --unified=0 -- docs/`의 추가/삭제 라인
- 아직 git에 추가되지 않은 untracked 문서 파일
- 삭제된 문서의 제거 라인

결과는 Markdown으로 저장되며, 각 Phase는 전체 문서 대신 이 변경 요약을 우선 참고합니다. 이 설계는 긴 스펙 문서를 반복 주입하지 않고도 “이번 작업에서 바뀐 의도”를 선명하게 전달하기 위한 것입니다.

### 유사 RAG 컨텍스트 필터링

`ContextFilter`는 작업 설명에서 키워드를 추출하고, ADR/컨벤션 문서에서 관련도가 높은 항목만 골라 `code-quality-guide.md`에 합칩니다.

```text
작업 목표
  -> 키워드 추출
  -> ADR 제목/본문 점수화
  -> code-convention.yaml 태그/카테고리 점수화
  -> 관련 기준만 Markdown으로 압축
```

이 문서는 구현 에이전트와 Evaluator가 같은 기준을 보도록 하기 위한 공유 컨텍스트입니다.

### PR 자동화 내부 흐름

```text
auto_pr_pipeline.py
  -> 현재 브랜치 push
  -> PR 본문 생성 후 gh pr create
  -> gh api로 PR 인라인 리뷰 코멘트 수집
  -> ACCEPT / DEFER / IGNORE 분류
  -> review-comments.md 저장
  -> ACCEPT 코멘트만 claude --print 반영 세션에 전달
  -> git add/commit/push
  -> 원본 리뷰 코멘트에 한국어 답글
  -> --auto-merge가 있으면 gh pr merge
```

자동 반영이 실패하면 커밋과 답글을 만들지 않고 오류를 결과에 기록합니다.

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
│   │   └── orchestrator.py     #   HarnessOrchestrator (스프린트 루프, 체크포인트, worktree, Phase 실행)
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
│   │   ├── criteria.py         #   CriteriaGenerator
│   │   ├── intent.py           #   IntentGenerator (설계 의도)
│   │   ├── reflection.py       #   ReviewReflection (리뷰 반영 판단)
│   │   ├── pr_body.py          #   PRBodyGenerator
│   │   ├── pipeline_integration.py # 리뷰 파이프라인 헬퍼
│   │   ├── docs_diff.py        #   DocsDiffGenerator (문서 변경 줄 단위 추적)
│   │   ├── session_fork.py     #   SessionForkManager (설계 의도 문서화)
│   │   └── worktree.py         #   WorktreeManager (git worktree 격리)
│   ├── guides/                 # 가이드 레지스트리
│   │   ├── registry.py         #   GuideRegistry (시스템 프롬프트, ADR/컨벤션 컨텍스트)
│   │   ├── context_filter.py   #   ADR/컨벤션 유사 RAG 필터
│   │   └── prompts.py          #   create/modify 모드별 시스템 프롬프트
│   ├── contracts/              # 스프린트 계약
│   │   ├── models.py           #   SprintContract, AcceptanceCriterion
│   │   └── store.py            #   ContractStore (JSON 저장)
│   ├── context/                # 세션/프로젝트 컨텍스트
│   │   ├── checkpoint.py       #   CheckpointStore, SessionState, Phase
│   │   ├── modify_context.py   #   ModifyContextCollector
│   │   ├── phase_manager.py    #   PhaseDefinition, TaskIndex, Phase 프롬프트 생성
│   │   └── project_policy.py   #   ProjectPolicyManager
│   └── tools/                  # 유틸리티 도구
│       ├── api_client.py       #   HarnessClient (Claude API HTTP 클라이언트)
│       ├── shell.py            #   run_command_safe, validate_command, validate_path
│       ├── file_io.py          #   atomic_write_text
│       ├── path_safety.py      #   sanitize_branch_name, validate_run_id
│       ├── adr.py              #   ADRLoader (ADR 로드·필터링)
│       └── json_types.py       #   타입 변환 유틸리티
├── scripts/                    # CLI 스크립트
│   ├── run_harness.py          #   메인 하네스 실행 (create/modify/resume)
│   ├── create_pr_body.py       #   PR 본문 생성
│   ├── run_phases.py           #   Phase별 claude --print 실행
│   ├── auto_pr_pipeline.py     #   push→PR→리뷰 반영→머지 자동화
│   ├── check_structure.py      #   구조 규칙 검사
│   └── pr_review.py            #   GitHub Actions PR AI 리뷰
├── tests/                      # 테스트
├── docs/
│   ├── adr/                    # Architecture Decision Records (0001~0009)
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
├── review-artifacts/<branch>/
│   ├── design-intent.md              # 설계 의도
│   ├── code-quality-guide.md         # 평가 기준
│   ├── pr-body.md                    # PR 본문
│   ├── review-comments.md            # 리뷰 반영 판단 로그
│   └── docs-diff-sprint<N>.md        # 스프린트별 문서 변경 요약
├── tasks/
│   └── sprint-<N>/
│       ├── task-index.json           # Phase 인덱스와 상태
│       ├── phase-*.md                # 자기 완결 Phase 프롬프트
│       ├── docs-diff.md              # docs-update 이후 갱신되는 런타임 docs-diff
│       └── phase-*-handoff.md        # Phase 간 핸드오프 요약
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

### Phase 계약 생성

```python
from pathlib import Path
from harness.context.phase_manager import PhaseManager

mgr = PhaseManager(Path("."))
index = mgr.create_phases(1, "인증 오류 메시지 개선")
mgr.save_task_index(index)
for phase in index.phases:
    prompt = mgr.build_phase_prompt(phase, sprint_contract="계약 내용")
    mgr.save_phase_prompt(1, phase, prompt)
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
- 헤드리스 Phase 실행은 docs-update를 첫 단계로 두고, 이후 Phase가 런타임 docs-diff와 핸드오프 요약을 참조하게 합니다 (ADR-0009).

## 라이선스

내부 프레임워크입니다.
