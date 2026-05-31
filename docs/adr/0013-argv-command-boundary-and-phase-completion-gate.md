# ADR-0013: argv 명령 경계와 Phase 완료 게이트

- **상태**: Accepted
- **날짜**: 2026-05-27
- **관련 ADR**: ADR-0002, ADR-0009, ADR-0012

## 배경

하네스는 외부 도구(`git`, `ruff`, `mypy`, `pytest`, `gh`, `claude`)를 많이 호출한다.
문자열 기반 `shell=True` 실행이 퍼지면 위험 명령 차단, timeout, stdout/stderr 캡처, 실패 메시지 형식이 호출 지점마다 달라진다.
또한 headless Phase 프롬프트는 handoff와 변경 허용 범위를 요구하지만, 실행기가 이를 결정적으로 검증하지 않으면 규칙이 안내문에 머문다.

## 결정

`harness/tools/shell.py`에 argv 기반 안전 실행 경계를 둔다.
새 외부 명령 호출은 `run_argv_safe()`를 기본으로 사용하고, 기존 문자열 명령 호환 경로도 `shlex.split()` 후 같은 경계를 통과한다.
headless Phase 실행기는 각 Phase 이후 handoff 존재, 20줄 이하, `결정적 파이프라인 결과:` 라인, `allowed_files` 밖 변경 여부를 검증한다.

## 대안

- 기존 `subprocess.run` 호출을 유지한다: 호출 지점별 정책 차이가 계속 생겨 채택하지 않는다.
- `shell=True` 문자열을 더 강하게 필터링한다: 인용과 셸 문법 해석 위험이 남아 채택하지 않는다.
- Phase 규칙을 프롬프트에만 둔다: 결정적 실패 처리가 불가능해 채택하지 않는다.

## 결과

- 긍정적 결과: 핵심 외부 도구 실행의 timeout, 캡처, 오류 표현이 공통화된다.
- 긍정적 결과: Phase handoff와 변경 범위 위반이 즉시 failed로 전환되어 후속 Phase 진행을 막는다.
- 트레이드오프: 기존 dirty worktree와 Phase 런타임 산출물을 구분하기 위한 git 상태 스냅샷 비용이 Phase마다 추가된다.
- 후속 조치: 남아 있는 직접 `subprocess.run` 호출도 테스트 가능한 경로부터 점진적으로 `run_argv_safe()`로 이동한다.

## 검증 방법

- `tests/test_run_phases.py`에서 handoff 누락, 20줄 초과, 필수 라인 누락, 허용 범위 밖 변경을 실패로 검증한다.
- `ruff check .`, `mypy harness`, `python3 scripts/check_structure.py`, `pytest`가 모두 통과해야 한다.
