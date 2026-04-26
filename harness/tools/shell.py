"""셸 명령 실행 유틸리티. 안전한 명령 실행과 경로 검증을 제공한다."""

from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

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


def validate_path(path: str, project_dir: Path) -> tuple[bool, str]:
    """경로가 프로젝트 디렉터리 안에 있는지 검증한다."""
    full_path = (project_dir / path).resolve()
    if not full_path.is_relative_to(project_dir.resolve()):
        return False, f"프로젝트 디렉터리 밖의 경로에 접근할 수 없습니다: {path}"
    return True, ""


def run_command_safe(
    command: str, cwd: str, timeout: int = 120
) -> str:
    """안전성 검증 후 셸 명령을 실행한다."""
    is_safe, reason = validate_command(command)
    if not is_safe:
        return f"Error: {reason}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout[:3000]}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr[:3000]}\n"
        output += f"Return code: {result.returncode}"
        return output
    except subprocess.TimeoutExpired:
        return f"Error: 명령 실행 타임아웃 ({timeout}초)"
    except Exception as e:
        return f"Error: {e}"
