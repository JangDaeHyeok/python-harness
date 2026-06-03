# Operations Guide

루트 `CLAUDE.md`에서 분리한 운영 가이드. 실행 명령, 옵션, 자동화 운영 정책을 한 곳에 모았다.

## 1. 설치

```bash
pip install -e ".[dev]"
```

## 2. 명령어 레퍼런스

### `harness` (= `python3 scripts/run_harness.py`)
| 사용법 | 의미 |
|--------|------|
| `harness --help` | 전체 옵션 확인 |
| `harness "프롬프트"` | create 모드: 새 프로젝트 생성 |
| `harness --mode modify "수정 요청"` | modify 모드: 현재 코드베이스 수정 |
| `harness --mode modify --use-headless-phases "수정 요청"` | Phase별 `claude --print` 실행 |
| `harness --mode modify --use-headless-phases --allow-empty-docs-diff "..."` | 문서 변경이 없는 예외 작업 |
| `harness --mode modify --use-headless-phases --auto-pr --pr-base main "..."` | 구현 → PR → 리뷰 반영. 팀 allow 밖 GitHub 쓰기(리뷰 답글/머지)는 건너뜀 |
| `harness --mode modify --auto-pr --pr-number 123 --pr-no-poll "..."` | 새 PR 생성 없이 기존 PR #123 리뷰 처리 |
| `harness --mode modify --auto-pr --pr-current-pr --pr-no-poll "..."` | 현재 브랜치에 연결된 기존 PR 리뷰 처리 |
| `harness --mode modify --use-headless-phases --auto-pr --pr-title "제목" "..."` | 새 PR 제목 직접 지정 |
| `harness --mode modify --use-headless-phases --auto-pr --pr-base main --pr-confirm-github-writes "..."` | 리뷰 답글까지 명시 승인 |
| `harness --mode modify --use-headless-phases --auto-pr --pr-base main --pr-auto-merge --pr-confirm-github-writes "..."` | 답글과 머지까지 명시 승인 |
| `harness --resume` | 현재 디렉터리 체크포인트 재개 |
| `harness --run-id <run_id>` | 특정 체크포인트 재개 |

### `create-pr-body` (= `python3 scripts/create_pr_body.py`)
| 사용법 | 의미 |
|--------|------|
| `create-pr-body --help` | 전체 옵션 |
| `create-pr-body --base main` | PR 본문 생성 (stdout) |
| `create-pr-body --base main --output pr-body.md` | 파일 저장 |
| `create-pr-body --base main --summary "요약" --branch feature/x` | 요약·브랜치 오버라이드 |
| `create-pr-body --base main --use-worktree` | worktree 격리 실행 |

### `auto-pr-pipeline` (= `python3 scripts/auto_pr_pipeline.py`)
| 사용법 | 의미 |
|--------|------|
| `auto-pr-pipeline --help` | 전체 옵션 |
| `auto-pr-pipeline --base main` | PR 자동화 파이프라인. 리뷰 답글/머지는 승인 필요 단계로 건너뜀 |
| `auto-pr-pipeline --base main --confirm-github-writes` | 리뷰 답글(`gh api --method POST`)까지 명시 승인 |
| `auto-pr-pipeline --base main --auto-merge --confirm-github-writes` | 리뷰 반영 후 자동 머지까지 명시 승인 |
| `auto-pr-pipeline --base main --skip-review` | 리뷰 수집/반영 건너뛰기 |
| `auto-pr-pipeline --pr-number 123 --no-poll` | 이미 열린 PR #123의 리뷰 코멘트만 처리 |
| `auto-pr-pipeline --current-pr --no-poll` | 현재 브랜치에 연결된 기존 PR 리뷰 코멘트 처리 |
| `auto-pr-pipeline --base main --title "PR 제목" --no-poll` | 제목 지정, 폴링 비활성화 |

### `harness-init` (= `python3 scripts/init_harness.py`)
| 사용법 | 의미 |
|--------|------|
| `harness-init --help` | 전체 옵션 |
| `harness-init --offline "사내 청구 자동화 도구"` | 자연어 의도로 ADR/컨벤션/구조/정책 일괄 생성 |
| `harness-init --project-dir ./billing --offline "PoC"` | 다른 디렉터리 부트스트랩 |
| `harness-init --only adr,policy --offline "데이터 파이프라인"` | 특정 항목만 |
| `harness-init --only claude-config --offline "팀 셋업만 배포"` | `.claude/settings.json` + Stop 훅 |
| `harness-init --with-coderabbit --offline "GitHub 리뷰 자동화"` | `.coderabbit.yaml` 템플릿도 함께 생성 |
| `harness-init --only coderabbit --offline "GitHub 리뷰 자동화"` | CodeRabbit 설정 파일만 생성 |
| `harness-init --force --only claude --offline "운영 가이드 갱신"` | 덮어쓰기 |
| `harness-init --dry-run --offline "사전 검토"` | 미리보기 |
| `harness-init --migrate --offline "기존 Python 서비스"` | 기존 프로젝트의 하네스 필수 구조 보강 |
| `harness-init --scaffold --offline "새 Python 도구"` | 규칙 파일 + Python 골격(pyproject/패키지/테스트/.gitignore/CI) 함께 생성 |
| `harness-init --only pyproject,ci --offline "..."` | 골격 중 특정 파일만 생성 |

### `harness-doctor` (= `python3 scripts/doctor.py`)
| 사용법 | 의미 |
|--------|------|
| `harness-doctor` | 현재 디렉터리의 GitHub/Python 준비 상태 점검 |
| `harness-doctor --project-dir ./billing` | 다른 디렉터리 점검 |
| `harness-doctor --api-endpoint https://...` | API 엔드포인트 설정까지 함께 점검 |

### 스크립트 직접 실행
| 사용법 | 의미 |
|--------|------|
| `python3 scripts/run_phases.py --sprint 1` | Phase별 헤드리스 실행 |
| `python3 scripts/run_phases.py --sprint 1 --require-docs-diff` | docs-update 이후 docs-diff 필수 |
| `ruff check .` | 린트 |
| `mypy harness` | 타입 체크 (strict) |
| `pytest` | 테스트 |
| `python3 scripts/check_structure.py` | 구조 분석 |

## 3. 헤드리스 Phase 운영
- `--use-headless-phases`는 오케스트레이터가 Generator 직접 호출 대신 `scripts/run_phases.py`를 사용하게 한다.
- 기본 정책: 첫 Phase에서 문서가 업데이트되어 docs-diff가 생겨야 한다. 예외는 `--allow-empty-docs-diff`로 명시.
- Phase 프롬프트에는 입력 파일, 변경 허용 범위, 기대 산출물, 검증 방법, 핸드오프 요구사항이 포함된다.
- 각 Phase는 `.harness/tasks/sprint-{N}/{phase_id}-handoff.md`(20줄 이내)에 다음 Phase용 요약을 남긴다.
- Phase 실행 후 handoff 파일이 없거나, 20줄을 초과하거나, `결정적 파이프라인 결과:` 라인이 없으면 해당 Phase는 failed가 된다.
- Phase 실행 중 현재 Phase의 런타임 산출물과 `allowed_files` 범위 밖 파일이 새로 변경되면 failed가 되며 후속 Phase는 진행되지 않는다.
- 재시도 시 완료되지 않은 Phase만 pending으로 되돌리고, done Phase는 재실행하지 않는다.
- 자세한 동작은 `harness/context/CLAUDE.md`와 `docs/adr/0009-phase-execution-and-context-isolation.md`.

## 4. PR 자동화 운영
- `run_harness.py --auto-pr` 사용 시 구현 성공 후 PR 파이프라인을 이어 실행한다.
- `--pr-base`, `--pr-title`, `--pr-number`, `--pr-current-pr`, `--pr-no-poll`, `--pr-skip-review`, `--pr-auto-merge`, `--pr-confirm-github-writes`로 동작 제어. 통과 스프린트가 0개면 PR 단계를 건너뛴다.
- PR 파이프라인 실패는 구현 결과에 영향을 주지 않는다(구현 성공/ PR 실패는 분리 기록). PR 결과는 `.harness/artifacts/auto-pr-result.json`에 `{pr_url, review_applied, merged, warnings, errors}` 형태로 저장되고, 오류는 stdout에도 눈에 띄게 출력된다.
- `--fail-on-pr-error`: 구현이 성공해도 PR 파이프라인이 중단되거나 오류를 기록하면 종료 코드 1로 끝낸다. CI에서 PR 단계 실패를 감지하려는 경우 사용한다.
- `scripts/auto_pr_pipeline.py`는 단독 실행 가능: 현재 브랜치 push → PR 생성 → 리뷰 수집 → 리뷰 반영까지 기본 수행한다. 리뷰 답글(`gh api --method POST`)과 선택적 머지(`gh pr merge`)는 `--confirm-github-writes`가 있을 때만 실행한다.
- 기존 PR은 단독 파이프라인에서 `--pr-number <N>` 또는 `--current-pr`로, `harness --auto-pr`에서는 `--pr-number <N>` 또는 `--pr-current-pr`로 새 PR 생성 없이 처리한다.
- 리뷰 코멘트 판정: `ACCEPT` / `DEFER` / `IGNORE`. 명확한 bug/failure/regression/security/type error/필수 동작 누락만 `ACCEPT`하고, optional/nit/style/consider/could 제안은 `DEFER`한다. 파일/라인 존재만으로는 `ACCEPT`하지 않는다.
- 키워드 매칭은 단어 경계 기준이라 `debug`/`bugfix done` 같은 부분일치는 ACCEPT로 오분류되지 않는다. CodeRabbit 본문의 `⚠️ Potential issue`/`_critical_`는 ACCEPT, `🧹 Nitpick`/`🛠️ Refactor`는 DEFER 가중 신호로 쓴다. `author_association`(MEMBER/OWNER/COLLABORATOR)은 신뢰 가중으로 사유에만 기록하며 단독으로 ACCEPT를 만들지 않는다.
- `ACCEPT`만 `claude --print` 리뷰 반영 세션에 전달하며, 리뷰 본문은 신뢰할 수 없는 외부 입력으로 fenced block에 격리한다.
- 판정 로그: `.harness/review-artifacts/{branch}/review-comments.md`.
- 리뷰 반영 전 dirty worktree가 있으면 실패한다. 반영 커밋은 자동화 중 변경된 파일만 stage한다. 원본 리뷰 코멘트 한국어 답글은 성공적으로 push되고 `--confirm-github-writes`가 명시된 경우에만 남긴다.
- GitHub review thread resolve는 답글 기반 확인으로 대체한다.
- CodeRabbit은 외부 리뷰어로 취급, 인라인 코멘트도 동일하게 수집·분류·반영한다.
- CodeRabbit 자동 검증은 GitHub App 설치 + `gh` CLI 인증이 전제다.
- optional/nit/칭찬성 CodeRabbit 코멘트는 DEFER로 남기고 자동 반영하지 않는다.
- 자세한 동작은 `harness/review/CLAUDE.md`.

## 4.1 modify 컨텍스트의 Python 프로젝트 요약
- modify 모드는 외부 Python 프로젝트에서 `pyproject.toml`, `requirements*.txt`, `setup.py`, `uv.lock`, `poetry.lock`, `Pipfile` 존재 여부를 요약한다.
- package manager(`uv`, `poetry`, `pipenv`, `pip`, `pyproject`, `setuptools`)와 `src`/flat 레이아웃, pydantic v1/v2, requests/httpx, click/typer/argparse, pytest/unittest 힌트, 최근 git commit 메시지 일부를 짧게 포함한다.
- 비밀값과 환경변수 값은 수집하지 않고, 의존성·import 이름 중심의 요약만 Planner 컨텍스트에 전달한다.

## 5. 프로젝트 부트스트랩(harness-init) 운영
- 새 프로젝트나 외부 프로젝트에 하네스 규칙 파일을 한 번에 배치하는 용도.
- 대상 파일: `docs/adr/0001-initial-architecture.md`, `docs/code-convention.yaml`, `harness_structure.yaml`, `.harness/project-policy.yaml`, `CLAUDE.md`, `.claude/settings.json`, `.claude/hooks/post_session_checks.sh`.
- 자연어 프롬프트로 프로젝트 의도를 전달하면 ADR/CLAUDE.md 요약에 반영된다.
- 기본 동작: 누락 파일만 생성, 기존 파일은 보존(`--force`로 덮어쓰기).
- `--only`로 특정 항목(`adr,convention,structure,policy,claude,claude-config,coderabbit`)만 생성·관리.
- CodeRabbit 설정은 선택 사항이다. `--with-coderabbit` 또는 `--only coderabbit`을 쓰면 `.coderabbit.yaml`을 생성한다. `--with-coderabbit`는 `--only` 목록에 `coderabbit`를 추가하는 동작과 같다.
- `--with-coderabbit` 사용 시 기존 `.harness/project-policy.yaml`이 있어도 `policies.review_tools.coderabbit` 플래그를 `true`로 자동 동기화한다. 다른 키/주석은 보존된다.
- `.coderabbit.yaml`의 `knowledge_base.code_guidelines`로 인해 `CLAUDE.md`, `docs/adr/*.md`, `.harness/project-policy.yaml`이 CodeRabbit(third-party SaaS)으로 전송된다. 사내 정보 포함 여부를 검토한 뒤 사용한다.
- `harness-init`은 CodeRabbit GitHub App을 설치하지 않는다. 저장소 설정에서 App 설치와 권한 승인을 별도로 완료해야 PR 리뷰가 실행된다.
- 생성/마이그레이션되는 `harness_structure.yaml`의 `no_print_debug`는 `severity: error`다. 외부 프로젝트에 `guard_no_print.py` PreToolUse 훅을 배포하지 않더라도 `python3 scripts/check_structure.py`와 Stop 훅의 structure 단계에서 `print()` 디버깅이 실패로 처리된다.
- `claude-config`는 보안 설정이므로 LLM에 위임하지 않고 결정적 템플릿을 사용한다. 이 대상은 `.claude/settings.json`과 Stop 훅 스크립트를 함께 생성하며, 두 파일은 각각 별도 `BootstrapPlan` 항목으로 요약에 노출된다. 쓰기 순서는 sidecar hook → `settings.json` 순이라 중간 실패가 발생해도 다음 실행이 fresh 경로로 깔끔히 복구된다. 기존 `settings.json`이 있어도 Stop 훅 스크립트가 누락되었으면 sidecar hook만 복구한다.
- `.claude/settings.json` allow 목록은 좁힌 패턴만 사용한다. `pip install *` 같은 와일드카드와 `gh pr *`/`gh api *` 무제약 패턴은 금지하고, `gh pr view/list/diff/status/checks/comment/create *`만 허용한다. `gh api repos/*`도 HTTP 메서드 플래그로 쓰기 요청이 가능하므로 팀 공유 allow에서는 제외한다. destructive 서브명령(`gh pr merge|close|reopen|edit`)은 일부러 빼고 사용자 확인을 거치게 한다. `python scripts/*` allow가 이 경계를 우회하지 않도록 `--confirm-github-writes`/`--pr-confirm-github-writes`가 붙은 PR 파이프라인 실행은 deny에 둔다.
- 부트스트랩 Stop 훅은 fresh 프로젝트에서 실패하지 않도록 설치된 도구와 존재하는 파일만 검사한다. `scripts/check_structure.py`나 `tests/`가 없으면 해당 단계는 건너뛰고, `pytest`가 수집한 테스트가 0건(exit 5)이면 성공으로 간주한다.
- `--dry-run`은 쓰기 없이 결과 미리보기.
- LLM 엔드포인트(`HARNESS_API_ENDPOINT`)가 설정되어 있고 `--offline`이 아니면 LLM이 템플릿을 사용자 의도에 맞게 다듬는다.
- LLM 호출 실패나 응답 검증 실패 시 내장 템플릿으로 안전 폴백.
- 프로젝트 이름은 따옴표로 감싼 토큰을 우선, 없으면 디렉터리명을 정규화.
- `harness-init`은 초기 환경 구성용. 본격 수정·생성은 `harness` CLI 사용.
- `--scaffold`는 규칙 파일 외에 Python 프로젝트 골격(`pyproject.toml`, `<package>/__init__.py` 또는 `src/<package>/__init__.py`, `tests/test_smoke.py`, `.gitignore`, `.github/workflows/ci.yml`)을 함께 생성한다. `--only pyproject,ci`처럼 골격 일부만 지정할 수도 있다. CI 템플릿의 검사 명령은 정책(`ruff check .`, `mypy {package_dir}`, structure, pytest)과 일치하며, 기존 파일은 보존하고 `--force`로만 덮어쓴다.
- src 레이아웃: 정책 `project.source_root: src`가 있으면 골격·구조 규칙·검증 명령이 모두 `src/<package>` 경로를 사용한다. `--migrate`는 루트와 `src/<package>`를 자동 탐지해 단일 후보면 `source_root`를 정책에 기록하고, 양쪽에 후보가 동시에 있으면 명시를 요구한다. 정책에 `source_root`가 이미 명시돼 있으면 해당 root만 탐색해 자동 탐지보다 우선하므로, 루트·src에 같은 패키지가 함께 있어도 명시 값이 유지된다. 자세한 결정은 `docs/adr/0014-src-layout-and-source-root.md`.

## 5.1 사전 점검(harness-doctor) 운영
- 하네스 실행 전 GitHub/Python 준비 상태를 점검하고, 실패 항목마다 한국어 원인 + 다음 조치를 출력한다.
- 점검 항목: git 저장소·origin 원격·현재 브랜치·기본(base) 브랜치, `git`/`gh`/`ruff`/`mypy`/`pytest`/`claude` 설치, `gh` 인증, `HARNESS_API_ENDPOINT` 설정, `.harness/project-policy.yaml`/`harness_structure.yaml`/`docs/code-convention.yaml`/`docs/adr/*.md` 존재.
- 현재 브랜치 점검은 detached HEAD 상태(브랜치가 아님)를 실패로 처리한다. PR 자동화는 실제 브랜치를 요구하므로 작업 전에 체크아웃/생성하도록 안내한다.
- 실패가 하나라도 있으면 종료 코드 1로 끝난다(CI 사전 게이트로 사용 가능).
- 점검에 쓰는 git/gh 호출은 읽기 전용(`git remote`, `git rev-parse`, `gh auth status`)만 허용된다.

## 6. 프로젝트 정책 파일(`.harness/project-policy.yaml`)
- 파일이 없거나 파싱 실패 시 기본 정책 사용.
- 기본 필수 검사: `ruff`, `mypy`, `pytest`, `structure`.
- Python 검증 설정 예시:
  `commands.lint: ruff check .`, `commands.type: mypy harness`,
  `commands.test: pytest`, `commands.structure: python3 scripts/check_structure.py`,
  `min_coverage: 80`, `package_manager: pip`,
  `pytest: {timeout: 300, coverage: true}`.
- `project.source_root`(예: `src`)로 패키지 레이아웃을 표현한다. 빈 값은 flat 루트(`<package>/`), `src`는 `src/<package>/`를 의미하며 구조 게이트·Phase·검증 명령이 이 값을 따른다.
- 정책 입력은 신뢰 대상이 아니다. `harness-init`은 `source_root`/`package`로 파생되는 모든 쓰기 경로를 `validate_path`로 검증하며, 프로젝트 디렉터리를 벗어나는 값(`../`, 절대경로 등)은 거부한다.
- modify 모드의 검증 요약은 `commands.lint`/`commands.type`를 사용한다. 정책이 없으면 `ruff check .`/`mypy <package_dir>`로 폴백하고, allowlist 밖 명령(ruff/mypy/pytest/python 외)은 안전하게 생략한다.
- 기본 문서 경로: `docs/code-convention.yaml`, `docs/adr/`, `harness_structure.yaml`.
- `custom_rules`는 `type`, `pattern`, `message` 등을 가진 목록이며 LinterSensor까지 전달된다.
- `adr.external_sources`로 외부 프로젝트 ADR 디렉터리 지정 가능. 존재하지 않거나 디렉터리가 아니면 건너뜀(오류 없음).
- 외부 ADR은 modify 컨텍스트, GuideRegistry, ContextFilter 모두에 반영.
- 정책 파일에는 토큰·비밀값·개인 계정 정보를 넣지 않는다.
- 정책 변경 후 검증: `ruff check . && mypy harness && python3 scripts/check_structure.py && pytest`.

## 7. 체크포인트
- `.harness/checkpoints/{run_id}.json` — 실행별 체크포인트.
- `.harness/checkpoints/latest.json` — 최근 실행 포인터.
- `--project-dir` 없이 `--resume`/`--run-id` 사용 시 현재 디렉터리에 체크포인트가 있으면 현재 디렉터리의 modify 실행으로 재개.

## 8. 리뷰 산출물 경로
- `.harness/review-artifacts/{branch}/design-intent.md` — 설계 의도
- `.harness/review-artifacts/{branch}/code-quality-guide.md` — 평가 기준
- `.harness/review-artifacts/{branch}/pr-body.md` — PR 본문
- `.harness/review-artifacts/{branch}/review-comments.md` — 리뷰 반영 판단 로그
- `.harness/review-artifacts/{branch}/docs-diff-sprint{N}.md` — docs-diff (스펙 변경 추적)

## 9. Task/Phase 경로
- `.harness/tasks/sprint-{N}/task-index.json`
- `.harness/tasks/sprint-{N}/phase-{NN}-{name}.md`
- `.harness/tasks/sprint-{N}/docs-diff.md`
- `.harness/tasks/sprint-{N}/phase-{NN}-{name}-handoff.md`

## 10. 계약 저장 경로
- `.harness/contracts/sprint_{N}.json` — 스프린트별 구조화 계약(JSON)
