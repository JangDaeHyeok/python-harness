"""에이전트 기본 클래스. 모든 에이전트의 공통 인터페이스를 정의한다."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from harness.tools.api_client import (
    DEFAULT_MODEL,
    APIError,
    HarnessClient,
    RateLimitError,
    get_model_cost,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """에이전트 간 통신 메시지."""

    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentConfig:
    """에이전트 설정."""

    name: str
    model: str = DEFAULT_MODEL
    max_tokens: int = 16000
    temperature: float = 0.7
    system_prompt: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    max_retries: int = 3
    timeout: int = 300


class BaseAgent(ABC):
    """
    모든 에이전트의 기본 클래스.

    핵심 책임:
    1. API 엔드포인트와의 통신
    2. 컨텍스트 관리 (안정 접두어 + 동적 접미어)
    3. 도구 실행 루프 (ReAct 패턴)
    4. 에러 핸들링 및 재시도
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.client = HarnessClient()
        self.conversation_history: list[dict[str, Any]] = []
        self.tool_results: list[dict[str, Any]] = []
        self._token_usage = {"input": 0, "output": 0}

    @abstractmethod
    def get_system_prompt(self) -> str:
        """각 에이전트의 시스템 프롬프트를 반환한다."""

    @abstractmethod
    def process_response(self, response: str) -> Any:
        """에이전트별 응답 처리 로직."""

    def run(self, user_message: str, context: dict[str, Any] | None = None) -> Any:
        """
        에이전트의 메인 실행 루프.
        ReAct 패턴: Thought → Action → Observation 반복.
        """
        self.conversation_history.append({
            "role": "user",
            "content": self._build_user_content(user_message, context),
        })

        max_turns = 50
        for _turn in range(max_turns):
            response = self._call_api_with_retry()
            self._track_tokens(response)

            if response.stop_reason == "tool_use":
                tool_results = self._execute_tools(response)
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response.content,
                })
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })
                continue

            final_text = self._extract_text(response)
            self.conversation_history.append({
                "role": "assistant",
                "content": response.content,
            })
            return self.process_response(final_text)

        raise RuntimeError(f"[{self.config.name}] 최대 턴 수({max_turns}) 초과")

    def _call_api_with_retry(self) -> Any:
        """지수 백오프를 적용한 API 호출."""
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                return self._call_api()
            except RateLimitError as e:
                wait_time = min(60 * (2 ** attempt), 300)
                logger.warning(
                    "[%s] Rate limit (시도 %d/%d). %d초 대기...",
                    self.config.name, attempt + 1, self.config.max_retries, wait_time,
                )
                time.sleep(wait_time)
                last_error = e
            except APIError as e:
                logger.error("[%s] API 에러: %s", self.config.name, e)
                last_error = e
                break
        raise RuntimeError(
            f"[{self.config.name}] API 호출 실패: {last_error}"
        ) from last_error

    def _call_api(self) -> Any:
        """API 호출."""
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "system": self.get_system_prompt(),
            "messages": self.conversation_history,
        }
        if self.config.tools:
            kwargs["tools"] = self.config.tools
        return self.client.create_message(**kwargs)

    def _build_user_content(
        self, message: str, context: dict[str, Any] | None
    ) -> str:
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            return f"<context>\n{context_str}\n</context>\n\n{message}"
        return message

    def _execute_tools(self, response: Any) -> list[dict[str, Any]]:
        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "tool_use":
                result = self._run_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })
        return tool_results

    def _run_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """개별 도구를 실행한다. 하위 클래스에서 오버라이드."""
        return f"Error: Unknown tool '{tool_name}'"

    def _extract_text(self, response: Any) -> str:
        texts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                texts.append(block.text)
        return "\n".join(texts)

    def _track_tokens(self, response: Any) -> None:
        usage = response.usage
        self._token_usage["input"] += usage.input_tokens
        self._token_usage["output"] += usage.output_tokens

    def reset_context(self) -> None:
        """컨텍스트 리셋. 컨텍스트 불안 방지를 위해 대화 히스토리를 초기화한다."""
        self.conversation_history = []
        self.tool_results = []
        logger.info("[%s] 컨텍스트 리셋 완료", self.config.name)

    @property
    def total_cost(self) -> float:
        """현재까지의 예상 비용(USD). 모델별 가격 적용."""
        return get_model_cost(
            self.config.model,
            self._token_usage["input"],
            self._token_usage["output"],
        )
