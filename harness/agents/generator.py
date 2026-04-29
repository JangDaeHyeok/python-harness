"""Generator 에이전트. 스프린트 단위로 한 번에 하나의 기능을 구현한다."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from harness.agents.base_agent import AgentConfig, BaseAgent
from harness.guides import GuideRegistry
from harness.guides.prompts import GENERATOR_SYSTEM_PROMPT
from harness.tools.api_client import DEFAULT_MODEL
from harness.tools.shell import run_command_safe, validate_path

logger = logging.getLogger(__name__)

__all__ = ["GENERATOR_SYSTEM_PROMPT", "GeneratorAgent"]

GENERATOR_TOOLS = [
    {
        "name": "write_file",
        "description": "파일을 생성하거나 덮어쓴다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "프로젝트 루트 기준 상대 경로"},
                "content": {"type": "string", "description": "파일 내용"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "파일 내용을 읽는다.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "파일 경로"}},
            "required": ["path"],
        },
    },
    {
        "name": "run_command",
        "description": "셸 명령을 실행한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "실행할 셸 명령"},
                "cwd": {"type": "string", "description": "작업 디렉터리"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "git_commit",
        "description": "현재 변경사항을 git에 커밋한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "커밋 메시지 (conventional commits)"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "list_files",
        "description": "디렉터리의 파일 목록을 조회한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "디렉터리 경로"},
                "recursive": {"type": "boolean", "description": "재귀적 조회 여부"},
            },
        },
    },
]

IGNORED_DIRS = {"node_modules", ".git", "__pycache__", ".next", "dist", "build", ".venv", "venv"}


class GeneratorAgent(BaseAgent):
    """스프린트 단위로 기능을 구현하는 Generator 에이전트."""

    def __init__(
        self, project_dir: str, model: str = DEFAULT_MODEL, mode: str = "create",
    ) -> None:
        config = AgentConfig(
            name="generator",
            model=model,
            max_tokens=16000,
            temperature=0.5,
            tools=GENERATOR_TOOLS,
        )
        super().__init__(config)
        self.project_dir = Path(project_dir)
        self.guides = GuideRegistry(self.project_dir, mode=mode)

    def get_system_prompt(self) -> str:
        return self.guides.get_system_prompt("generator")

    def process_response(self, response: str) -> str:
        return response

    def _run_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        handlers = {
            "write_file": lambda: self._write_file(tool_input["path"], tool_input["content"]),
            "read_file": lambda: self._read_file(tool_input["path"]),
            "run_command": lambda: self._run_command(
                tool_input["command"], tool_input.get("cwd")
            ),
            "git_commit": lambda: self._git_commit(tool_input["message"]),
            "list_files": lambda: self._list_files(
                tool_input.get("path", "."), tool_input.get("recursive", False)
            ),
        }
        handler = handlers.get(tool_name)
        if handler:
            return handler()
        return f"Error: Unknown tool '{tool_name}'"

    def _write_file(self, path: str, content: str) -> str:
        is_safe, reason = validate_path(path, self.project_dir)
        if not is_safe:
            return f"Error: {reason}"
        full_path = self.project_dir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return f"파일 작성 완료: {path} ({len(content)} bytes)"

    def _read_file(self, path: str) -> str:
        is_safe, reason = validate_path(path, self.project_dir)
        if not is_safe:
            return f"Error: {reason}"
        full_path = self.project_dir / path
        if not full_path.exists():
            return f"Error: 파일을 찾을 수 없음 - {path}"
        content = full_path.read_text(encoding="utf-8")
        if len(content) > 10000:
            return content[:5000] + "\n\n... [중간 생략] ...\n\n" + content[-5000:]
        return content

    def _run_command(self, command: str, cwd: str | None = None) -> str:
        work_dir = str(self.project_dir / cwd) if cwd else str(self.project_dir)
        return run_command_safe(command, work_dir)

    def _git_commit(self, message: str) -> str:
        try:
            subprocess.run(
                ["git", "add", "."], cwd=str(self.project_dir), check=True
            )
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
            )
            return result.stdout or result.stderr
        except Exception as e:
            return f"Git 커밋 실패: {e}"

    def _list_files(self, path: str, recursive: bool) -> str:
        target = self.project_dir / path
        if not target.exists():
            return f"Error: 경로를 찾을 수 없음 - {path}"
        if recursive:
            files = [
                str(f.relative_to(self.project_dir))
                for f in target.rglob("*")
                if f.is_file() and not any(d in f.parts for d in IGNORED_DIRS)
            ]
        else:
            files = [str(f.relative_to(self.project_dir)) for f in target.iterdir()]
        return "\n".join(sorted(files)[:100])

    def implement_sprint(
        self, spec_json: str, sprint_contract: str, sprint_number: int
    ) -> str:
        """스프린트를 구현한다."""
        message = (
            f"## 스프린트 {sprint_number} 구현\n\n"
            f"### 제품 스펙\n{spec_json}\n\n"
            f"### 스프린트 계약\n{sprint_contract}\n\n"
            "위 스프린트 계약에 명시된 기능을 구현해주세요.\n"
            "구현이 완료되면 다음을 수행하세요:\n"
            "1. 모든 테스트를 실행하고 통과 여부를 확인\n"
            "2. lint 검사를 실행\n"
            "3. git 커밋\n"
            "4. 구현 보고서를 작성"
        )
        result = self.run(message)
        if not isinstance(result, str):
            raise TypeError(f"str 예상, {type(result).__name__} 반환됨")
        return result
