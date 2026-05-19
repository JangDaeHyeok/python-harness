# Python Harness Framework

AI 코딩 에이전트를 위한 **하네스(harness) 엔지니어링 프레임워크**.

사용자가 자연어로 만들고 싶은 것 또는 고치고 싶은 것을 설명하면, 3-에이전트(Planner / Generator / Evaluator)가 **계약 기반 스프린트 루프**로 코드를 작성·검사·평가하고, 결정적 센서(ruff·mypy·pytest·구조 검사)와 AI 코드 리뷰를 거쳐 PR 생성·리뷰 반영·머지까지 한 흐름으로 연결한다.

> "모델은 점점 좋아지지만, 코딩 에이전트의 성능은 **모델 주변의 하네스**에 더 많이 좌우된다." — 이 프로젝트는 그 명제를 자기 자신에도 적용한다 (`.claude/` 셋업, 서브패키지 CLAUDE.md, hooks, skills).

---

## 목차

- [핵심 가치](#핵심-가치)
- [요구 사항 / 설치](#요구-사항--설치)
- [환경변수](#환경변수)
- [5분 안에 써보기](#5분-안에-써보기)
- [End-to-End: 구현 → PR → 리뷰 → 머지](#end-to-end-구현--pr--리뷰--머지)
- [핵심 개념](#핵심-개념)
- [Claude Code 하네스 레이어 (자기 도그푸딩)](#claude-code-하네스-레이어-자기-도그푸딩)
- [Claude Code에서 사용하기](#claude-code에서-사용하기)
- [CLI 빠른 참조](#cli-빠른-참조)
- [트러블슈팅](#트러블슈팅)
- [프로젝트 구조](#프로젝트-구조)
- [산출물 경로](#산출물-경로)
- [프로젝트 정책 파일](#프로젝트-정책-파일)
- [품질 기준 / 검증](#품질-기준--검증)
- [ADR 목록](#adr-목록)
- [CI/CD](#cicd)
- [라이선스](#라이선스)

---

## 핵심 가치

| 축 | 무엇을 하는가 |
|----|-------------|
| **3-에이전트 루프** | Planner → Generator → Evaluator. 계약(`SprintContract`)을 협상하고 스프린트 단위로 진행 (ADR-0001, ADR-0005). |
| **결정적 센서 우선** | ruff → mypy → 구조분석 → pytest를 먼저 실행하고, AI 코드 리뷰는 보조로 이어진다 (ADR-0002). |
| **modify 모드 + 프로젝트 정책** | 기존 코드베이스의 diff / ADR / 컨벤션 / 구조 / 정책을 Planner 컨텍스트에 주입, 최소 변경 원칙 (ADR-0008). |
| **헤드리스 Phase + docs-diff** | 첫 Phase에서 문서를 갱신하고 `docs-diff.md`를 생성한 뒤, 이후 Phase가 컨텍스트 격리된 `claude --print` 세션으로 순차 실행된다 (ADR-0009). |
| **PR 자동화** | push → PR → 코멘트 수집 → ACCEPT/DEFER/IGNORE 분류 → ACCEPT만 반영 → 한국어 답글 → 선택적 머지. CodeRabbit 코멘트도 동일 흐름. |
| **부트스트랩(harness-init)** | 외부 프로젝트에 ADR/컨벤션/구조/정책/CLAUDE.md와 `.claude` 팀 설정·Stop 훅을 일괄 배치. LLM이 자연어 의도로 보강. |
| **자기 도그푸딩** | 본 저장소 스스로 hooks·skills·서브패키지 CLAUDE.md를 적용. CRITICAL 규칙은 모델 기억력이 아니라 hook으로 강제된다. |

---

## 요구 사항 / 설치

- Python 3.11 이상
- Git (worktree 격리·diff 기반 기능에 사실상 필수)
- (선택) `gh` CLI — PR 자동화 / CodeRabbit 연동 시. 사전에 `gh auth login` 인증 필요.

```bash
git clone <repo-url>
cd python-harness
python3 -m venv .venv && source .venv/bin/activate

pip install -e ".[dev]"     # 개발 의존성 포함 (ruff, mypy, pytest, types-PyYAML)
```

`pip install -e .` 후 다음 4개 CLI가 등록된다:

| CLI | 대응 스크립트 | 용도 |
|-----|---------------|------|
| `harness` | `scripts/run_harness.py` | 메인 실행 (create/modify/resume) |
| `auto-pr-pipeline` | `scripts/auto_pr_pipeline.py` | PR 자동화 파이프라인 |
| `create-pr-body` | `scripts/create_pr_body.py` | PR 본문 생성 |
| `harness-init` | `scripts/init_harness.py` | 신규 프로젝트 부트스트랩 |

---

## 환경변수

| 이름 | 설명 | 필수 |
|------|------|-----|
| `HARNESS_API_ENDPOINT` | Planner / Generator / Evaluator / AI 리뷰가 호출할 비공개 API 엔드포인트 | AI 호출 시 필수 |
| `CLAUDE_HOOK_SKIP` | `1`로 설정 시 Stop hook(`.claude/hooks/post_session_checks.sh`)을 우회 (CI/임시 디버깅용) | 선택 |

`HARNESS_API_ENDPOINT`를 환경변수로 두는 대신 실행 시 `--api-endpoint`로 직접 넘길 수도 있다. 토큰·비밀값을 커밋하지 않는다.

---

## 5분 안에 써보기

### 케이스 A — 신규 프로젝트에 하네스 셋업 한 번에 배치

```bash
harness-init --offline "사내 청구 자동화 도구. Python 3.11, FastAPI, PostgreSQL."
```

생성되는 파일:
- `docs/adr/0001-initial-architecture.md`
- `docs/code-convention.yaml`
- `harness_structure.yaml`
- `.harness/project-policy.yaml`
- `CLAUDE.md`
- **`.claude/settings.json`** — 팀 공유 allow/deny + Stop hook 연결
- **`.claude/hooks/post_session_checks.sh`** — fresh 프로젝트에서도 안전한 선택형 검사. 설치된 도구와 존재하는 파일 기준으로 ruff·mypy·structure·pytest를 실행하고, 없으면 건너뜀

이후 본격 작업은 `harness` CLI로 이어진다. 기존 파일은 보존(`--force`로 덮어쓰기), LLM 실패 시 내장 템플릿 폴백, `--dry-run`으로 미리보기 가능.

### 케이스 B — 기존 코드베이스 수정

> 케이스 B부터는 LLM 호출이 발생하므로 먼저 엔드포인트를 지정한다.
> ```bash
> export HARNESS_API_ENDPOINT="https://your-internal-endpoint"
> # 또는 매번 --api-endpoint "https://..." 옵션으로 전달
> ```

```bash
cd /path/to/existing-repo
harness --mode modify --use-headless-phases \
  "로그인 실패 시 에러 메시지를 명확히 하고 관련 테스트를 보강해주세요"
```

수행되는 일:
1. 현재 git diff, ADR, 컨벤션, 구조 규칙, 정책을 수집해 Planner에 주입
2. Planner가 수정용 스펙·스프린트 계획 생성
3. 스프린트 계약·설계 의도·평가 기준·Phase 파일 생성
4. `phase-01-docs-update`를 먼저 실행하고 `docs-diff.md` 갱신
5. 이후 Phase를 `claude --print` 독립 세션으로 순차 실행
6. Evaluator가 계약·품질 기준으로 결과 평가

문서 변경이 필요 없는 작업은 `--allow-empty-docs-diff`를 명시한다.

---

## End-to-End: 구현 → PR → 리뷰 → 머지

`--auto-pr`을 붙이면 구현 성공 후 PR 파이프라인까지 자동 연결된다.

```bash
harness --mode modify --use-headless-phases \
  --auto-pr --pr-base main \
  "결제 취소 플로우의 테스트를 보강해주세요"
```

리뷰 반영 후 머지까지:

```bash
harness --mode modify --use-headless-phases \
  --auto-pr --pr-base main --pr-auto-merge \
  "..."
```

전체 흐름:

```
1. 컨텍스트 수집 (diff, ADR, 컨벤션, 구조, 정책)
2. Planner → 수정 계획
3. Phase별 구현 (docs-update → core-impl → integration → tests → validation)
4. Evaluator 평가 (ruff, mypy, pytest, 구조)
5. ──── 여기까지가 구현 단계 ────
6. git push → PR 생성 (PR 본문 자동 생성)
7. 리뷰 코멘트 수집 (사람 + CodeRabbit)
8. ACCEPT / DEFER / IGNORE 분류 → ACCEPT만 자동 반영
9. 반영 커밋 push → 원본 코멘트에 한국어 답글
10. (옵션) PR 머지
```

PR 파이프라인만 단독 실행:

```bash
auto-pr-pipeline --base main             # PR 자동화
auto-pr-pipeline --base main --auto-merge
```

> 구현이 실패하면(통과 스프린트 0개) PR 단계를 건너뛴다. PR 파이프라인 실패는 구현 결과에 영향을 주지 않는다.

---

## 핵심 개념

### 1. 3-에이전트 + 스프린트 계약

- **Planner**: 사용자 프롬프트(+ modify 시 컨텍스트) → `ProductSpec` / 스프린트 계획
- **Generator**: `SprintContract`대로 파일 변경
- **Evaluator**: 계약 + 품질 기준 충족 여부 평가
- **Orchestrator**: 위 3개를 잇는 루프 + 재시도 + 체크포인트

계약은 `.harness/contracts/sprint_{N}.json`에 raw 텍스트와 함께 구조화 저장된다 (ADR-0005).

### 2. 결정적 → 추론적 센서

`harness/pipeline/harness_pipeline.py`가 다음 순서로 실행한다 (ADR-0002):

```
ruff → mypy → 구조분석(harness_structure.yaml) → pytest → AI 코드 리뷰
```

앞 단계가 실패하면 빠르게 끊고, 비용 큰 AI 단계로 가지 않는다. 모든 단계는 `harness/sensors/`의 센서 객체가 담당하고, **센서는 에이전트에 의존하지 않는다** (구조 검사로 강제).

### 3. modify 모드와 프로젝트 정책

`.harness/project-policy.yaml`이 있으면 컨벤션·ADR·구조 규칙 경로와 프로젝트별 정책을 반영한다. 정책 파일이 없거나 파싱 실패 시 기본 정책으로 폴백 (예외 전파 금지). 외부 ADR 디렉터리(`adr.external_sources`)도 지원 (ADR-0008).

modify 모드는 **최소 변경, 기존 패턴 재사용, 정책 준수**가 기본 원칙이다.

### 4. 헤드리스 Phase와 docs-diff

`--use-headless-phases` 사용 시 오케스트레이터는 스프린트 계약 후:

1. `.harness/tasks/sprint-{N}/phase-*.md` 자기 완결 프롬프트 생성
2. `phase-01-docs-update`로 문서 갱신 → `docs-diff.md` 생성
3. 이후 Phase를 **컨텍스트 격리된** `claude --print` 세션으로 순차 실행
4. 각 Phase는 **20줄 이내 핸드오프**를 다음 Phase에 남긴다

기본 정책은 docs-diff가 비어 있으면 실패다. 예외는 `--allow-empty-docs-diff`로 명시 (ADR-0009).

### 5. PR 자동화와 코멘트 분류

`scripts/auto_pr_pipeline.py`는 push → PR → 리뷰 수집 → 분류 → ACCEPT 반영 → 답글 → 선택적 머지 순서로 동작한다.

- 코멘트 판정: **ACCEPT** (즉시 반영) / **DEFER** (가치는 있으나 범위 밖) / **IGNORE** (잘못된 지적·칭찬·중복)
- **ACCEPT만** `claude --print` 반영 세션에 전달
- CodeRabbit: 외부 리뷰어로 동일 흐름. optional/nit/칭찬성은 **DEFER**.
- 판정 로그: `.harness/review-artifacts/{branch}/review-comments.md`
- 답글은 한국어. GitHub review thread resolve는 API 제약 때문에 답글 기반 확인으로 대체.

분류·답글 형식은 `.claude/skills/pr-review-triage/SKILL.md`가 표준이다.

### 6. 부트스트랩 (harness-init)

외부 프로젝트나 신규 저장소에 하네스 규칙 묶음을 한 번에 배치한다. ADR/컨벤션/구조/정책/CLAUDE.md와 `.claude` 팀 설정 + 안전한 Stop 훅 + LLM 보강 + 템플릿 폴백 + dry-run을 지원한다.

`.claude/settings.json`은 LLM에 위임하지 않는다 (`_LLM_SKIP_KINDS` — JSON 보안 설정은 결정적 템플릿만). `--only claude-config`는 `.claude/settings.json`과 `.claude/hooks/post_session_checks.sh`를 함께 배포한다. 기존 `settings.json`은 보존하되 Stop hook 스크립트가 누락된 경우에는 sidecar hook만 복구한다.

> ⚠️ `harness-init`은 `.claude/settings.json`과 hook만 배포하고 **`.claude/skills/`는 배포하지 않는다**. 외부 프로젝트에서 본 저장소의 스킬을 사용하려면 `.claude/skills/{name}/` 디렉터리를 수동으로 복사한다.

---

## Claude Code 하네스 레이어 (자기 도그푸딩)

본 저장소는 자신이 외부에 권장하는 하네스 5계층을 자기 자신에 적용한다.

| 계층 | 위치 | 역할 |
|------|------|------|
| **CLAUDE.md (얇게, 계층적)** | 루트 + 9개 서브패키지 | 루트는 포인터·CRITICAL만(≈65줄), 서브패키지별 로컬 규칙은 작업 시에만 추가 로드 |
| **Hooks** | `.claude/hooks/` | `post_session_checks.sh` (Stop: ruff→mypy→structure), `guard_no_print.py` (PreToolUse: `harness/` 내 `print(` 차단) |
| **Skills** | `.claude/skills/` | `pr-review-triage`, `adr-author`, `phase-handoff` — 작업별 progressive disclosure |
| **팀 공유 설정** | `.claude/settings.json` (커밋) | allow/deny + hooks 연결. 개인 오버라이드는 `.claude/settings.local.json`(`.gitignore`) |
| **운영 가이드 분리** | [docs/operations.md](docs/operations.md) | CLAUDE.md에서 빼낸 명령어·정책 상세를 한 곳에 |
| **부트스트랩 배포 채널** | `harness-init`이 위 셋업을 함께 배포 | 외부 프로젝트가 첫날부터 동일 hook 환경 |

**의미**: CRITICAL 규칙이 "모델이 기억해야 하는 것"에서 "시스템이 강제하는 것"으로 이동했다. 예) `harness/`에 `print(` 작성 시도는 hook이 즉시 차단(exit 2), 세션 종료 시 ruff/mypy/structure 자동 실행, ADR/리뷰 작업 시 skill 형식 자동 로드.

---

## Claude Code에서 사용하기

본 저장소를 클론한 뒤 Claude Code(`claude` CLI / IDE)에서 열면 다음이 자동 적용된다.

### 자동 활성화되는 것

| 무엇 | 위치 | 동작 시점 |
|------|------|----------|
| 팀 공유 permission | `.claude/settings.json` | 세션 시작 시. ruff/mypy/pytest/`gh pr view·list·diff·status·checks·comment·create` 등을 별도 승인 없이 허용 |
| Stop hook | `.claude/hooks/post_session_checks.sh` | 세션 종료 시 ruff → mypy → structure 자동 실행. `CLAUDE_HOOK_SKIP=1`로 우회 |
| PreToolUse guard | `.claude/hooks/guard_no_print.py` | `Write/Edit/MultiEdit`로 `harness/` 내부에 `print(` 작성 시 즉시 차단 (exit 2) |
| 서브패키지 CLAUDE.md | `harness/*/CLAUDE.md` | 해당 디렉터리 파일을 읽을 때 추가 컨텍스트로 로드 |

### 스킬 호출 방법

3개의 스킬은 **사용자가 명시적으로 호출하지 않아도** description의 트리거 조건에 맞으면 Claude가 자동으로 따른다. 슬래시 명령으로 강제 호출도 가능.

| 스킬 | 자동 트리거 | 슬래시 호출 | 정의 |
|------|------------|------------|------|
| `pr-review-triage` | `gh pr view` / `gh api .../comments` 결과 처리, `auto-pr-pipeline` 실행, `review-comments.md` 작성 시 | `/pr-review-triage` | [SKILL.md](.claude/skills/pr-review-triage/SKILL.md) |
| `adr-author` | "ADR 작성", "결정 사항 기록", "아키텍처 결정" 등의 발화 | `/adr-author` | [SKILL.md](.claude/skills/adr-author/SKILL.md) |
| `phase-handoff` | `--use-headless-phases` 실행 중 한 Phase 종료 직전 | `/phase-handoff` | [SKILL.md](.claude/skills/phase-handoff/SKILL.md) |

### 권장 사용 흐름

```bash
# 1. 셸에서 한 번만
export HARNESS_API_ENDPOINT="https://your-internal-endpoint"
gh auth login                       # PR 자동화를 쓸 경우

# 2. Claude Code 진입
cd python-harness && claude         # IDE는 그냥 폴더 열기

# 3. Claude 안에서 자연어로 요청
#    예) "결제 모듈에 재시도 로직 추가하고 PR까지 올려줘"
#    → 내부에서 harness CLI를 호출하고, 위 스킬·hook이 자동 작동
```

개인용 permission 오버라이드는 `.claude/settings.local.json` (gitignore됨)에 둔다.

---

## CLI 빠른 참조

상세 옵션은 [docs/operations.md](docs/operations.md) 또는 각 명령의 `--help`를 본다.

```bash
# 메인 실행
harness "..."                                                      # create 모드
harness --mode modify "..."                                        # modify
harness --mode modify --use-headless-phases "..."                  # 헤드리스 Phase
harness --mode modify --use-headless-phases --allow-empty-docs-diff "..."  # 문서 변경 없는 작업
harness --mode modify --use-headless-phases --auto-pr --pr-base main "..."  # End-to-End
harness --project-dir /path/to/repo --mode modify "..."            # 다른 디렉터리 대상
harness --api-endpoint "https://..." "..."                         # 환경변수 대신 직접 전달
harness --resume                                                   # 현재 디렉터리의 최근 체크포인트 재개
harness --run-id <run_id>                                          # 여러 run 중 특정 체크포인트 재개

# PR 자동화 단독
auto-pr-pipeline --base main                  # push → PR → 리뷰 반영
auto-pr-pipeline --base main --auto-merge     # 머지까지
create-pr-body --base main --output pr-body.md

# 부트스트랩
harness-init --offline "사내 청구 자동화"
harness-init --only claude-config --offline "팀 셋업만 배포"     # .claude/settings.json + Stop hook
harness-init --dry-run --offline "사전 검토"

# 직접 검증
ruff check . && mypy harness && python3 scripts/check_structure.py && pytest
```

---

## 트러블슈팅

| 증상 | 원인 | 대처 |
|------|------|------|
| `HARNESS_API_ENDPOINT is not set` 등 LLM 호출 에러 | 환경변수 미설정 | `export HARNESS_API_ENDPOINT=...` 또는 `--api-endpoint` 옵션 사용. 부트스트랩 미리보기는 `harness-init --offline`/`--dry-run`이라 영향 없음 |
| `--auto-pr` 실행이 PR 단계 진입 직전에 멈춤 | `gh` CLI 미인증 또는 미설치 | `gh auth login` 수행 후 재실행. 인증 상태는 `gh auth status`로 확인 |
| `docs-diff is empty` 같은 메시지로 Phase 실패 | 첫 Phase에서 문서가 갱신되지 않음 (기본 정책) | 문서 변경이 정말 필요 없는 작업이면 `--allow-empty-docs-diff` 명시. 그렇지 않으면 문서 갱신 의도를 프롬프트에 추가 |
| `--auto-pr` 사용했는데 PR이 안 만들어짐 | 통과 스프린트 0개 — 구현 단계가 실패 | `.harness/artifacts/summary.json`과 Evaluator 로그로 실패 원인 확인 후 재시도. PR 파이프라인 자체는 정상 |
| 세션 종료 시 ruff/mypy/structure 검사가 매번 돌아 거슬림 | 본 저장소의 Stop hook | 임시 우회는 `CLAUDE_HOOK_SKIP=1`. 외부 프로젝트의 fresh 환경에서는 도구·파일이 없으면 자동 건너뜀 |
| `print(...)` 추가가 차단됨 | `harness/` 디렉터리에 대한 PreToolUse guard | `logging` 모듈로 대체. 정말 필요한 경우 `harness/` 밖에서만 사용 |
| `--resume`이 다른 run을 잡거나 못 찾음 | 같은 디렉터리에 여러 run 기록 | `.harness/checkpoints/`에서 run_id 확인 후 `--run-id <id>`로 명시 |
| 외부 프로젝트에 부트스트랩했더니 `/pr-review-triage` 등이 안 보임 | `harness-init`은 스킬을 배포하지 않음 | `.claude/skills/{name}/` 디렉터리를 본 저장소에서 수동 복사 |

---

## 프로젝트 구조

```
python-harness/
├── harness/                    # 메인 패키지
│   ├── agents/                 #   Planner, Generator, Evaluator, Orchestrator (+ CLAUDE.md)
│   ├── sensors/
│   │   ├── computational/      #   ruff, mypy, pytest, 구조분석 센서
│   │   └── inferential/        #   AI 코드 리뷰
│   ├── pipeline/               #   통합 파이프라인 (+ CLAUDE.md)
│   ├── review/                 #   리뷰 산출물, PR 본문, docs-diff, worktree, session-fork (+ CLAUDE.md)
│   ├── guides/                 #   시스템 프롬프트, GuideRegistry, ContextFilter (+ CLAUDE.md)
│   ├── context/                #   체크포인트, modify 컨텍스트, 정책, Phase 매니저 (+ CLAUDE.md)
│   ├── contracts/              #   SprintContract 모델, 저장소 (+ CLAUDE.md)
│   ├── bootstrap/              #   harness-init 부트스트래퍼, 템플릿 (+ CLAUDE.md)
│   └── tools/                  #   shell, path_safety, file_io, api_client, adr_loader (+ CLAUDE.md)
├── scripts/                    # CLI 스크립트
│   ├── run_harness.py          #   메인 (create/modify/resume)
│   ├── auto_pr_pipeline.py     #   PR 자동화
│   ├── create_pr_body.py       #   PR 본문 생성
│   ├── init_harness.py         #   harness-init
│   ├── run_phases.py           #   Phase별 claude --print 실행
│   ├── check_structure.py      #   구조 규칙 검사
│   └── pr_review.py            #   GitHub Actions PR AI 리뷰
├── tests/                      # pytest 테스트 (486개)
├── docs/
│   ├── adr/                    # ADR 0001~0009
│   ├── code-convention.yaml
│   └── operations.md           # CLI/운영 상세 가이드
├── .claude/                    # Claude Code 하네스 레이어
│   ├── settings.json           #   팀 공유 (allow/deny + hooks) — 커밋
│   ├── settings.local.json     #   개인 오버라이드 — .gitignore
│   ├── hooks/                  #   post_session_checks.sh, guard_no_print.py
│   └── skills/                 #   pr-review-triage/, adr-author/, phase-handoff/
├── harness_structure.yaml      # 아키텍처 자동 검증 규칙
├── pyproject.toml
├── CLAUDE.md                   # 루트 (얇은 포인터)
└── AGENTS.md                   # 에이전트 런타임 컨텍스트
```

---

## 산출물 경로

```
.harness/
├── artifacts/
│   ├── spec.json                     # Planner 출력
│   └── summary.json                  # 실행 요약
├── contracts/
│   └── sprint_{N}.json               # 구조화 스프린트 계약
├── checkpoints/
│   ├── {run_id}.json                 # 실행별 체크포인트
│   └── latest.json                   # 최근 실행 포인터
├── review-artifacts/{branch}/
│   ├── design-intent.md              # 설계 의도
│   ├── code-quality-guide.md         # 평가 기준
│   ├── pr-body.md                    # PR 본문
│   ├── review-comments.md            # 리뷰 반영 판단 로그
│   └── docs-diff-sprint{N}.md        # 스프린트별 docs-diff
└── tasks/sprint-{N}/
    ├── task-index.json               # Phase 인덱스/상태
    ├── phase-*.md                    # 자기 완결 Phase 프롬프트
    ├── docs-diff.md                  # docs-update 이후 런타임 docs-diff
    └── phase-*-handoff.md            # Phase 간 핸드오프 (≤20줄)
```

---

## 프로젝트 정책 파일

`.harness/project-policy.yaml`가 있으면 컨벤션·ADR·구조 경로와 프로젝트별 정책이 반영된다. 파일이 없거나 파싱 실패하면 기본 정책 사용 (ADR-0008).

```yaml
project:
  name: my-app
  language: python
  python_version: "3.11+"
policies:
  review_language: ko
  required_checks: [ruff, mypy, pytest, structure]
  conventions:
    source: docs/code-convention.yaml
  adr:
    directory: docs/adr/
    external_sources: []          # 외부 프로젝트 ADR 경로 (절대경로)
  structure:
    source: harness_structure.yaml
  artifacts:
    design_intent: true
    code_quality_guide: true
    review_comments: true
    pr_body: true
  custom_rules: |
    프로젝트별 암묵지, 금지사항, 검증 규칙을 자유 형식으로 적는다.
```

정책 파일에는 토큰·비밀값을 넣지 않는다.

---

## 품질 기준 / 검증

에이전트가 생성한 코드는 다음을 모두 통과해야 한다:

- **ruff 에러 0개**
- **mypy 에러 0개** (strict 모드)
- **pytest 전체 통과**
- **`harness_structure.yaml` 규칙 위반 0개**

본 저장소 자체 검증:

```bash
ruff check . && mypy harness && python3 scripts/check_structure.py && pytest
```

세션 종료 시 본 저장소의 `.claude/hooks/post_session_checks.sh`는 ruff → mypy → structure를 자동 실행한다 (`CLAUDE_HOOK_SKIP=1`로 우회 가능). pytest는 CI와 수동 검증 명령에서 실행한다.

---

## ADR 목록

| ADR | 제목 | 핵심 결정 |
|-----|------|----------|
| [0001](docs/adr/0001-three-agent-architecture.md) | 3-에이전트 아키텍처 | Planner→Generator→Evaluator, 계약 협상 |
| [0002](docs/adr/0002-computational-sensors-first.md) | 연산적 센서 우선 | ruff→mypy→구조→pytest 결정적 검사 후 AI 리뷰 |
| [0003](docs/adr/0003-adr-driven-architecture-rules.md) | ADR 기반 아키텍처 규칙 | ADR + `harness_structure.yaml` 검증 |
| [0004](docs/adr/0004-review-artifacts-workflow.md) | 리뷰 산출물 워크플로 | 브랜치별 설계 의도·기준·PR 본문·반영 로그 |
| [0005](docs/adr/0005-structured-sprint-contracts.md) | 구조화 스프린트 계약 | raw 보존 + 구조화 파싱, JSON 저장 |
| [0006](docs/adr/0006-checkpoint-and-resume.md) | 체크포인트와 재개 | Phase enum, run_id 기반 세션 복원 |
| [0007](docs/adr/0007-guide-registry.md) | 가이드 레지스트리 | 시스템 프롬프트/컨텍스트 중앙 관리 |
| [0008](docs/adr/0008-modify-mode-and-project-policy.md) | 수정 모드와 프로젝트 정책 | modify 구현, `project-policy.yaml` 정책 적용 |
| [0009](docs/adr/0009-phase-execution-and-context-isolation.md) | Phase 실행과 컨텍스트 격리 | docs-diff, Phase 분할, 컨텍스트 필터, 헤드리스 실행, PR 자동화, 세션 포크 |

신규 ADR 작성 시 `.claude/skills/adr-author/SKILL.md`의 번호 규칙·본문 형식을 따른다.

---

## CI/CD

`.github/workflows/pr-check.yml`이 PR마다 다음 Job을 실행한다:

| Job | 설명 | 의존성 |
|-----|------|--------|
| `lint` | ruff | - |
| `type-check` | mypy (strict) | - |
| `test` | pytest | - |
| `structure` | `scripts/check_structure.py` | - |
| `ai-review` | AI 코드 리뷰 | 위 4개 통과 후 |
| `pr-body` | PR 본문 자동 생성 | lint |

AI 리뷰는 저장소 secret에 `HARNESS_API_ENDPOINT`가 등록되어 있을 때만 동작한다. secret이 없으면 그 단계만 건너뛴다.

독립 실행: `scripts/pr_review.py`는 `GITHUB_TOKEN`, `PR_NUMBER`, `HARNESS_API_ENDPOINT`를 받아 PR diff에 AI 리뷰를 단다.

---

## 라이선스

내부 프레임워크.
