"""Evaluator 에이전트. Generator의 결과물을 다차원으로 평가하고 피드백을 제공한다."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.agents.base_agent import AgentConfig, BaseAgent
from harness.guides import GuideRegistry
from harness.guides.prompts import EVALUATOR_SYSTEM_PROMPT
from harness.tools.api_client import DEFAULT_MODEL
from harness.tools.shell import run_command_safe, validate_path

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_CRITERIA",
    "EVALUATOR_SYSTEM_PROMPT",
    "EvaluationCriteria",
    "EvaluationResult",
    "EvaluatorAgent",
]


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

DEFAULT_CRITERIA = [
    EvaluationCriteria("product_depth", "제품 깊이와 스펙 충실도", 0.3, 6.0),
    EvaluationCriteria("functionality", "핵심 기능 작동 여부", 0.3, 7.0),
    EvaluationCriteria("visual_design", "비주얼 디자인 품질", 0.2, 5.0),
    EvaluationCriteria("code_quality", "코드 품질과 테스트", 0.2, 6.0),
]


class EvaluatorAgent(BaseAgent):
    """스프린트 결과물을 평가하는 Evaluator 에이전트."""

    def __init__(self, project_dir: str, model: str = DEFAULT_MODEL) -> None:
        config = AgentConfig(
            name="evaluator",
            model=model,
            max_tokens=16000,
            temperature=0.3,
            tools=EVALUATOR_TOOLS,
        )
        super().__init__(config)
        self.project_dir = Path(project_dir)
        self.guides = GuideRegistry(self.project_dir)

    def get_system_prompt(self) -> str:
        return self.guides.get_system_prompt("evaluator")

    def process_response(self, response: str) -> EvaluationResult:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Evaluator 응답 파싱 실패, 기본 실패 결과 반환")
            return EvaluationResult(
                sprint_number=0,
                passed=False,
                overall_score=0.0,
                criteria_scores=[],
                bugs_found=[],
                summary="평가 응답 파싱 실패",
                detailed_feedback=f"원본 응답:\n{response[:2000]}",
            )

        criteria_scores = [
            EvaluationCriteria(
                name=c["name"],
                description="",
                weight=0.25,
                threshold=6.0,
                score=c["score"],
                feedback=c["feedback"],
            )
            for c in data.get("criteria", [])
        ]

        return EvaluationResult(
            sprint_number=data.get("sprint_number", 0),
            passed=data.get("passed", False),
            overall_score=data.get("overall_score", 0.0),
            criteria_scores=criteria_scores,
            bugs_found=data.get("bugs_found", []),
            summary=data.get("summary", ""),
            detailed_feedback=data.get("detailed_feedback", ""),
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
        return run_command_safe(command, str(self.project_dir))

    def _read_file(self, path: str) -> str:
        is_safe, reason = validate_path(path, self.project_dir)
        if not is_safe:
            return f"Error: {reason}"
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
        self,
        sprint_number: int,
        sprint_contract: str,
        app_url: str = "http://localhost:3000",
        criteria_md: str | None = None,
    ) -> EvaluationResult:
        """스프린트 결과물을 평가한다.

        Args:
            sprint_number: 스프린트 번호
            sprint_contract: 스프린트 계약 (검증 기준)
            app_url: 테스트 대상 앱 URL
            criteria_md: 추가 평가 기준 마크다운 (CriteriaGenerator 출력)
        """
        criteria_section = ""
        if criteria_md:
            criteria_section = f"\n### 프로젝트 평가 기준\n{criteria_md}\n"

        message = (
            f"## 스프린트 {sprint_number} 평가\n\n"
            f"### 스프린트 계약 (검증 기준)\n{sprint_contract}\n\n"
            f"{criteria_section}"
            f"### 테스트 대상 앱\n앱이 {app_url}에서 실행 중입니다.\n\n"
            "다음 절차로 평가해주세요:\n"
            "1. `check_url`로 앱 접근 가능한지 확인\n"
            "2. 스프린트 계약의 각 기준을 검증\n"
            "3. `run_command`로 테스트 스위트 실행\n"
            "4. `read_file`로 핵심 코드 파일을 읽고 코드 품질 평가\n\n"
            "**기억하세요: 관대하지 마세요.**"
        )
        result = self.run(message)
        if not isinstance(result, EvaluationResult):
            raise TypeError(f"EvaluationResult 예상, {type(result).__name__} 반환됨")
        return result

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
        self.conversation_history.append({
            "role": "user",
            "content": message,
        })
        response = self._call_api_with_retry()
        self._track_tokens(response)
        text = self._extract_text(response)
        self.conversation_history.append({
            "role": "assistant",
            "content": response.content,
        })
        return text
