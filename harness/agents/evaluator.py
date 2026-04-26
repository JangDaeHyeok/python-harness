"""Evaluator 에이전트. Generator의 결과물을 다차원으로 평가하고 피드백을 제공한다."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.agents.base_agent import AgentConfig, BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class EvaluationCriteria:
    """평가 기준."""

    name: str
    description: str
    weight: float
    threshold: float
    score: float = 0.0
    feedback: str = ""


@dataclass
class EvaluationResult:
    """평가 결과."""

    sprint_number: int
    passed: bool
    overall_score: float
    criteria_scores: list[EvaluationCriteria]
    bugs_found: list[dict[str, Any]]
    summary: str
    detailed_feedback: str


EVALUATOR_TOOLS = [
    {
        "name": "run_command",
        "description": "셸 명령을 실행하여 테스트, 빌드, API 호출 등을 수행한다.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "실행할 명령"}},
            "required": ["command"],
        },
    },
    {
        "name": "check_url",
        "description": "URL에 HTTP 요청을 보내고 응답을 확인한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string", "description": "GET, POST 등"},
                "body": {"type": "string", "description": "요청 본문 (JSON)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "read_file",
        "description": "파일 내용을 읽는다.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]

EVALUATOR_SYSTEM_PROMPT = """당신은 엄격한 시니어 QA 엔지니어이자 코드 리뷰어입니다.
Generator가 구현한 스프린트 결과물을 평가하는 것이 임무입니다.

## 평가 원칙

**가장 중요한 원칙: 관대하지 마세요.**

## 평가 기준 (각 기준 0-10점)

1. 제품 깊이 (가중치: 0.3, 임계값: 6)
2. 기능성 (가중치: 0.3, 임계값: 7)
3. 비주얼 디자인 (가중치: 0.2, 임계값: 5)
4. 코드 품질 (가중치: 0.2, 임계값: 6)

## 출력 형식

반드시 아래 JSON 형식으로 출력하세요.

```json
{
  "sprint_number": 1,
  "overall_score": 7.2,
  "passed": true,
  "criteria": [
    {"name": "product_depth", "score": 7, "feedback": "..."},
    {"name": "functionality", "score": 8, "feedback": "..."},
    {"name": "visual_design", "score": 6, "feedback": "..."},
    {"name": "code_quality", "score": 7, "feedback": "..."}
  ],
  "bugs_found": [
    {"severity": "high", "description": "...", "location": "파일:라인", "fix_suggestion": "..."}
  ],
  "summary": "전체 평가 요약",
  "detailed_feedback": "Generator에게 전달할 상세 피드백"
}
```
"""

DEFAULT_CRITERIA = [
    EvaluationCriteria("product_depth", "제품 깊이와 스펙 충실도", 0.3, 6.0),
    EvaluationCriteria("functionality", "핵심 기능 작동 여부", 0.3, 7.0),
    EvaluationCriteria("visual_design", "비주얼 디자인 품질", 0.2, 5.0),
    EvaluationCriteria("code_quality", "코드 품질과 테스트", 0.2, 6.0),
]


class EvaluatorAgent(BaseAgent):
    """스프린트 결과물을 평가하는 Evaluator 에이전트."""

    def __init__(self, project_dir: str, model: str = "claude-sonnet-4-20250514") -> None:
        config = AgentConfig(
            name="evaluator",
            model=model,
            max_tokens=16000,
            temperature=0.3,
            tools=EVALUATOR_TOOLS,
        )
        super().__init__(config)
        self.project_dir = Path(project_dir)

    def get_system_prompt(self) -> str:
        return EVALUATOR_SYSTEM_PROMPT

    def process_response(self, response: str) -> EvaluationResult:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        data = json.loads(cleaned)

        criteria_scores = [
            EvaluationCriteria(
                name=c["name"],
                description="",
                weight=0.25,
                threshold=6.0,
                score=c["score"],
                feedback=c["feedback"],
            )
            for c in data["criteria"]
        ]

        return EvaluationResult(
            sprint_number=data["sprint_number"],
            passed=data["passed"],
            overall_score=data["overall_score"],
            criteria_scores=criteria_scores,
            bugs_found=data.get("bugs_found", []),
            summary=data["summary"],
            detailed_feedback=data["detailed_feedback"],
        )

    def _run_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        if tool_name == "run_command":
            return self._run_command(tool_input["command"])
        if tool_name == "read_file":
            return self._read_file(tool_input["path"])
        if tool_name == "check_url":
            return self._check_url(
                tool_input["url"],
                tool_input.get("method", "GET"),
                tool_input.get("body"),
            )
        return f"Error: Unknown tool '{tool_name}'"

    def _run_command(self, command: str) -> str:
        try:
            result = subprocess.run(
                command, shell=True, cwd=str(self.project_dir),
                capture_output=True, text=True, timeout=120,
            )
            output = ""
            if result.stdout:
                output += f"STDOUT:\n{result.stdout[:3000]}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr[:3000]}\n"
            output += f"Return code: {result.returncode}"
            return output
        except subprocess.TimeoutExpired:
            return "Error: 타임아웃 (120초)"

    def _read_file(self, path: str) -> str:
        full_path = self.project_dir / path
        if not full_path.exists():
            return f"Error: 파일을 찾을 수 없음 - {path}"
        return full_path.read_text(encoding="utf-8")[:10000]

    def _check_url(self, url: str, method: str = "GET", body: str | None = None) -> str:
        import urllib.error
        import urllib.request

        try:
            data = body.encode() if body else None
            req = urllib.request.Request(url, data=data, method=method)
            if body:
                req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return f"Status: {resp.status}\nBody:\n{resp.read().decode()[:3000]}"
        except urllib.error.URLError as e:
            return f"Error: {e}"

    def evaluate_sprint(
        self, sprint_number: int, sprint_contract: str, app_url: str = "http://localhost:3000"
    ) -> EvaluationResult:
        """스프린트 결과물을 평가한다."""
        message = (
            f"## 스프린트 {sprint_number} 평가\n\n"
            f"### 스프린트 계약 (검증 기준)\n{sprint_contract}\n\n"
            f"### 테스트 대상 앱\n앱이 {app_url}에서 실행 중입니다.\n\n"
            "다음 절차로 평가해주세요:\n"
            "1. `check_url`로 앱 접근 가능한지 확인\n"
            "2. 스프린트 계약의 각 기준을 검증\n"
            "3. `run_command`로 테스트 스위트 실행\n"
            "4. `read_file`로 핵심 코드 파일을 읽고 코드 품질 평가\n\n"
            "**기억하세요: 관대하지 마세요.**"
        )
        return self.run(message)

    def negotiate_contract(
        self, spec_json: str, sprint_number: int, generator_proposal: str
    ) -> str:
        """Generator의 스프린트 제안을 검토하고 계약을 협상한다."""
        message = (
            f"## 스프린트 계약 협상\n\n"
            f"### 제품 스펙\n{spec_json}\n\n"
            f"### Generator의 스프린트 {sprint_number} 제안\n{generator_proposal}\n\n"
            "이 제안을 검토하고 합의된 스프린트 계약을 반환하세요.\n"
            "계약에는 반드시 다음을 포함해야 합니다:\n"
            "- 구현할 기능 목록\n"
            "- 각 기능의 검증 기준\n"
            "- 성공/실패 판정 기준"
        )
        # negotiate_contract returns raw text, not EvaluationResult
        self.conversation_history.append({
            "role": "user",
            "content": message,
        })
        response = self._call_api()
        self._track_tokens(response)
        text = self._extract_text(response)
        self.conversation_history.append({
            "role": "assistant",
            "content": response.content,
        })
        return text
