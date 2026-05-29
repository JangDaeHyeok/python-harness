"""하네스 API 클라이언트. 환경변수로 제공된 엔드포인트와 통신한다."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ENDPOINT_ENV_VAR = "HARNESS_API_ENDPOINT"
DEFAULT_ENDPOINT = ""
DEFAULT_MODEL = "claude-sonnet-4-6"

MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5": {"input": 0.25, "output": 1.25},
}


class APIError(Exception):
    """API 호출 에러."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(APIError):
    """Rate limit 에러."""


@dataclass
class Usage:
    """토큰 사용량."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class TextBlock:
    """텍스트 응답 블록."""

    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    """도구 사용 응답 블록."""

    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    type: str = "tool_use"


@dataclass
class RawContentBlock:
    """알 수 없는 응답 블록."""

    type: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class APIResponse:
    """API 응답."""

    content: list[Any] = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)
    thinking: dict[str, Any] | None = None


def get_model_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """모델별 비용을 계산한다 (USD)."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])
    input_cost = input_tokens * pricing["input"] / 1_000_000
    output_cost = output_tokens * pricing["output"] / 1_000_000
    return input_cost + output_cost


class HarnessClient:
    """환경변수 기반 커스텀 엔드포인트용 API 클라이언트."""

    def __init__(self, endpoint: str | None = None) -> None:
        if endpoint is None:
            endpoint = os.environ.get(ENDPOINT_ENV_VAR, DEFAULT_ENDPOINT)
        self.endpoint = endpoint.strip()
        if self.endpoint:
            self._validate_endpoint(self.endpoint)

    @staticmethod
    def _validate_endpoint(endpoint: str) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("API 엔드포인트는 http:// 또는 https:// 로 시작해야 합니다.")
        if not parsed.netloc:
            raise ValueError("API 엔드포인트에 호스트가 없습니다.")

    def create_message(
        self,
        *,
        model: str = DEFAULT_MODEL,
        system: str = "",
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.3,
        tools: list[dict[str, Any]] | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> APIResponse:
        """메시지를 생성한다."""
        if not self.endpoint:
            raise APIError(
                f"API 엔드포인트가 설정되지 않았습니다. {ENDPOINT_ENV_VAR}를 설정하세요."
            )

        request_body: dict[str, Any] = {
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            request_body["tools"] = tools

        if thinking:
            budget = thinking.get("budget_tokens", 0)
            if budget >= max_tokens:
                raise ValueError("max_tokens는 budget_tokens보다 커야 합니다.")
            request_body["thinking"] = thinking

        data = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimitError(f"Rate limit: {e}", status_code=429) from e
            raise APIError(f"HTTP {e.code}: {e.reason}", status_code=e.code) from e
        except urllib.error.URLError as e:
            raise APIError(f"연결 실패: {e}") from e

        return self._parse_response(result)

    def _parse_response(self, result: dict[str, Any]) -> APIResponse:
        """Lambda 응답을 APIResponse로 변환한다."""
        content = self._parse_content(result)
        stop_reason = self._parse_stop_reason(result, content)

        metrics = result.get("metrics", {})
        usage = Usage(
            input_tokens=metrics.get("inputTokens", 0),
            output_tokens=metrics.get("outputTokens", 0),
        )

        thinking_data = result.get("thinking")

        return APIResponse(
            content=content,
            stop_reason=stop_reason,
            usage=usage,
            thinking=thinking_data,
        )

    def _parse_content(self, result: dict[str, Any]) -> list[Any]:
        raw_content = result.get("content")
        if isinstance(raw_content, list):
            content = [
                self._parse_content_block(block)
                for block in raw_content
                if isinstance(block, dict)
            ]
            if content:
                return content

        text = result.get("text", "")
        if isinstance(text, str):
            return [TextBlock(text=text)]
        return [TextBlock()]

    def _parse_content_block(self, block: dict[str, Any]) -> Any:
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text", "")
            return TextBlock(text=text if isinstance(text, str) else "")
        if block_type == "tool_use":
            tool_input = block.get("input", {})
            return ToolUseBlock(
                id=str(block.get("id", "")),
                name=str(block.get("name", "")),
                input=tool_input if isinstance(tool_input, dict) else {},
            )
        return RawContentBlock(
            type=str(block_type) if block_type is not None else "",
            data=block,
        )

    def _parse_stop_reason(self, result: dict[str, Any], content: list[Any]) -> str:
        stop_reason = result.get("stopReason", result.get("stop_reason"))
        if isinstance(stop_reason, str):
            return stop_reason
        if any(getattr(block, "type", "") == "tool_use" for block in content):
            return "tool_use"
        return "end_turn"
