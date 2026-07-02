"""셸 명령 실행 유틸리티. 안전한 명령 실행과 경로 검증을 제공한다."""

from __future__ import annotations

import ipaddress
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Sequence

# HTTP 요청에 허용되는 스킴. file://, gopher:// 등 비-HTTP 스킴을 차단한다.
ALLOWED_URL_SCHEMES = {"http", "https"}

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

SHELL_CONTROL_TOKENS = {
    "&&",
    "||",
    ";",
    "|",
    "|&",
    ">",
    ">>",
    "<",
    "<<",
    "2>",
    "2>>",
    "&",
}

READ_ONLY_COMMANDS = {
    "cat",
    "head",
    "ls",
    "pwd",
    "rg",
    "sed",
    "tail",
    "wc",
}

DEV_COMMANDS = {
    "mypy",
    "pytest",
    "ruff",
}

SAFE_GIT_SUBCOMMANDS = {
    "branch",
    "diff",
    "log",
    "ls-files",
    "remote",
    "rev-parse",
    "show",
    "status",
}

# git remote의 읽기 전용 외 변경 액션은 차단한다.
MUTATING_GIT_REMOTE_ACTIONS = {
    "add",
    "remove",
    "rename",
    "set-url",
    "set-head",
    "set-branches",
    "prune",
    "update",
}

# gh는 읽기 전용 인증 상태 조회만 허용한다. (token은 자격증명 노출이라 제외)
SAFE_GH_SUBCOMMANDS = {"auth"}
SAFE_GH_AUTH_ACTIONS = {"status"}

SAFE_PYTHON_MODULES = {
    "mypy",
    "pytest",
    "ruff",
}

BLOCKED_COMMANDS = {
    "bash",
    "cp",
    "mv",
    "rm",
    "sh",
    "zsh",
}

BLOCKED_GIT_SUBCOMMANDS = {
    "clean",
    "checkout",
    "push",
    "rebase",
    "reset",
    "restore",
}


def _command_name(executable: str) -> str:
    """경로가 포함된 실행 파일에서 비교용 명령 이름을 추출한다."""
    return Path(executable).name


def _is_python_command(command_name: str) -> bool:
    """python/python3/python3.11 계열 명령인지 반환한다."""
    return re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", command_name) is not None


def _contains_shell_control(argv: Sequence[str]) -> str:
    """shell 제어 토큰이 포함되어 있으면 해당 토큰을 반환한다."""
    for part in argv:
        if part in SHELL_CONTROL_TOKENS:
            return part
    return ""


def _validate_git_argv(argv: Sequence[str]) -> tuple[bool, str]:
    """git 하위 명령의 allowlist/denylist를 검증한다."""
    if len(argv) == 1:
        return False, "git 하위 명령이 필요합니다."
    subcommand = argv[1]
    if subcommand in BLOCKED_GIT_SUBCOMMANDS:
        return False, f"차단된 git 하위 명령입니다: {subcommand}"
    if subcommand not in SAFE_GIT_SUBCOMMANDS:
        return False, f"허용되지 않은 git 하위 명령입니다: {subcommand}"
    if subcommand == "reset" and "--hard" in argv:
        return False, "git reset --hard는 실행할 수 없습니다."
    if subcommand == "remote":
        for action in argv[2:]:
            if action in MUTATING_GIT_REMOTE_ACTIONS:
                return False, f"git remote 변경 액션은 실행할 수 없습니다: {action}"
    return True, ""


def _validate_gh_argv(argv: Sequence[str]) -> tuple[bool, str]:
    """gh는 읽기 전용 인증 상태 조회만 허용한다."""
    if len(argv) < 2:
        return False, "gh 하위 명령이 필요합니다."
    subcommand = argv[1]
    if subcommand not in SAFE_GH_SUBCOMMANDS:
        return False, f"허용되지 않은 gh 하위 명령입니다: {subcommand}"
    if len(argv) < 3 or argv[2] not in SAFE_GH_AUTH_ACTIONS:
        actions = ", ".join(sorted(SAFE_GH_AUTH_ACTIONS))
        return False, f"gh auth는 다음 액션만 허용됩니다: {actions}"
    if len(argv) > 3:
        # --show-token 등 자격증명 노출 플래그를 막기 위해 추가 인자를 전부 거부한다.
        return False, f"gh auth status에는 추가 인자를 사용할 수 없습니다: {argv[3]}"
    return True, ""


def _validate_find_argv(argv: Sequence[str]) -> tuple[bool, str]:
    """find 명령의 파괴적 액션을 차단한다."""
    blocked_actions = {"-delete", "-exec", "-execdir", "-ok", "-okdir"}
    for part in argv[1:]:
        if part in blocked_actions:
            return False, f"find의 파괴적 액션은 실행할 수 없습니다: {part}"
    return True, ""


def _validate_python_argv(argv: Sequence[str]) -> tuple[bool, str]:
    """python 실행은 검증 스크립트와 안전한 dev module로 제한한다."""
    if len(argv) == 1:
        return False, "python 대화형 실행은 허용되지 않습니다."

    args = list(argv[1:])
    if any(arg in {"-c", "--command"} for arg in args):
        return False, "python 임의 코드 실행은 허용되지 않습니다."

    if args[0] in {"--version", "-V"}:
        return True, ""

    if args[0] == "-m":
        if len(args) < 2:
            return False, "python -m 실행에는 모듈명이 필요합니다."
        module_name = args[1].split(".", 1)[0]
        if module_name in SAFE_PYTHON_MODULES:
            return True, ""
        return False, f"허용되지 않은 python 모듈 실행입니다: {args[1]}"

    script = Path(args[0])
    if script.suffix == ".py" and len(script.parts) >= 2 and script.parts[0] == "scripts":
        return True, ""

    return False, f"허용되지 않은 python 실행 대상입니다: {args[0]}"


def _validate_allowed_argv(argv: Sequence[str]) -> tuple[bool, str]:
    """파싱된 argv를 기반으로 허용된 명령만 통과시킨다."""
    command_name = _command_name(argv[0])
    if command_name in BLOCKED_COMMANDS:
        return False, f"차단된 명령입니다: {command_name}"
    if command_name in DEV_COMMANDS or command_name in READ_ONLY_COMMANDS:
        return True, ""
    if command_name == "git":
        return _validate_git_argv(argv)
    if command_name == "gh":
        return _validate_gh_argv(argv)
    if command_name == "find":
        return _validate_find_argv(argv)
    if _is_python_command(command_name):
        return _validate_python_argv(argv)
    return False, f"허용되지 않은 명령입니다: {command_name}"


def validate_command(command: str) -> tuple[bool, str]:
    """셸 명령의 안전성을 검증한다. (안전 여부, 사유)를 반환."""
    try:
        argv = shlex.split(command)
    except ValueError as e:
        return False, f"명령 파싱 실패: {e}"
    return validate_argv(argv)


def _validate_dangerous_patterns(command: str) -> tuple[bool, str]:
    """문자열 방어선을 적용한다."""
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
    control_token = _contains_shell_control(argv)
    if control_token:
        return False, f"셸 제어 토큰은 사용할 수 없습니다: {control_token}"
    is_safe, reason = _validate_dangerous_patterns(shlex.join(argv))
    if not is_safe:
        return False, reason
    return _validate_allowed_argv(argv)


def resolve_safe_path(path: str, project_dir: Path) -> tuple[Path | None, str]:
    """경로를 정규화해 프로젝트 디렉터리 봉쇄를 검증하고 안전한 절대 경로를 반환한다.

    심볼릭 링크를 따라간 뒤 프로젝트 밖을 가리키면 차단한다. 검증에 사용한
    정규화 경로를 그대로 반환하므로, 호출부는 이 경로로 파일을 읽고 써야
    검증 시점과 사용 시점의 불일치(TOCTOU)를 피할 수 있다.
    """
    project_root = project_dir.resolve()
    full_path = (project_dir / path).resolve()
    if not full_path.is_relative_to(project_root):
        return None, f"프로젝트 디렉터리 밖의 경로에 접근할 수 없습니다: {path}"
    return full_path, ""


def validate_path(path: str, project_dir: Path) -> tuple[bool, str]:
    """경로가 프로젝트 디렉터리 안에 있는지 검증한다."""
    resolved, reason = resolve_safe_path(path, project_dir)
    return resolved is not None, reason


def validate_http_url(url: str) -> tuple[bool, str]:
    """HTTP 요청 대상 URL의 안전성을 검증한다. (안전 여부, 사유)를 반환.

    스킴을 http/https로 제한하고(file:// 등 차단), 클라우드 메타데이터 등
    link-local(169.254.0.0/16, fe80::/10) 대역 접근을 차단한다. 로컬/사설
    대역은 하네스가 로컬 앱을 평가하는 정상 용례이므로 허용한다.
    """
    try:
        parts = urlsplit(url)
    except ValueError as e:
        return False, f"URL 파싱 실패: {e}"

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        return False, f"허용되지 않은 URL 스킴입니다: {scheme or '(없음)'}"

    host = parts.hostname
    if not host:
        return False, "URL에 호스트가 없습니다."

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # IP 리터럴이 아닌 호스트명은 통과시킨다(로컬 개발 대상 허용).
        return True, ""

    if ip.is_link_local:
        return False, f"link-local 주소에는 접근할 수 없습니다: {host}"
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


def run_git_commit_safe(
    project_dir: str | Path, message: str, timeout: int = 120
) -> CommandResult:
    """작업 트리 전체를 스테이징한 뒤 커밋한다.

    `git add`/`git commit`은 mutating 작업이라 일반 allowlist(`validate_argv`)에서
    의도적으로 차단된다. 하네스가 스프린트 결과를 커밋해야 하는 정상 용례를 위해
    tools 계층에서만 노출하는 전용 래퍼로, 타임아웃을 강제하고 subprocess 사용을
    이 한 곳으로 집중시킨다.
    """
    cwd_path = Path(project_dir)
    if not cwd_path.exists() or not cwd_path.is_dir():
        return CommandResult(
            ["git", "commit"],
            126,
            error_message=f"작업 디렉터리가 존재하지 않습니다: {cwd_path}",
        )
    if "\x00" in message:
        return CommandResult(
            ["git", "commit"], 126, error_message="커밋 메시지에 NUL 문자가 포함되어 있습니다."
        )

    try:
        add = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if add.returncode != 0:
            return CommandResult(
                ["git", "add", "-A"], add.returncode, add.stdout, add.stderr
            )
        commit = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandResult(
            ["git", "commit", "-m", message],
            commit.returncode,
            commit.stdout,
            commit.stderr,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            ["git", "commit"],
            124,
            timed_out=True,
            error_message=f"git 커밋 타임아웃 ({timeout}초)",
        )
    except (subprocess.SubprocessError, OSError) as e:
        return CommandResult(["git", "commit"], 126, error_message=str(e))
