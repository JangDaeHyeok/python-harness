"""Planner 에이전트. 간단한 사용자 프롬프트를 상세한 제품 스펙으로 확장한다."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from harness.agents.base_agent import AgentConfig, BaseAgent
from harness.guides import GuideRegistry
from harness.guides.prompts import PLANNER_SYSTEM_PROMPT

__all__ = ["PLANNER_SYSTEM_PROMPT", "PlannerAgent", "ProductSpec"]


@dataclass
class ProductSpec:
    """제품 스펙 데이터 구조."""

    title: str
    description: str
    features: list[dict[str, Any]]
    design_language: dict[str, Any]
    tech_stack: dict[str, str]
    sprints: list[dict[str, Any]]
    ai_features: list[dict[str, Any]] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> ProductSpec:
        return cls.from_dict(json.loads(text))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProductSpec:
        return cls(
            title=data["title"],
            description=data["description"],
            features=data["features"],
            design_language=data["design_language"],
            tech_stack=data["tech_stack"],
            sprints=data["sprints"],
            ai_features=data.get("ai_features", []),
            success_criteria=data.get("success_criteria", []),
        )


class PlannerAgent(BaseAgent):
    """제품 스펙을 생성하는 Planner 에이전트."""

    def __init__(self, model: str = "claude-sonnet-4-6", mode: str = "create") -> None:
        config = AgentConfig(
            name="planner",
            model=model,
            max_tokens=16000,
            temperature=0.8,
        )
        super().__init__(config)
        self.guides = GuideRegistry(mode=mode)

    def get_system_prompt(self) -> str:
        return self.guides.get_system_prompt("planner")

    def process_response(self, response: str) -> ProductSpec:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"Planner 응답 파싱 실패: {e}\n응답: {response[:500]}") from e

        return ProductSpec.from_dict(data)

    def plan(self, user_prompt: str) -> ProductSpec:
        """사용자 프롬프트를 제품 스펙으로 확장한다."""
        message = (
            f"다음 아이디어를 상세한 제품 스펙으로 확장해주세요:\n\n{user_prompt}\n\n"
            "야심적이되 실현 가능한 범위로, 최소 10개 이상의 주요 기능을 포함해주세요.\n"
            "AI 기능을 자연스럽게 통합할 수 있는 기회를 찾아주세요."
        )
        result = self.run(message)
        if not isinstance(result, ProductSpec):
            raise TypeError(f"ProductSpec 예상, {type(result).__name__} 반환됨")
        return result
