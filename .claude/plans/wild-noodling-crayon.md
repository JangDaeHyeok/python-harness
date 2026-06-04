# 초보자 친화 CLI 별칭·문서 첫 진입면 정리

## Context

`python-harness`는 기능이 많고 CLI 표면(5개 엔트리포인트 + 다수의 전략 플래그)과
README가 복잡해 처음 쓰는 사람이 진입하기 어렵다. 고급 기능은 그대로 유지하되,
초보자가 외울 명령을 3~4개로 줄이고, 내부 아키텍처 용어(`.harness/tasks`,
`contracts`, `docs-diff`, `--use-headless-phases` 등)가 첫 화면에 노출되지 않도록 정리한다.

핵심 제약: 기존 사용법(`harness --mode modify ...`, `harness-init`, `harness-doctor`,
`auto-pr-pipeline`, `create-pr-body`)과 모든 플래그를 깨지 않는다. `harness`는 현재
서브파서 없는 flat argparse(`scripts/run_harness.py:176`)이므로, argparse **앞단에서**
`sys.argv[1]`을 가로채는 디스패치 방식으로 서브커맨드를 추가한다(`harness "프롬프트"`는
따옴표로 한 토큰이라 서브커맨드명과 절대 충돌하지 않음).

확정된 결정:
- `harness fix` = 비-headless modify 기본. docs-diff 게이트는 headless에서만 작동하므로
  기본 경로에서 작은 수정이 막히지 않는다. `--headless` opt-in 플래그로 phase 실행 허용.
- `harness pr`(새 PR 흐름) + `harness review`(현재 PR 리뷰 재처리) 둘 다 추가, 모두 `auto-pr-pipeline`에 위임.
- 개선된 완료 메시지는 create/modify/fix 모든 모드 공통 적용.

## 1. 서브커맨드 디스패치 (`scripts/run_harness.py`)

기존 `main()` 본문(argparse + orchestrator 실행, 176~350행)을 `_run_harness(argv: list[str] | None = None) -> None`로 추출하고, `main()`은 디스패치만 담당한다.

```python
_SUBCOMMANDS = {"doctor", "init", "fix", "pr", "review"}

def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in _SUBCOMMANDS:
        _dispatch_subcommand(sys.argv[1], sys.argv[2:])
        return
    _run_harness()
```

`_dispatch_subcommand(name: str, rest: list[str]) -> None` 매핑:
- `doctor` → `sys.argv=["harness-doctor",*rest]` 후 `scripts.doctor.main()` 호출(함수 내 import).
- `init`   → `sys.argv=["harness-init",*rest]` 후 `scripts.init_harness.main()`.
- `pr`     → `sys.argv=["auto-pr-pipeline",*rest]` 후 `scripts.auto_pr_pipeline.main()`.
- `review` → `rest`에 `--current-pr`/`--pr-number`가 없으면 `--current-pr`를 앞에 주입한 뒤 `auto_pr_pipeline.main()`.
- `fix`    → 아래 변환 후 `_run_harness(base)` 호출.

`fix` argv 변환 (전달 인자 passthrough 유지):
- `base = ["--mode", "modify"]`로 시작.
- `rest`를 순회하며 토큰이 `--headless`면 `["--use-headless-phases","--allow-empty-docs-diff"]`로 치환, 그 외 토큰(positional prompt, `--auto-pr` 등)은 그대로 append.
- 결과를 `_run_harness(base)`에 전달 → 기존 flat parser가 그대로 검증/실행.

`_run_harness`는 `parser.parse_args(argv)` 형태로 인자를 받도록 `argparse`의 `parse_args(argv)` 사용. `pyproject.toml`의 `[project.scripts]`는 변경 불필요(`harness = scripts.run_harness:main` 유지).

## 2. 완료 메시지 개선 (`scripts/run_harness.py`)

현재 330~336행의 `print` 블록을 `_print_completion(project_dir, summary, mode, auto_pr_enabled)` 헬퍼로 대체. scripts/는 print 허용 — harness/ 내부는 건드리지 않음.

표시 항목:
- **변경된 파일**: `_changed_files(project_dir)` 헬퍼 — `harness/tools/shell.py:run_command_safe`로 `git status --porcelain` 실행해 working-tree 변경 파일 목록 파싱(상위 5개 + "외 N개"). git 실패 시 빈 목록 폴백(예외 전파 금지).
- **검증 결과**: `summary["passed_sprints"]/summary["total_sprints"]` 통과 표시. 전부 통과면 "품질 검증(ruff·mypy·pytest·구조) 통과" 한 줄.
- **비용/소요 시간**: 기존 `total_cost_usd`, `elapsed_human` 유지.
- **다음에 볼 파일**: 변경 파일 중 상위 1개.
- **다음 명령**: `--auto-pr` 미사용이고 통과 스프린트>0이면 `harness pr` 안내 + `git diff` 안내. modify/fix면 동일.
- **내부 산출물**: `.harness/tasks`·`contracts`·`docs-diff`는 기본 미노출. headless 실행(`config.use_headless_phases`)일 때만 `.harness/tasks/...` 경로 1줄 안내, `-v` 시 `.harness/artifacts/summary.json` 안내.

`_run_auto_pr`의 출력(154~169행)은 유지하되, 완료 메시지가 그 앞에 오도록 순서 유지.

## 3. README 첫 화면 재정리 (`README.md`)

상단을 "처음 쓰는 사람" 기준으로 압축:
- 한 문단 소개 유지(현 1~5행).
- 신설 **"빠른 시작"** 섹션을 목차 직후 최상단에 배치, 명령 4개만 노출:
  ```
  harness doctor                 # 사전 점검
  harness init "프로젝트 설명"     # 부트스트랩(ADR·컨벤션·구조 규칙)
  harness fix "수정 요청"          # 현재 프로젝트 수정
  harness pr                     # PR 생성 → 리뷰 반영
  ```
  + `harness review`(현재 PR 리뷰 재처리) 한 줄 보조 안내.
- 기존 "어떤 명령을 써야 하나요?" 의사결정 매트릭스, "CLI 옵션 상세", 시나리오 레시피, FAQ/트러블슈팅은 **하단 "고급 사용" 영역으로 이동**하거나 `docs/operations.md` 링크로 대체. `--use-headless-phases`/`--allow-empty-docs-diff`/`--headless-phase-timeout` 등 전략 플래그는 첫 화면에서 제거하고 "고급 옵션"으로 분리.
- 첫 화면에는 내부 아키텍처 용어(3-에이전트/센서/계약/docs-diff/Phase) 노출 최소화 — "핵심 개념"은 하단 섹션 링크로.

## 4. operations 문서 보강 (`docs/operations.md`)

- 2장 `harness` 명령 표에 서브커맨드 행 추가: `doctor`/`init`/`fix`/`pr`/`review`와 각 위임 대상·기본값 명시.
- `fix`의 `--headless` opt-in이 내부적으로 `--use-headless-phases --allow-empty-docs-diff`로 매핑됨을 설명.
- `--use-headless-phases`/`--allow-empty-docs-diff`/`--headless-phase-timeout`을 "고급 전략 옵션" 소절로 묶어 의미·기본값 정리(기존 3장 헤드리스 운영과 교차 링크).

## 5. CLAUDE.md 요약 갱신 (`CLAUDE.md`)

"자주 쓰는 명령 (요약)" 블록에 새 별칭 4~5개 반영(기존 raw 명령은 "전체 옵션은 operations 참조" 유지). 의미 변경 없음.

## 변경 대상 파일

- `scripts/run_harness.py` — 디스패치 + `fix` 변환 + `_print_completion`/`_changed_files` (핵심).
- `README.md` — 첫 화면 재정리.
- `docs/operations.md` — 서브커맨드·고급 옵션 문서화.
- `CLAUDE.md` — 자주 쓰는 명령 요약 갱신.
- `tests/` — 아래 테스트 추가/갱신.

재사용: `harness/tools/shell.py:run_command_safe`(git 호출), 기존 `_run_auto_pr`/`_resolve_project_dir`/`enforce_structure_gate`는 그대로 사용. 신규 헬퍼/함수에는 타입 힌트 필수.

## 테스트

- `tests/`에서 run_harness 완료 출력에 대한 기존 assert 유무를 grep(`grep -rn "실행 완료" tests`)하여 깨지면 갱신.
- 신규 단위 테스트:
  - `_dispatch_subcommand`가 각 서브커맨드를 올바른 모듈 `main`으로 라우팅(monkeypatch로 위임 대상 mock, `sys.argv` 검증).
  - `fix` 변환: `["fix","요청"]` → `_run_harness`가 `--mode modify` + positional "요청"으로 호출됨. `--headless` → headless+allow-empty-docs-diff 치환 검증.
  - `review`가 `--current-pr` 주입, `--pr-number` 지정 시 미주입.
  - `_changed_files` git 실패 시 빈 목록 폴백.
- 기존 `harness --mode modify ...` 플로우가 그대로 동작하는지 회귀 테스트 확인.

## 검증 (구현 후 실행)

```
ruff check .
mypy harness
python3 scripts/check_structure.py
pytest
```

수동 확인:
- `harness doctor` → `harness-doctor`와 동일 출력.
- `harness fix "..."` (mock LLM/소규모) → modify 모드, docs-diff 게이트 미적용, 개선된 완료 메시지(변경 파일/검증/다음 명령) 출력.
- `harness --mode modify "..."` 기존 사용법 동작 무변화.
- `harness pr`, `harness review` → `auto-pr-pipeline` 동작과 일치(review는 현재 PR 대상).
