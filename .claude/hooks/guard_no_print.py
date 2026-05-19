#!/usr/bin/env python3
"""PreToolUse hook: harness/ 내부 파일에 print() 작성 시도를 차단한다.

CLAUDE.md의 CRITICAL 규칙: harness/ 내부에서 print() 금지, logging 사용.
모델이 규칙을 잊더라도 결정적으로 강제한다.

stdin으로 PreToolUse 이벤트 JSON을 받는다. 형식 (Claude Code 명세):
{
  "tool_name": "Write" | "Edit",
  "tool_input": {
    "file_path": "...",
    "content": "..." | "new_string": "..."
  }
}

차단 조건:
- file_path가 저장소 내 harness/ 하위
- 그리고 작성 내용(또는 신규 문자열)에 '^\\s*print\\(' 패턴이 존재

차단 시 exit code 2로 reason을 stderr로 남긴다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PRINT_PATTERN = re.compile(r"^\s*print\(", re.MULTILINE)


def _is_harness_path(file_path: str) -> bool:
    if not file_path:
        return False
    parts = Path(file_path).resolve().parts
    # Claude 훅은 repo root 정보를 안정적으로 주지 않으므로 세그먼트 기반으로
    # 판정한다. 이 저장소 안에서 쓰는 단순 가드이며, 중첩 harness 디렉터리도
    # 동일한 정책 대상으로 본다.
    return "harness" in parts and not any(
        seg.startswith(".") for seg in parts if seg != "harness"
    )


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    tool_name = event.get("tool_name", "")
    if tool_name not in {"Write", "Edit", "MultiEdit"}:
        return 0

    tool_input = event.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "")
    if not _is_harness_path(file_path):
        return 0

    # 테스트 코드와 hook 자체는 print 사용 허용.
    if "/tests/" in file_path or file_path.endswith("guard_no_print.py"):
        return 0

    candidates: list[str] = []
    for key in ("content", "new_string"):
        value = tool_input.get(key)
        if isinstance(value, str):
            candidates.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for item in edits:
            new_string = item.get("new_string") if isinstance(item, dict) else None
            if isinstance(new_string, str):
                candidates.append(new_string)

    for text in candidates:
        if PRINT_PATTERN.search(text):
            sys.stderr.write(
                "[hook] harness/ 내부에서 print() 사용 금지. logging 모듈을 사용하세요.\n"
                f"  대상: {file_path}\n"
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
