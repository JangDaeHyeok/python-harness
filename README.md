# Python Harness Framework

AI 코딩 에이전트를 위한 **하네스(harness) 엔지니어링 프레임워크**.

사용자가 자연어로 만들고 싶은 것 또는 고치고 싶은 것을 설명하면, 3-에이전트(Planner / Generator / Evaluator)가 **계약 기반 스프린트 루프**로 코드를 작성·검사·평가하고, 결정적 센서(ruff·mypy·pytest·구조 검사)와 AI 코드 리뷰를 거쳐 PR 생성·리뷰 반영·머지까지 한 흐름으로 연결한다.

> "모델은 점점 좋아지지만, 코딩 에이전트의 성능은 **모델 주변의 하네스**에 더 많이 좌우된다." — 이 프로젝트는 그 명제를 자기 자신에도 적용한다 (`.claude/` 셋업, 서브패키지 CLAUDE.md, hooks, skills).

---

## 목차

- [핵심 가치](#핵심-가치)
- [어떤 명령을 써야 하나요?](#어떤-명령을-써야-하나요)
- [요구 사항 / 설치](#요구-사항--설치)
- [환경변수](#환경변수)
- [5분 안에 써보기](#5분-안에-써보기)
- [End-to-End: 구현 → PR → 리뷰 → 머지](#end-to-end-구현--pr--리뷰--머지)
- [전체 워크스루: init부터 머지까지 한 흐름으로](#전체-워크스루-init부터-머지까지-한-흐름으로)
- [시나리오별 CLI 레시피](#시나리오별-cli-레시피)
- [CLI 옵션 상세](#cli-옵션-상세)
- [핵심 개념](#핵심-개념)
- [Claude Code 하네스 레이어 (자기 도그푸딩)](#claude-code-하네스-레이어-자기-도그푸딩)
- [Claude Code에서 사용하기](#claude-code에서-사용하기)
  - [자동 활성화되는 것](#자동-활성화되는-것)
  - [스킬 사용 가이드](#스킬-사용-가이드)
  - [`pr-review-triage` 스킬](#pr-review-triage-스킬)
  - [`adr-author` 스킬](#adr-author-스킬)
  - [`phase-handoff` 스킬](#phase-handoff-스킬)
  - [권장 사용 흐름](#권장-사용-흐름)
- [CLI 빠른 참조](#cli-빠른-참조)
- [자주 묻는 질문 (FAQ)](#자주-묻는-질문-faq)
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
| **고정 구조 게이트** | modify/resume/PR 산출물 생성 전에 `docs/`, `tests/`, `scripts/`, 정책 package 등 필수 구조를 확인하고, 누락 시 `harness-init --migrate`를 안내한다 (ADR-0010, ADR-0011). |
| **결정적 평가 게이트** | 스프린트 평가 직전에 파이프라인을 다시 실행하고, 결정적 검사와 LLM 평가가 모두 pass일 때만 최종 pass로 판정한다 (ADR-0012). |
| **PR 자동화** | push → PR → 코멘트 수집 → ACCEPT/DEFER/IGNORE 분류 → ACCEPT만 반영 → 한국어 답글 → 선택적 머지. CodeRabbit 코멘트도 동일 흐름. |
| **부트스트랩(harness-init)** | 외부 프로젝트에 ADR/컨벤션/구조/정책/CLAUDE.md와 `.claude` 팀 설정·Stop 훅을 일괄 배치. LLM이 자연어 의도로 보강. |
| **자기 도그푸딩** | 본 저장소 스스로 hooks·skills·서브패키지 CLAUDE.md를 적용. CRITICAL 규칙은 모델 기억력이 아니라 hook으로 강제된다. |

---

## 어떤 명령을 써야 하나요?

처음이라면 아래 표에서 현재 상황에 맞는 줄 하나만 고르면 된다. 자세한 옵션은 뒤의 [시나리오별 CLI 레시피](#시나리오별-cli-레시피)와 [CLI 옵션 상세](#cli-옵션-상세)에 모아두었다.

| 하고 싶은 일 | 먼저 실행할 명령 | 언제 쓰나 |
|-------------|----------------|----------|
| 새 프로젝트에 하네스 규칙 파일만 깔기 | `harness-init --offline "프로젝트 설명"` | ADR, 컨벤션, 구조 규칙, CLAUDE.md, `.claude` 설정을 처음 배치할 때 |
| 기존 Python 프로젝트를 하네스 구조로 보강하기 | `harness-init --migrate --offline "프로젝트 설명"` | 이미 코드가 있는 저장소에 누락된 `docs/`, `.harness/`, `tests/`, `scripts/` 등을 맞출 때 |
| 현재 저장소를 자연어 요청대로 수정하기 | `harness --mode modify "수정 요청"` | 작은 기능 추가, 버그 수정, 테스트 보강처럼 로컬 구현·평가까지만 필요할 때 |
| 큰 작업을 Phase로 나눠 안정적으로 진행하기 | `harness --mode modify --use-headless-phases "수정 요청"` | 여러 파일을 건드리는 리팩터링, 문서/구현/테스트가 함께 바뀌는 작업 |
| 구현 후 PR까지 자동으로 열기 | `harness --mode modify --use-headless-phases --auto-pr --pr-base main "수정 요청"` | 구현, 검증, push, PR 생성을 한 번에 연결할 때 |
| 이미 있는 PR의 리뷰 코멘트만 처리하기 | `auto-pr-pipeline --base main` | 현재 브랜치의 PR 리뷰를 수집하고 ACCEPT 코멘트만 반영할 때 |
| PR 본문만 따로 만들기 | `create-pr-body --base main --output pr-body.md` | 수동으로 PR을 열되 하네스 산출물 기반 본문이 필요할 때 |

가장 흔한 흐름은 다음 둘이다.

```bash
# 1) 새 프로젝트에 하네스 셋업
harness-init --offline "사내 청구 자동화 도구. Python 3.11, FastAPI, PostgreSQL"

# 2) 기존 프로젝트 수정
export HARNESS_API_ENDPOINT="https://your-internal-endpoint"
harness --mode modify --use-headless-phases \
  "로그인 실패 시 에러 메시지를 명확히 하고 관련 테스트를 보강해주세요"
```

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
| `harness-init` | `scripts/init_harness.py` | 신규/기존 프로젝트 부트스트랩 |

---

## 환경변수

| 이름 | 설명 | 필수 |
|------|------|-----|
| `HARNESS_API_ENDPOINT` | Planner / Generator / Evaluator / AI 리뷰가 호출할 비공개 API 엔드포인트 | AI 호출 시 필수 |
| `CLAUDE_HOOK_SKIP` | `1`로 설정 시 Stop hook(`.claude/hooks/post_session_checks.sh`)을 우회 (CI/임시 디버깅용) | 선택 |

`HARNESS_API_ENDPOINT`를 환경변수로 두는 대신 실행 시 `--api-endpoint`로 직접 넘길 수도 있다. 토큰·비밀값을 커밋하지 않는다.

예시:

```bash
export HARNESS_API_ENDPOINT="https://your-internal-endpoint"

# 환경변수를 쓰고 싶지 않은 일회성 실행
harness --api-endpoint "https://your-internal-endpoint" \
  --mode modify "회원가입 에러 처리를 보강해주세요"
```

---

## 5분 안에 써보기

이 섹션은 설치 직후 바로 손에 익히기 위한 최소 경로다. 더 많은 상황별 예시는 [시나리오별 CLI 레시피](#시나리오별-cli-레시피)에 있다.

### 케이스 A — 신규 프로젝트에 하네스 셋업 한 번에 배치

```bash
mkdir -p ~/projects/billing && cd ~/projects/billing
git init
harness-init --offline "사내 청구 자동화 도구. Python 3.11, FastAPI, PostgreSQL."
```

CodeRabbit 리뷰를 GitHub PR에서 함께 쓰려면 설정 파일을 선택적으로 배포할 수 있다. 이 명령은 `.coderabbit.yaml`만 만들며, GitHub 저장소의 CodeRabbit App 설치와 권한 승인은 별도로 해야 한다.

> ⚠️ `knowledge_base.code_guidelines`에 의해 `CLAUDE.md`, `docs/adr/*.md`, `.harness/project-policy.yaml`이 CodeRabbit(third-party SaaS)으로 전송된다. 사내 정보가 포함될 수 있으니 노출 가능 여부를 확인한 뒤 사용하라.

```bash
harness-init --with-coderabbit --offline "사내 청구 자동화 도구. Python 3.11, FastAPI, PostgreSQL."
# 또는 설정 파일만
harness-init --only coderabbit --offline "GitHub PR 리뷰 자동화"
```

- `--with-coderabbit`는 `--only` 목록에 `coderabbit`를 추가하는 syntactic sugar다. `--only adr --with-coderabbit`처럼 조합하면 ADR + `.coderabbit.yaml`만 생성된다.
- 기존 `.harness/project-policy.yaml`이 있어도 `--with-coderabbit` 사용 시 `policies.review_tools.coderabbit` 플래그를 `true`로 자동 동기화한다 (다른 키/주석은 보존). `--force` 없이도 동작.

생성되는 파일:
- `docs/adr/0001-initial-architecture.md`
- `docs/code-convention.yaml`
- `harness_structure.yaml`
- `.harness/project-policy.yaml`
- `CLAUDE.md`
- **`.claude/settings.json`** — 팀 공유 allow/deny + Stop hook 연결
- **`.claude/hooks/post_session_checks.sh`** — fresh 프로젝트에서도 안전한 선택형 검사. 설치된 도구와 존재하는 파일 기준으로 ruff·mypy·structure·pytest를 실행하고, 없으면 건너뜀
- `--with-coderabbit` 또는 `--only coderabbit` 사용 시 **`.coderabbit.yaml`** — CodeRabbit PR 리뷰 설정 템플릿

잘 생성됐는지 확인:

```bash
ls docs/adr/ .harness/ .claude/
git status --short
```

이후 본격 작업은 `harness` CLI로 이어진다. 기존 파일은 보존(`--force`로 덮어쓰기), LLM 실패 시 내장 템플릿 폴백, `--dry-run`으로 미리보기 가능.

### 케이스 A-2 — 기존 Python 프로젝트를 하네스 구조로 보강

이미 코드가 있는 저장소라면 `--migrate`를 먼저 사용한다. 이 모드는 기존 README, CLAUDE.md, `.claude/skills/`는 건드리지 않고 하네스 필수 파일과 디렉터리만 보강한다.

```bash
cd /path/to/existing-python-repo
harness-init --migrate --offline "기존 서비스에 Python Harness 적용"
```

마이그레이션은 루트 패키지(`my_package/__init__.py`)를 자동 탐지한다. 후보가 여러 개이거나 `src/` 레이아웃처럼 루트 패키지가 없으면 중단하고 `.harness/project-policy.yaml`의 `project.package`를 명시하라고 안내한다.

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

실행 후에는 아래 파일을 먼저 보면 결과를 빠르게 파악할 수 있다.

```bash
cat .harness/artifacts/summary.json
ls .harness/contracts/
ls .harness/tasks/sprint-1/  # --use-headless-phases 사용 시
```

프롬프트는 짧아도 되지만, 좋은 요청은 “무엇을 바꿀지”, “어떤 제약이 있는지”, “어떻게 확인할지”를 포함한다.

```text
로그인 실패 시 사용자에게 원인을 구분해서 보여주세요.
기존 API 응답 형식은 깨지지 않아야 하고, 관련 단위 테스트를 추가해주세요.
문서의 에러 메시지 예시도 같이 갱신해주세요.
```

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

## 전체 워크스루: init부터 머지까지 한 흐름으로

위의 개별 섹션을 처음부터 끝까지 한 시나리오로 이어 본다. 빈 디렉터리에서 시작해 PR 리뷰 답글까지 도달하는 가장 흔한 경로다. 각 단계는 앞 단계의 산출물을 그대로 사용하므로 위에서부터 차례로 따라가면 된다.

> 가정: 사내 청구 자동화 도구를 새로 만들고, 첫 기능으로 "결제 재시도 로직"을 추가한 뒤 PR을 올려 CodeRabbit + 동료 리뷰를 받아 머지하는 상황.

### 0. 1회성 셋업 (최초 한 번만)

```bash
export HARNESS_API_ENDPOINT="https://your-internal-endpoint"   # ~/.zshrc 등에 영구 저장 권장
gh auth login                                                  # PR 자동화에서 필요
pip install -e ".[dev]"                                        # 본 저장소 클론한 경우
```

### 1. 신규 프로젝트 부트스트랩 (`harness-init`)

```bash
mkdir -p ~/projects/billing && cd ~/projects/billing
git init
harness-init --offline "사내 청구 자동화 도구. Python 3.11, FastAPI, PostgreSQL."
git add -A && git commit -m "chore: bootstrap harness"
```

이 시점에 생기는 것:
- `docs/adr/0001-initial-architecture.md`, `docs/code-convention.yaml`, `harness_structure.yaml`
- `.harness/project-policy.yaml`
- `CLAUDE.md`, `.claude/settings.json`, `.claude/hooks/post_session_checks.sh`

> 이미 코드가 있는 저장소라면 1단계는 `harness-init --migrate --offline "..."`로 대체한다 (기존 README/스킬은 보존).

### 2. Claude Code 진입 (선택, 권장)

```bash
claude        # 또는 VS Code/JetBrains에서 폴더 열기
```

진입과 동시에 `.claude/settings.json`의 permission, Stop hook, PreToolUse guard가 자동 활성화된다. 이후 단계는 Claude와 대화로 진행해도 되고, 셸에서 직접 CLI를 쳐도 동일하다.

### 3. 자연어 요청 → 구현 → PR 자동 생성

Claude Code 안에서:

> 사용자: `결제 모듈에 재시도 횟수 환경변수(MAX_RETRY)와 지수 백오프를 추가하고, 단위 테스트와 문서까지 갱신한 뒤 PR을 올려줘`

또는 셸에서 직접:

```bash
harness --mode modify --use-headless-phases \
  --auto-pr --pr-base main \
  "결제 모듈에 재시도 횟수 환경변수(MAX_RETRY)와 지수 백오프를 추가하고, 단위 테스트와 문서를 갱신해주세요"
```

내부 진행:
1. diff·ADR·컨벤션·구조·정책 수집 → Planner 컨텍스트 주입
2. Planner → `SprintContract` 생성
3. `phase-01-docs-update` → `docs-diff.md` 갱신 → 이후 Phase가 `claude --print` 독립 세션으로 순차 실행
4. Phase 사이 20줄 핸드오프 (`phase-handoff` 스킬)
5. Evaluator가 결정적 센서(ruff/mypy/structure/pytest) + LLM 평가로 최종 판정 (ADR-0012)
6. 통과하면 push → PR 본문 자동 생성 → PR 오픈

중간 점검:

```bash
cat .harness/artifacts/summary.json                 # 실행 요약
ls .harness/tasks/sprint-1/                         # Phase별 산출물
cat .harness/tasks/sprint-1/docs-diff.md            # 문서 변경 요약
```

### 4. 리뷰 코멘트 자동 처리 (사람 + CodeRabbit)

PR이 열린 뒤 사람·CodeRabbit이 코멘트를 남기면, 같은 명령에 `--pr-auto-merge`를 더해 마지막까지 자동으로 갈 수도 있고, 별도로 분리해 처리할 수도 있다.

분리해서 처리하는 경우 (PR 브랜치에 체크아웃된 상태에서):

```bash
auto-pr-pipeline --base main
```

또는 Claude Code 안에서:

> 사용자: `현재 PR의 리뷰 코멘트 정리해서 반영할 건 반영하고 답글 달아줘`

이때 `pr-review-triage` 스킬이 자동 작동해서:
1. `gh pr view ... --comments` + `gh api .../pulls/{n}/comments`로 코멘트 수집
2. 각 코멘트를 **ACCEPT / DEFER / IGNORE**로 분류
3. `.harness/review-artifacts/{branch}/review-comments.md`에 판정 로그 기록
4. ACCEPT만 `claude --print` 반영 세션에 전달 → 코드 수정 → push
5. 원본 코멘트에 한국어 답글

분류 결과 확인:

```bash
cat .harness/review-artifacts/$(git branch --show-current)/review-comments.md
```

`review-comments.md` 예시 (실제 출력의 발췌):

```markdown
## Comment #1 (CodeRabbit, harness/payment/retry.py:42)
> Consider extracting the backoff calculation into a helper for testability.

**판정**: ACCEPT
**근거**: 테스트 용이성·재사용성 개선이며 변경 범위가 작다.
**반영**: `_calc_backoff` 헬퍼로 추출, 단위 테스트 추가.

## Comment #2 (reviewer@team, harness/payment/retry.py:58)
> nit: 변수명 i 대신 attempt가 어떨까요?

**판정**: DEFER
**근거**: nit, 합의된 컨벤션 위반은 아님. 다음 정리 PR에서 일괄 반영 예정.
```

### 5. 머지

머지까지 한 줄로 가고 싶었으면 3단계에서 이미 `--pr-auto-merge`를 줬을 것이고, 그렇지 않다면:

```bash
auto-pr-pipeline --base main --auto-merge
# 또는 수동
gh pr merge --squash --delete-branch
```

### 6. 끝났을 때 남는 것

```
.harness/
├── artifacts/summary.json                            # 전체 실행 요약
├── contracts/sprint_1.json                           # 스프린트 계약
├── checkpoints/{run_id}.json                         # 재개 가능 체크포인트
├── tasks/sprint-1/
│   ├── phase-01-docs-update.md ... phase-*.md        # Phase 프롬프트
│   ├── docs-diff.md                                  # 런타임 docs-diff
│   └── phase-*-handoff.md                            # Phase 간 ≤20줄 핸드오프
└── review-artifacts/{branch}/
    ├── design-intent.md / code-quality-guide.md
    ├── pr-body.md                                    # PR 본문
    └── review-comments.md                            # 코드리뷰 판정 로그
```

세션 종료 시 Stop hook이 `ruff → mypy → structure`를 한 번 더 돌려서 깨진 코드가 남지 않도록 한다 (임시 우회: `CLAUDE_HOOK_SKIP=1`).

### 한 줄 요약

```bash
# (선택) Claude Code 안에서 자연어로 한 줄
"결제 재시도 로직 추가하고 PR 올리고 리뷰 코멘트도 반영해줘"

# 같은 일을 셸에서 한 줄로
harness --mode modify --use-headless-phases \
  --auto-pr --pr-base main --pr-auto-merge \
  "결제 재시도 로직 추가, 단위 테스트·문서 갱신 포함"
```

`harness-init`만 한 번 깔아두면, 이후 모든 변경은 위 한 줄(또는 자연어 한 문장)로 init·구현·PR·리뷰 반영·머지가 일관된 파이프라인으로 이어진다.

---

## 시나리오별 CLI 레시피

"무엇을 하고 싶은지 → 어떤 명령을 칠지" 매핑. 처음 쓰는 사람은 위에서부터 차례로 따라가면 된다.

### 시나리오 1. 새 프로젝트를 시작하는데 하네스 셋업부터 깔고 싶다

```bash
mkdir -p ~/projects/billing && cd ~/projects/billing
git init
harness-init --offline "사내 청구 자동화 도구. Python 3.11, FastAPI, PostgreSQL"
git add -A && git commit -m "chore: bootstrap harness"
```

확인:

```bash
ls docs/adr/ .harness/ .claude/   # ADR/정책/Claude 셋업이 보여야 함
```

LLM 호출 없이 템플릿만 깔고 싶으면 `--offline`을 그대로 둔다. 사후에 LLM으로 보강하고 싶으면 `--offline`을 떼고 `HARNESS_API_ENDPOINT`를 설정한 뒤 같은 명령을 다시 친다 (`--force` 필요).

### 시나리오 1-2. 이미 있는 Python 프로젝트를 하네스 고정 구조에 맞추고 싶다

```bash
cd /path/to/existing-python-repo
harness-init --migrate --offline "기존 Python 서비스에 하네스 적용"
```

생성·보강 대상은 ADR, 코드 컨벤션, 구조 규칙, 프로젝트 정책이다. `tests/`와 `scripts/`가 비어 있으면 `.gitkeep`만 둔다. 기존 `CLAUDE.md`와 `.claude/skills/`는 보존한다.

### 시나리오 2. 기존 코드에 작은 기능을 추가하고 싶다 (PR 없이 로컬 검증만)

```bash
cd /path/to/repo
export HARNESS_API_ENDPOINT="https://your-internal-endpoint"
harness --mode modify "결제 모듈에 재시도 횟수 환경변수(MAX_RETRY)를 추가해주세요"
```

진행 상태 확인:

```bash
cat .harness/artifacts/summary.json
ls .harness/contracts/
```

### 시나리오 3. 큰 작업을 Phase로 쪼개서 안정적으로 진행하고 싶다

```bash
harness --mode modify --use-headless-phases \
  "장바구니 도메인 모델을 신규 사양에 맞게 리팩터링해주세요"
```

이때 일어나는 일:
- `phase-01-docs-update`가 먼저 돌면서 `docs-diff.md`가 생성된다
- 이후 `phase-02-core-impl`, `phase-03-integration`, ... 가 각각 독립 `claude --print` 세션으로 실행된다
- Phase 사이에는 20줄 핸드오프 파일이 남는다

진행 상태:

```bash
ls .harness/tasks/sprint-1/
cat .harness/tasks/sprint-1/phase-01-docs-update-handoff.md
```

### 시나리오 4. 구현 → PR → 코드리뷰 반영 → 머지까지 한 번에

```bash
gh auth login                                            # 처음 한 번만
harness --mode modify --use-headless-phases \
  --auto-pr --pr-base main --pr-auto-merge \
  "결제 취소 플로우의 테스트 커버리지를 80% 이상으로 끌어올려주세요"
```

이 한 줄이 push → PR 생성 → 리뷰 수집 → ACCEPT 코멘트 반영 → 한국어 답글 → 머지까지 자동 수행한다. 머지 직전에 멈추고 싶으면 `--pr-auto-merge`만 뺀다.

### 시나리오 5. PR은 이미 떠 있다. 리뷰 반영만 자동으로 돌리고 싶다

```bash
cd /path/to/repo   # PR 브랜치로 체크아웃된 상태
auto-pr-pipeline --base main
```

판정 결과는 `.harness/review-artifacts/{branch}/review-comments.md`에 남는다. ACCEPT 코멘트만 반영되고, DEFER/IGNORE는 사유만 기록된다.

### 시나리오 6. 도중에 실패했다. 처음부터 다시 안 돌리고 이어서 하고 싶다

```bash
harness --resume                                # 가장 최근 run 이어서
# 또는 여러 run이 섞여 있으면 run_id 명시
ls .harness/checkpoints/
harness --run-id <run_id>
```

### 시나리오 7. 문서 변경이 정말 필요 없는 작업이라서 docs-diff 검사를 건너뛰고 싶다

```bash
harness --mode modify --use-headless-phases --allow-empty-docs-diff \
  "오타 수정 / 단순 로깅 메시지 변경 등"
```

이 옵션은 명시적 예외다. 기본은 "문서 갱신을 강제"하므로, 빠뜨리고 싶지 않은 변경이 있다면 옵션을 빼고 프롬프트에 문서 갱신 의도를 적는 편이 안전하다.

### 시나리오 8. PR 본문만 따로 만들고 싶다

```bash
create-pr-body --base main --output pr-body.md
gh pr create --base main --body-file pr-body.md
```

### 시나리오 9. 외부 프로젝트에 본 저장소의 스킬까지 그대로 가져가고 싶다

`harness-init`은 `.claude/settings.json`과 hook만 배포한다. 스킬은 수동 복사가 필요하다.

```bash
# 외부 프로젝트 루트에서
cp -R /path/to/python-harness/.claude/skills .claude/skills
```

---

## CLI 옵션 상세

각 CLI의 자주 쓰는 옵션과 의미. 전체는 `--help` 또는 [docs/operations.md](docs/operations.md) 참조.

### `harness`

| 옵션 | 의미 |
|------|------|
| `"프롬프트"` | 인자로 자연어 의도를 그대로 전달 |
| `--mode {create,modify}` | `create`(기본): 새 프로젝트 생성, `modify`: 현재 코드 수정 |
| `--use-headless-phases` | Phase별로 `claude --print` 독립 세션 실행 (큰 작업에서 안정적) |
| `--allow-empty-docs-diff` | docs-update Phase에서 문서가 안 바뀌어도 통과시킴 (예외 명시) |
| `--auto-pr` | 구현 성공 시 PR 파이프라인 연결 |
| `--pr-base <branch>` | PR 대상 베이스 브랜치 (예: `main`) |
| `--pr-auto-merge` | 리뷰 반영 후 자동 머지 |
| `--pr-skip-review` | PR 생성까지만 하고 리뷰 수집/반영 건너뜀 |
| `--project-dir <path>` | 현재 디렉터리 대신 다른 저장소를 대상으로 |
| `--api-endpoint <url>` | `HARNESS_API_ENDPOINT` 환경변수 대신 한 번만 지정 |
| `--resume` | 같은 디렉터리의 최근 체크포인트 이어서 실행 |
| `--run-id <id>` | 특정 run의 체크포인트로 재개 |

### `auto-pr-pipeline`

| 옵션 | 의미 |
|------|------|
| `--base <branch>` | PR 대상 베이스 (필수에 가까움) |
| `--auto-merge` | 리뷰 반영 후 머지까지 |
| `--skip-review` | 리뷰 수집/반영 단계 생략 |
| `--title "..."` | PR 제목 직접 지정 (기본은 자동 생성) |
| `--no-poll` | 리뷰 코멘트 폴링 비활성화 |

### `create-pr-body`

| 옵션 | 의미 |
|------|------|
| `--base <branch>` | diff 기준 베이스 |
| `--output <path>` | 결과를 파일로 저장 (없으면 stdout) |
| `--summary "..."` | 자동 요약 대신 직접 지정 |
| `--branch <name>` | 브랜치 이름 오버라이드 |
| `--use-worktree` | git worktree로 격리해서 실행 |

### `harness-init`

| 옵션 | 의미 |
|------|------|
| `"의도"` | 프로젝트의 자연어 설명 (LLM 보강에 사용) |
| `--offline` | LLM 호출 없이 내장 템플릿만으로 셋업 |
| `--project-dir <path>` | 다른 디렉터리에 셋업 |
| `--only <kinds>` | 일부만 배포 (`adr,policy,claude-config,coderabbit` 등 콤마 구분) |
| `--with-coderabbit` | `.coderabbit.yaml` 배포 + 기존 정책 파일의 `review_tools.coderabbit`를 `true`로 동기화 (GitHub App 설치는 별도) |
| `--force` | 기존 파일 덮어쓰기 (기본은 보존) |
| `--dry-run` | 만들 파일 목록만 보여주고 실제로 쓰지 않음 |
| `--migrate` | 기존 Python 프로젝트에 하네스 필수 구조를 보강 (`adr,convention,structure,policy` 중심) |

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

스프린트 최종 평가는 결정적 파이프라인과 LLM 평가를 분리해 기록한다. 둘 중 하나라도 실패하면 최종 스프린트는 fail이다 (ADR-0012).

### 3. modify 모드와 프로젝트 정책

`.harness/project-policy.yaml`이 있으면 컨벤션·ADR·구조 규칙 경로와 프로젝트별 정책을 반영한다. 정책 파일이 없거나 파싱 실패 시 기본 정책으로 폴백 (예외 전파 금지). 외부 ADR 디렉터리(`adr.external_sources`)도 지원 (ADR-0008).

modify 모드는 **최소 변경, 기존 패턴 재사용, 정책 준수**가 기본 원칙이다.

modify/resume, PR 본문 생성, PR 자동화 시작 전에는 고정 구조 게이트도 실행된다. 필수 경로(`docs/`, `docs/adr/*.md`, `docs/code-convention.yaml`, `harness_structure.yaml`, `.harness/project-policy.yaml`, `tests/`, `scripts/`, 정책의 `project.package` 디렉터리)가 없으면 실행을 중단하고 `harness-init --migrate`를 안내한다 (ADR-0010).

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

기존 Python 프로젝트에는 `harness-init --migrate`를 사용한다. 이 경로는 ADR/컨벤션/구조/정책만 대상으로 삼고, 루트 Python 패키지를 정책의 `project.package`에 고정한다. `src/` 레이아웃이나 다중 패키지처럼 자동 선택이 위험한 경우에는 명확한 오류로 멈춘다 (ADR-0011).

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

본 저장소를 클론한 뒤 Claude Code(`claude` CLI / IDE)에서 열면 별도 설정 없이 hooks·skills·서브패키지 CLAUDE.md가 자동 적용된다.

### 자동 활성화되는 것

| 무엇 | 위치 | 동작 시점 | 사용자가 느끼는 효과 |
|------|------|----------|--------------------|
| 팀 공유 permission | `.claude/settings.json` | 세션 시작 시 | ruff/mypy/pytest/`gh pr view·list·diff·status·checks·comment·create` 등이 매번 승인을 묻지 않고 바로 실행됨 |
| Stop hook | `.claude/hooks/post_session_checks.sh` | 세션 종료 시 | ruff → mypy → structure 검사가 자동 실행돼 깨진 코드를 남기지 않음. 임시 우회는 `CLAUDE_HOOK_SKIP=1` |
| PreToolUse guard | `.claude/hooks/guard_no_print.py` | `Write/Edit/MultiEdit` 직전 | `harness/` 내부에 `print(`을 적는 시도는 exit 2로 즉시 차단. CRITICAL 규칙이 시스템 레벨로 강제됨 |
| 서브패키지 CLAUDE.md | `harness/*/CLAUDE.md` | 해당 디렉터리 파일을 읽을 때 | 작업 중인 영역의 로컬 규칙만 추가로 컨텍스트에 들어옴 (루트는 얇게 유지) |

### 스킬 사용 가이드

세 가지 스킬이 등록되어 있다. **명시적으로 호출하지 않아도** description의 트리거 조건에 맞으면 Claude가 자동으로 따른다. 슬래시 명령으로 강제 호출도 가능.

| 스킬 | 자동 트리거 | 슬래시 호출 | 정의 |
|------|------------|------------|------|
| `pr-review-triage` | `gh pr view` / `gh api .../comments` 결과 처리, `auto-pr-pipeline` 실행, `review-comments.md` 작성 | `/pr-review-triage` | [SKILL.md](.claude/skills/pr-review-triage/SKILL.md) |
| `adr-author` | "ADR 작성", "결정 사항 기록", "아키텍처 결정" 등의 발화 | `/adr-author` | [SKILL.md](.claude/skills/adr-author/SKILL.md) |
| `phase-handoff` | `--use-headless-phases` 실행 중 한 Phase 종료 직전 | `/phase-handoff` | [SKILL.md](.claude/skills/phase-handoff/SKILL.md) |

> 💡 **스킬은 "지시"가 아니라 "형식"이다.** Claude가 작업을 할 때 어떤 출력 형식·판정 규칙·파일 위치를 따라야 하는지를 표준화한다. 따라서 같은 작업이라도 스킬이 적용되면 결과가 일관된다.

---

### `pr-review-triage` 스킬

**무엇을 해주는가**
PR에 달린 사람·CodeRabbit 코멘트를 `ACCEPT` / `DEFER` / `IGNORE`로 분류하고, ACCEPT만 코드에 반영하며, 한국어 답글까지 작성한다.

**언제 자동으로 트리거되는가**
- "PR 리뷰 코멘트 반영해줘", "CodeRabbit 코멘트 처리해줘" 같은 요청
- `gh pr view`, `gh api repos/.../pulls/{n}/comments`를 실행한 결과를 다룰 때
- `auto-pr-pipeline` 내부에서 자동 호출

**예시 대화**

> 사용자: `현재 PR #42에 달린 리뷰 코멘트를 검토해서 반영할 건 반영하고 답글 달아줘`

Claude는 이때:
1. `gh pr view 42 --comments`로 코멘트 수집
2. 각 코멘트를 ACCEPT/DEFER/IGNORE로 분류 (스킬의 표를 따름)
3. `.harness/review-artifacts/{branch}/review-comments.md`에 판정 로그 작성
4. ACCEPT 코멘트만 코드에 반영 후 push
5. 원본 코멘트에 한국어로 답글

**산출물 확인**

```bash
cat .harness/review-artifacts/$(git branch --show-current)/review-comments.md
```

**수동 강제 호출**

> 사용자: `/pr-review-triage PR #42`

**분류 기준 요약** (자세히는 [SKILL.md](.claude/skills/pr-review-triage/SKILL.md))

| 판정 | 조건 |
|------|------|
| ACCEPT | 버그·보안·계약 위반, ADR/컨벤션 위반, 합의된 개선 |
| DEFER | 가치는 있으나 범위 밖, nit·취향, optional 제안 (CodeRabbit `Refactor suggestion` 등) |
| IGNORE | 잘못된 지적, 중복, 칭찬성 |

---

### `adr-author` 스킬

**무엇을 해주는가**
ADR(Architecture Decision Record)을 정해진 형식·번호 규칙·한국어 본문으로 작성하거나 갱신한다. 결번 없는 번호 부여, 상태 라벨, 배경/결정/결과 섹션을 표준화한다.

**언제 자동으로 트리거되는가**
- 발화에 "ADR 작성", "결정 사항 기록", "아키텍처 결정"이 포함될 때
- 코드 변경이 아키텍처 결정을 동반해야 할 때 (새 검사 단계 추가, 의존성 방향 변경 등)

**예시 대화**

> 사용자: `센서가 LLM 호출 캐싱을 갖도록 바꾸려고 해. ADR로 기록해줘`

Claude는 이때:
1. `docs/adr/` 디렉터리를 확인해 다음 번호 결정 (현재 0001~0012 → `0013-...`)
2. 스킬이 정의한 형식대로 `0013-inferential-sensor-caching.md` 생성
3. 상태(Proposed/Accepted), 배경, 결정, 결과, 대안, 관련 ADR 섹션 채움

**산출물 확인**

```bash
ls docs/adr/                       # 0013-... 가 추가됨
```

**수동 강제 호출**

> 사용자: `/adr-author "헤드리스 Phase 도입"`

---

### `phase-handoff` 스킬

**무엇을 해주는가**
헤드리스 Phase 실행에서 각 Phase가 다음 Phase로 넘기는 **20줄 이내** 요약을 표준 형식으로 작성한다. Phase 간 컨텍스트 격리에도 필수 정보가 새지 않게 한다.

**언제 자동으로 트리거되는가**
- `harness --mode modify --use-headless-phases`로 실행되는 각 Phase가 종료될 때
- `.harness/tasks/sprint-{N}/{phase_id}-handoff.md` 파일 작성·갱신 시점

**핸드오프 형식**

```markdown
# Handoff — phase-02-core-impl

## 한 줄 요약
결제 도메인 엔티티를 신규 사양에 맞게 분리했다.

## 변경된 파일 (경로만, 최대 10개)
- src/payment/entity.py
- src/payment/dto.py

## 다음 Phase가 알아야 할 사실
- DTO 변환은 아직 미적용. integration Phase에서 처리 필요.
- 기존 호출처는 호환 어댑터로 임시 연결.
```

**산출물 확인**

```bash
ls .harness/tasks/sprint-1/
cat .harness/tasks/sprint-1/phase-02-core-impl-handoff.md
```

**왜 20줄 제한인가**
다음 Phase는 `claude --print` 독립 세션이라 이 핸드오프만 보고 작업을 잇는다. 너무 길면 컨텍스트가 오염되고, 너무 짧으면 정보가 누락된다 (ADR-0009).

---

### 권장 사용 흐름

#### Step 1. 셸에서 한 번만 (최초 1회)

```bash
export HARNESS_API_ENDPOINT="https://your-internal-endpoint"   # ~/.zshrc 등에 영구 저장 권장
gh auth login                                                  # PR 자동화 사용 시
```

#### Step 2. Claude Code 진입

```bash
cd /path/to/python-harness && claude        # 터미널 CLI
# 또는 IDE(VS Code/JetBrains)에서 폴더 열기
```

이 시점에 `.claude/settings.json`의 permission, Stop hook, PreToolUse guard가 자동 적용된다.

#### Step 3. 자연어로 요청

대화 안에서 그냥 자연어로 요청하면 된다. Claude가 필요한 CLI를 알아서 호출하고, 스킬·hook이 자동 작동한다.

> 사용자: `결제 모듈에 재시도 로직 추가하고 PR까지 올려줘`

이때 내부적으로:
- `harness --mode modify --use-headless-phases --auto-pr --pr-base main "..."`을 실행
- `phase-handoff` 스킬이 Phase 사이 핸드오프 작성
- PR이 올라가면 `pr-review-triage` 스킬이 리뷰 코멘트 처리
- 세션 종료 시 Stop hook이 ruff/mypy/structure 자동 실행

#### Step 4. 결과 확인

```bash
cat .harness/artifacts/summary.json                                          # 실행 요약
cat .harness/review-artifacts/$(git branch --show-current)/pr-body.md        # PR 본문
cat .harness/review-artifacts/$(git branch --show-current)/review-comments.md # 코멘트 판정 로그
```

#### 개인 설정 오버라이드

permission을 개인 단위로 추가하고 싶으면 `.claude/settings.local.json`에 둔다. 이 파일은 gitignore되어 팀에 영향 주지 않는다.

```json
{
  "permissions": {
    "allow": ["Bash(open *)", "Bash(code *)"]
  }
}
```

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
harness-init --migrate --offline "기존 Python 서비스에 하네스 적용"

# 직접 검증
ruff check . && mypy harness && python3 scripts/check_structure.py && pytest
```

---

## 자주 묻는 질문 (FAQ)

**Q. `harness`와 `claude`(Claude Code) 중 무엇을 써야 하나?**
A. 보통은 **Claude Code 안에서 자연어로 요청**하는 게 가장 편하다. Claude가 내부에서 `harness` CLI를 적절한 옵션으로 호출하고, hook·skill이 자동 작동한다. `harness` CLI를 직접 치는 건 (1) 스크립트/CI에 박을 때, (2) 옵션을 정확히 통제하고 싶을 때다.

**Q. `create` 모드와 `modify` 모드는 어떻게 다른가?**
A. `create`(기본)는 **새 프로젝트를 처음부터** 만든다. `modify`는 **현재 코드베이스를 수정**하며, 기존 diff·ADR·컨벤션·구조 규칙·정책을 Planner 컨텍스트로 주입한다. 기존 저장소에서 작업할 때는 항상 `--mode modify`를 쓴다.

**Q. `--use-headless-phases`는 언제 꼭 써야 하나?**
A. 변경 범위가 여러 파일·여러 관심사에 걸칠 때(리팩터링, 기능 추가, 테스트 보강 동시 진행). 작은 한 줄 변경에는 굳이 필요 없다. 헤드리스 모드는 Phase별 컨텍스트 격리 덕분에 큰 작업에서 안정적이지만, 그만큼 시간이 더 걸린다.

**Q. 스킬이 자동 트리거되지 않았다. 어떻게 강제하나?**
A. 슬래시 명령 `/pr-review-triage`, `/adr-author`, `/phase-handoff`로 직접 호출하거나, 프롬프트에 트리거 키워드("ADR 작성", "리뷰 코멘트 분류" 등)를 명시한다.

**Q. 외부 프로젝트에 본 저장소의 스킬을 가져갈 수 있나?**
A. `harness-init`은 스킬을 배포하지 않는다 ([트러블슈팅](#트러블슈팅) 참조). `.claude/skills/{name}/` 디렉터리를 수동 복사한다.

**Q. PR을 만들지 않고 로컬에서만 검증하려면?**
A. `--auto-pr`을 빼면 된다. 그러면 push·PR 생성 없이 구현·평가 단계까지만 돈다.

**Q. LLM 호출 비용이 걱정된다. 어디서 끊을 수 있나?**
A. 결정적 센서(ruff → mypy → structure → pytest)가 먼저 돌고, 실패하면 AI 리뷰 단계로 가지 않는다 (ADR-0002). 또 `harness-init --offline`은 LLM을 아예 호출하지 않고 템플릿만 깔아준다.

**Q. 세션 종료 때마다 Stop hook이 도는 게 거슬린다.**
A. 일회성 우회는 `CLAUDE_HOOK_SKIP=1 claude`. 영구 비활성화는 권장하지 않지만, 정말 필요하면 `.claude/settings.local.json`에서 hooks 항목을 오버라이드한다.

**Q. 체크포인트 재개가 다른 run을 잡는다.**
A. `.harness/checkpoints/` 디렉터리에서 run_id를 확인하고 `harness --run-id <id>`로 명시한다.

---

## 트러블슈팅

| 증상 | 원인 | 대처 |
|------|------|------|
| `HARNESS_API_ENDPOINT is not set` 등 LLM 호출 에러 | 환경변수 미설정 | `export HARNESS_API_ENDPOINT=...` 또는 `--api-endpoint` 옵션 사용. 부트스트랩 미리보기는 `harness-init --offline`/`--dry-run`이라 영향 없음 |
| `--auto-pr` 실행이 PR 단계 진입 직전에 멈춤 | `gh` CLI 미인증 또는 미설치 | `gh auth login` 수행 후 재실행. 인증 상태는 `gh auth status`로 확인 |
| `docs-diff is empty` 같은 메시지로 Phase 실패 | 첫 Phase에서 문서가 갱신되지 않음 (기본 정책) | 문서 변경이 정말 필요 없는 작업이면 `--allow-empty-docs-diff` 명시. 그렇지 않으면 문서 갱신 의도를 프롬프트에 추가 |
| `[STRUCTURE VIOLATION]`으로 실행이 중단됨 | 하네스 고정 구조 필수 경로 또는 정책 package 디렉터리가 없음 | 안내된 누락 경로를 만들거나 `harness-init --migrate --offline "프로젝트 설명"`으로 보강 |
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
├── tests/                      # pytest 테스트
├── docs/
│   ├── adr/                    # ADR 0001~0012
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
│   ├── summary.json                  # 실행 요약
│   └── sprint_{N}_contract.md        # 스프린트 계약 원문
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
  package: my_app                # 루트 Python 패키지 디렉터리명
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
| [0010](docs/adr/0010-structure-enforcement.md) | 외부 프로젝트 고정 구조 강제 | modify/resume/PR 산출물 생성 전 필수 구조 게이트 |
| [0011](docs/adr/0011-harness-init-migration-mode.md) | harness-init 마이그레이션 모드 | 기존 Python 프로젝트 보강, package 기반 구조 고정 |
| [0012](docs/adr/0012-deterministic-pipeline-evaluation-gate.md) | 결정적 파이프라인 평가 게이트 | 결정적 검사와 LLM 평가가 모두 pass일 때만 최종 pass |

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
