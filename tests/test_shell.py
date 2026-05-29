"""셸 안전 래퍼 테스트."""

from __future__ import annotations

import shlex
import sys

from harness.tools.shell import run_command_safe, validate_argv, validate_command


def test_validate_command_allows_safe_development_commands() -> None:
    """검증/개발용 명령은 계속 허용한다."""
    allowed = [
        "ruff check .",
        "mypy harness",
        "pytest",
        "python3 scripts/check_structure.py",
        "python3 -m pytest",
        "git status --short",
        "find . -name '*.py'",
    ]

    for command in allowed:
        is_safe, reason = validate_command(command)

        assert is_safe, reason


def test_validate_command_blocks_destructive_commands() -> None:
    """프로젝트를 파괴하거나 임의 코드를 실행할 수 있는 명령은 차단한다."""
    blocked = [
        "git reset --hard",
        "rm -rf .",
        "find . -delete",
        "mv harness /tmp/harness",
        "cp -R . /tmp/project-copy",
        "python3 -c 'import pathlib; pathlib.Path(\"x\").unlink()'",
        "python3 -m http.server",
        "bash -c 'pytest'",
    ]

    for command in blocked:
        is_safe, reason = validate_command(command)

        assert not is_safe, command
        assert reason


def test_validate_command_rejects_shell_control_tokens() -> None:
    """문자열 명령의 셸 제어 연산자는 argv 실행에서도 차단한다."""
    blocked = [
        "ruff check . && mypy harness",
        "pytest ; git status",
        "python3 scripts/check_structure.py | cat",
    ]

    for command in blocked:
        is_safe, reason = validate_command(command)

        assert not is_safe, command
        assert "셸 제어 토큰" in reason


def test_validate_argv_uses_same_policy_as_string_commands() -> None:
    """argv API도 동일한 allowlist/denylist 정책을 적용한다."""
    is_safe, reason = validate_argv(["python3", "scripts/check_structure.py"])
    assert is_safe, reason

    is_safe, reason = validate_argv(["python3", "-c", "1 + 1"])
    assert not is_safe
    assert "임의 코드 실행" in reason


def test_run_command_safe_does_not_execute_blocked_python_code(
    tmp_path,
) -> None:
    """차단된 명령은 subprocess 실행 전에 실패한다."""
    result = run_command_safe(
        "python3 -c 'raise SystemExit(99)'",
        str(tmp_path),
    )

    assert "Error:" in result
    assert "임의 코드 실행" in result


def test_run_command_safe_executes_argv_without_shell(tmp_path) -> None:
    """허용된 명령은 shell 없이 argv로 실행된다."""
    python = shlex.quote(sys.executable)

    result = run_command_safe(f"{python} --version", str(tmp_path))

    assert "Return code: 0" in result
