#!/usr/bin/env bash
# Stop hook: ruff → mypy → 구조 분석을 결정적으로 강제한다.
#
# 호출 환경:
#   - cwd는 사용자가 실행한 위치라 보장이 없다. 저장소 루트를 hook 파일 위치 기준으로 계산한다.
#   - 자동화/CI 환경에서는 hook 무한 루프를 피하기 위해 CLAUDE_HOOK_SKIP=1로 우회할 수 있다.
#
# 실패 시 exit code 2를 반환하여 Claude에게 위반 사실을 인지시킨다.

set -u

if [[ "${CLAUDE_HOOK_SKIP:-0}" == "1" ]]; then
  exit 0
fi

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
cd "$REPO_ROOT" || exit 0

# 가상환경 또는 시스템 파이썬을 사용한다. CI에서는 python3가 보장된다.
PYTHON_BIN="${PYTHON_BIN:-python3}"

print_section() {
  printf '\n=== %s ===\n' "$1"
}

failed=0

print_section "ruff check ."
if ! "$PYTHON_BIN" -m ruff check . 2>&1; then
  failed=1
fi

print_section "mypy harness"
if ! "$PYTHON_BIN" -m mypy harness 2>&1; then
  failed=1
fi

print_section "structure"
if ! "$PYTHON_BIN" scripts/check_structure.py 2>&1; then
  failed=1
fi

if [[ "$failed" -ne 0 ]]; then
  printf '\n[hook] CRITICAL 검증 실패. 위 출력의 위반 사항을 수정한 뒤 다시 시도하세요.\n' >&2
  exit 2
fi

exit 0
