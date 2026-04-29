# Python Harness Framework

Python Harness Framework는 AI 코딩 에이전트가 프로젝트를 스프린트 단위로 만들고 검증하도록 돕는 하네스 엔지니어링 프레임워크입니다.

사용자는 만들고 싶은 제품을 자연어로 설명하고, 하네스는 그 설명을 실행 가능한 계획으로 바꾼 뒤 코드 생성, 품질 검사, 평가, 리뷰 산출물 생성을 하나의 흐름으로 묶어 실행합니다.

## 하네스가 하는 일

하네스는 세 가지 역할의 에이전트를 중심으로 동작합니다.

- `Planner`: 사용자 프롬프트를 제품 스펙과 스프린트 계획으로 변환합니다.
- `Generator`: 각 스프린트의 목표에 따라 프로젝트 파일을 작성하고 필요한 명령을 실행합니다.
- `Evaluator`: 생성된 결과가 계약, 품질 기준, 테스트 조건을 만족하는지 평가합니다.

이 흐름 위에 Ruff, mypy, pytest, 구조 규칙 검사, AI 코드 리뷰를 센서처럼 연결해 빠른 검증부터 의미 기반 리뷰까지 단계적으로 수행합니다.

## 현재 기능 표

| 영역 | 현재 상태 | 구현 위치 |
|------|-----------|-----------|
| 3-에이전트 실행 | Planner, Generator, Evaluator, Orchestrator 스프린트 루프 | `harness/agents/` |
| 연산적 센서 | Ruff, mypy, pytest, 구조 규칙 검사 | `harness/sensors/computational/`, `harness/pipeline/` |
| AI 코드 리뷰 | 현재 브랜치 diff 기반 리뷰, 평가 기준 포함 리뷰 | `harness/sensors/inferential/code_reviewer.py`, `scripts/pr_review.py` |
| 리뷰 산출물 | 설계 의도, 평가 기준, PR 본문, 리뷰 반영 판단 로그 | `harness/review/` |
| worktree 안전화 | 임시 git worktree 격리 실행, 로컬 변경 충돌 감지, 생성 실패 시 fallback 금지 | `harness/review/worktree.py`, `harness/agents/orchestrator.py` |
| 구조화 계약 | raw 계약 보존, 기능·검증 기준 최선 노력 파싱, JSON 저장 | `harness/contracts/` |
| 체크포인트 | 실행 상태 저장, latest 포인터, `--resume`/`--run-id` 재개 | `harness/context/checkpoint.py`, `scripts/run_harness.py` |
| 가이드 레지스트리 | 에이전트 시스템 프롬프트 조회, 필요 시 ADR/컨벤션 컨텍스트 조립 | `harness/guides/` |
| 구조 규칙 | ADR 연계 의존성·필수 파일·금지 패턴 검사 | `harness_structure.yaml`, `scripts/check_structure.py` |

## 빠른 시작

```bash
git clone <repo-url>
cd python-harness

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

AI 호출이 필요한 기능을 사용하려면 엔드포인트를 환경변수로 주입합니다. 실제 엔드포인트 값은 저장소에 커밋하지 않고 로컬 셸, CI secret, 배포 환경에서만 설정합니다.

```bash
export HARNESS_API_ENDPOINT="https://your-private-endpoint.example.com"
```

환경변수 대신 실행 시 직접 넘길 수도 있습니다.

```bash
python scripts/run_harness.py \
  --api-endpoint "https://your-private-endpoint.example.com" \
  "브라우저에서 동작하는 간단한 ToDo 앱을 만들어주세요"
```

## 하네스 실행

```bash
python scripts/run_harness.py "브라우저에서 동작하는 간단한 ToDo 앱을 만들어주세요"
```

출력 디렉터리를 지정할 수 있습니다.

```bash
python scripts/run_harness.py \
  --project-dir ./my-todo-app \
  "React와 FastAPI로 ToDo 앱을 만들어주세요"
```

자주 쓰는 옵션은 다음과 같습니다.

```bash
python scripts/run_harness.py \
  --project-dir ./project \
  --model claude-sonnet-4-6 \
  --max-retries 3 \
  --max-sprints 15 \
  "만들고 싶은 프로젝트 설명"
```

worktree 격리 실행을 켜면 스프린트 구현 시도를 임시 git worktree에서 수행한 뒤
변경된 파일만 메인 프로젝트로 동기화합니다. 동기화는 추가·수정·삭제를 반영하되,
같은 경로에 로컬 변경이 있으면 덮어쓰거나 삭제하지 않고 중단합니다.

```bash
python scripts/run_harness.py \
  --project-dir ./project \
  --use-worktree \
  --worktree-sync-exclude tmp \
  --worktree-sync-exclude cache \
  "만들고 싶은 프로젝트 설명"
```

중단된 실행은 최근 체크포인트 또는 특정 run_id로 재개할 수 있습니다.

```bash
python scripts/run_harness.py --project-dir ./project --resume
python scripts/run_harness.py --project-dir ./project --run-id abc123def456
```

### `scripts/run_harness.py` 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `prompt` | `""` | 프로젝트 설명. 새 실행에는 필요하며, 재개 시에는 생략할 수 있습니다. |
| `--project-dir` | `./project` | 생성·검증 대상 프로젝트 디렉터리 |
| `--model` | `claude-sonnet-4-6` | Planner/Generator/Evaluator가 사용할 모델명 |
| `--api-endpoint` | `$HARNESS_API_ENDPOINT` | API 엔드포인트. 지정하면 환경변수를 덮어씁니다. |
| `--max-retries` | `3` | 스프린트당 최대 구현 재시도 횟수 |
| `--max-sprints` | `15` | 실행할 최대 스프린트 수 |
| `--app-url` | `http://localhost:3000` | Evaluator가 확인할 앱 URL |
| `--no-context-reset` | `false` | 재시도 사이 Generator 컨텍스트 리셋을 비활성화 |
| `--run-id` | `""` | 지정한 체크포인트 run_id에서 재개 |
| `--resume` | `false` | `.harness/checkpoints/latest.json`이 가리키는 실행 재개 |
| `--use-worktree` | `false` | 스프린트 구현을 임시 git worktree에서 격리 실행. 로컬 변경 충돌 시 동기화 중단 |
| `--worktree-sync-exclude` | `[]` | worktree 결과 동기화에서 제외할 파일/디렉터리명. 반복 지정 가능 |
| `-v`, `--verbose` | `false` | 상세 로그 출력 |

## 동작 방식

```text
사용자 프롬프트
  -> Planner가 제품 스펙과 스프린트 계획 작성
  -> Generator와 Evaluator가 스프린트 계약 협의
  -> Generator가 스프린트 결과 생성
  -> Evaluator가 결과 평가
  -> 실패 시 피드백을 반영해 재시도
  -> 모든 스프린트 결과와 요약 산출
```

품질 검사는 빠르고 결정적인 검사부터 실행됩니다.

```text
ruff
  -> mypy
  -> 구조 규칙 검사
  -> pytest
  -> AI 코드 리뷰
```

이 순서는 명확한 오류를 먼저 잡아내고, 비용이 큰 AI 리뷰는 필요한 시점에만 사용하기 위한 것입니다.

## 주요 명령

품질 검사는 로컬에서 다음 명령으로 실행할 수 있습니다.

```bash
ruff check .
mypy harness
pytest
python scripts/check_structure.py
```

현재 브랜치의 변경 내용을 바탕으로 PR 본문을 만들 수 있습니다.

```bash
python scripts/create_pr_body.py --base main
python scripts/create_pr_body.py --base main --output pr-body.md
```

## 주요 API 사용법

```python
from pathlib import Path
from harness.review.criteria import CriteriaGenerator

gen = CriteriaGenerator(Path("."))
criteria = gen.generate(task_description="인증 모듈 리팩터링")
md = gen.to_markdown(criteria)  # list[EvalCriterion]을 마크다운으로 변환
```

```python
from pathlib import Path
from harness.review.worktree import WorktreeManager

mgr = WorktreeManager(Path("."))

def my_task(work_dir: Path) -> list[Path]:
    """콜백은 worktree 경로를 받고, 생성된 산출물 경로 list[Path]를 반환한다."""
    output = work_dir / "result.md"
    output.write_text("# Result", encoding="utf-8")
    return [output]

mgr.run_isolated(my_task, preserve_to=Path(".harness/review-artifacts/my-branch"))
```

## 산출물

하네스 실행 중 생성되는 주요 산출물은 프로젝트 디렉터리 아래에 저장됩니다.

```text
.harness/artifacts/
  spec.json
  summary.json
  sprint_<number>_contract.md

.harness/review-artifacts/<branch>/
  design-intent.md
  code-quality-guide.md
  pr-body.md
  review-comments.md

.harness/contracts/
  sprint_<number>.json

.harness/checkpoints/
  <run_id>.json
  latest.json
```

이 산출물은 스프린트의 의도, 평가 기준, PR 설명, 리뷰 반영 판단을 추적하기 위한 기록입니다.

## 환경변수

| 이름 | 설명 |
|------|------|
| `HARNESS_API_ENDPOINT` | Planner, Generator, Evaluator, AI 리뷰가 호출할 비공개 API 엔드포인트 |

`HARNESS_API_ENDPOINT`가 설정되지 않은 상태에서 AI 호출이 필요한 기능을 실행하면 하네스는 명확한 설정 오류를 반환합니다.

GitHub Actions에서 AI 리뷰를 사용하려면 저장소 secret에 `HARNESS_API_ENDPOINT`를 등록합니다. Secret이 없으면 AI 리뷰 job은 실패하지 않고 리뷰 단계를 건너뜁니다.

## 아키텍처 원칙

- 센서는 에이전트에 의존하지 않습니다.
- 빠른 결정론적 검사를 먼저 실행하고, AI 리뷰는 뒤에서 보조합니다.
- 중요한 아키텍처 결정은 ADR로 남깁니다.
- ADR은 기본적으로 결정 기록과 구조 검증의 기준입니다. 모든 ADR 원문을 에이전트 런타임 프롬프트에 자동 주입하지는 않으며, 필요한 경우 `GuideRegistry.build_context()`로 컨텍스트를 조립해 사용할 수 있습니다.
- 모든 public 함수는 타입 힌트를 갖습니다.

## 라이선스

내부 프레임워크입니다.
