"""셸 안전 래퍼 테스트."""

from __future__ import annotations

import shlex
import subprocess
import sys

from harness.tools.shell import (
    resolve_safe_path,
    run_command_safe,
    run_git_commit_safe,
    validate_argv,
    validate_command,
    validate_http_url,
)


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


def test_validate_command_allows_doctor_read_only_commands() -> None:
    """doctor가 쓰는 읽기 전용 git/gh 명령은 허용한다."""
    allowed = [
        "git remote",
        "git rev-parse --abbrev-ref origin/HEAD",
        "gh auth status",
    ]

    for command in allowed:
        is_safe, reason = validate_command(command)

        assert is_safe, reason


def test_validate_command_blocks_mutating_remote_and_gh() -> None:
    """git remote 변경 액션과 비인증 gh 명령은 차단한다."""
    blocked = [
        "git remote add origin https://example.invalid/x.git",
        "git remote set-url origin https://example.invalid/y.git",
        "gh pr create",
        "gh auth login",
        "gh auth token",
        "gh auth status --show-token",
    ]

    for command in blocked:
        is_safe, _ = validate_command(command)

        assert not is_safe, command


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


def test_resolve_safe_path_returns_normalized_path(tmp_path) -> None:
    """검증에 성공하면 정규화된 절대 경로를 반환한다."""
    resolved, reason = resolve_safe_path("sub/file.txt", tmp_path)

    assert reason == ""
    assert resolved == (tmp_path / "sub" / "file.txt").resolve()


def test_resolve_safe_path_blocks_traversal(tmp_path) -> None:
    """상위 경로 탈출은 차단하고 None을 반환한다."""
    resolved, reason = resolve_safe_path("../outside.txt", tmp_path)

    assert resolved is None
    assert "프로젝트 디렉터리 밖" in reason


def test_resolve_safe_path_blocks_symlink_escape(tmp_path) -> None:
    """프로젝트 밖을 가리키는 심볼릭 링크를 통한 접근을 차단한다."""
    outside = tmp_path.parent / "outside_target"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    link.symlink_to(outside)

    resolved, reason = resolve_safe_path("link/secret.txt", tmp_path)

    assert resolved is None
    assert "프로젝트 디렉터리 밖" in reason


def test_validate_http_url_allows_local_and_remote_http() -> None:
    """로컬 앱 평가 용례(localhost/사설망)와 일반 http/https는 허용한다."""
    for url in [
        "http://localhost:3000",
        "http://127.0.0.1:8080/health",
        "http://192.168.0.10/api",
        "https://example.com/status",
    ]:
        is_safe, reason = validate_http_url(url)
        assert is_safe, f"{url}: {reason}"


def test_validate_http_url_blocks_non_http_schemes() -> None:
    """file:// 등 비-HTTP 스킴은 차단한다."""
    for url in ["file:///etc/passwd", "gopher://x/", "ftp://host/f"]:
        is_safe, reason = validate_http_url(url)
        assert not is_safe, url
        assert "스킴" in reason


def test_validate_http_url_blocks_link_local_metadata() -> None:
    """클라우드 메타데이터 등 link-local 대역은 차단한다."""
    is_safe, reason = validate_http_url("http://169.254.169.254/latest/meta-data/")

    assert not is_safe
    assert "link-local" in reason


def test_run_git_commit_safe_commits_changes(tmp_path) -> None:
    """스테이징+커밋을 안전 래퍼로 수행한다."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.dev"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path), check=True)
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")

    result = run_git_commit_safe(tmp_path, "feat: add a")

    assert result.ok, result.combined_output()
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(tmp_path), capture_output=True, text=True
    )
    assert "feat: add a" in log.stdout


def test_run_git_commit_safe_rejects_missing_dir(tmp_path) -> None:
    """존재하지 않는 작업 디렉터리는 실행 전에 실패한다."""
    result = run_git_commit_safe(tmp_path / "nope", "msg")

    assert not result.ok
    assert "작업 디렉터리" in result.error_message


def test_run_command_safe_still_blocks_direct_git_commit(tmp_path) -> None:
    """일반 셸 경로에서는 git commit이 여전히 차단된다(전용 래퍼로만 허용)."""
    result = run_command_safe("git commit -m x", str(tmp_path))

    assert "Error:" in result
