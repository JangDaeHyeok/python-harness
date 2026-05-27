"""셸 명령 실행 유틸리티. 안전한 명령 실행과 경로 검증을 제공한다."""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/(?!tmp)"),
    re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+~"),
    re.compile(r"mkfs\."),
    re.compile(r"dd\s+if="),
    re.compile(r":\(\)\s*\{"),
    re.compile(r"\|\s*(sh|bash)\b"),
    re.compile(r"curl\b.*\|\s*(sh|bash)"),
    re.compile(r"wget\b.*\|\s*(sh|bash)"),
    re.compile(r"sudo\b"),
    re.compile(r">\s*/dev/sd"),
    re.compile(r"chmod\s+777"),
    re.compile(r"eval\s+\$"),
]


def validate_command(command: str) -> tuple[bool, str]:
    """셸 명령의 안전성을 검증한다. (안전 여부, 사유)를 반환."""
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return False, f"위험한 명령 패턴 감지: {pattern.pattern}"
    return True, ""


def validate_argv(argv: Sequence[str]) -> tuple[bool, str]:
    """argv 기반 명령의 안전성을 검증한다. (안전 여부, 사유)를 반환."""
    if not argv:
        return False, "빈 명령은 실행할 수 없습니다."
    if any("\x00" in part for part in argv):
        return False, "명령 인자에 NUL 문자가 포함되어 있습니다."
    return validate_command(shlex.join(argv))


def validate_path(path: str, project_dir: Path) -> tuple[bool, str]:
    """경로가 프로젝트 디렉터리 안에 있는지 검증한다."""
    full_path = (project_dir / path).resolve()
    if not full_path.is_relative_to(project_dir.resolve()):
        return False, f"프로젝트 디렉터리 밖의 경로에 접근할 수 없습니다: {path}"
    return True, ""


@dataclass(frozen=True)
class CommandResult:
    """안전 실행 결과."""

    argv: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error_message: str = ""

    @property
    def ok(self) -> bool:
        """명령이 성공했는지 반환한다."""
        return self.returncode == 0 and not self.error_message and not self.timed_out

    def combined_output(self, limit: int | None = None) -> str:
        """stdout/stderr/returncode를 일관된 텍스트로 반환한다."""
        stdout = self.stdout if limit is None else self.stdout[:limit]
        stderr = self.stderr if limit is None else self.stderr[:limit]
        parts: list[str] = []
        if stdout:
            parts.append(f"STDOUT:\n{stdout}")
        if stderr:
            parts.append(f"STDERR:\n{stderr}")
        if self.error_message:
            parts.append(f"Error: {self.error_message}")
        parts.append(f"Return code: {self.returncode}")
        return "\n".join(parts)


def run_argv_safe(
    argv: Sequence[str],
    cwd: str | Path,
    timeout: int = 120,
) -> CommandResult:
    """argv 기반으로 명령을 안전하게 실행한다."""
    command = [str(part) for part in argv]
    is_safe, reason = validate_argv(command)
    if not is_safe:
        return CommandResult(command, 126, error_message=reason)

    cwd_path = Path(cwd)
    if not cwd_path.exists() or not cwd_path.is_dir():
        return CommandResult(
            command,
            126,
            error_message=f"작업 디렉터리가 존재하지 않습니다: {cwd_path}",
        )

    try:
        result = subprocess.run(
            command,
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandResult(
            argv=command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except subprocess.TimeoutExpired as e:
        return CommandResult(
            command,
            124,
            stdout=e.stdout if isinstance(e.stdout, str) else "",
            stderr=e.stderr if isinstance(e.stderr, str) else "",
            timed_out=True,
            error_message=f"명령 실행 타임아웃 ({timeout}초)",
        )
    except FileNotFoundError:
        return CommandResult(
            command,
            127,
            error_message=f"명령을 찾을 수 없습니다: {command[0]}",
        )
    except OSError as e:
        return CommandResult(command, 126, error_message=str(e))


def run_command_safe(
    command: str, cwd: str, timeout: int = 120
) -> str:
    """안전성 검증 후 셸 명령을 실행한다."""
    is_safe, reason = validate_command(command)
    if not is_safe:
        return f"Error: {reason}"

    try:
        argv = shlex.split(command)
    except ValueError as e:
        return f"Error: {e}"
    result = run_argv_safe(argv, cwd, timeout=timeout)
    return result.combined_output(limit=3000)
