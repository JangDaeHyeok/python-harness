"""Planner 에이전트. 간단한 사용자 프롬프트를 상세한 제품 스펙으로 확장한다."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from harness.agents.base_agent import AgentConfig, BaseAgent

PLANNER_SYSTEM_PROMPT = """당신은 시니어 프로덕트 매니저이자 소프트웨어 아키텍트입니다.
사용자의 간단한 아이디어를 야심찬 범위의 상세한 제품 스펙으로 확장하는 것이 임무입니다.

## 핵심 원칙

1. **야심적 범위 설정**: 사용자의 기대를 넘어서는 기능을 제안하세요.
   최소한 10개 이상의 주요 기능을 포함해야 합니다.

2. **제품 컨텍스트 중심**: 기술적 구현 세부사항을 명세하지 마세요.
   사용자 스토리와 제품 경험에 집중하세요.

3. **AI 기능 통합**: 제품에 자연스럽게 AI 기능을 직조하세요.

4. **비주얼 디자인 랭귀지**: 제품의 시각적 정체성을 정의하세요.

5. **스프린트 분해**: 기능을 논리적 순서의 스프린트로 분해하세요.

## 출력 형식

반드시 아래 JSON 형식으로 출력하세요. 다른 텍스트를 포함하지 마세요.

```json
{
  "title": "프로젝트 제목",
  "description": "프로젝트 설명 (2-3문장)",
  "features": [
    {"name": "기능명", "user_story": "사용자 스토리", "priority": 1, "sprint": 1}
  ],
  "design_language": {
    "mood": "전체적인 분위기",
    "color_palette": {"primary": "", "secondary": "", "accent": "", "background": ""},
    "typography": "타이포그래피 스타일",
    "layout_principles": ["원칙1", "원칙2"]
  },
  "tech_stack": {
    "frontend": "추천 프레임워크",
    "backend": "추천 프레임워크",
    "database": "추천 DB"
  },
  "sprints": [
    {"number": 1, "name": "스프린트명", "features": ["기능1"], "goal": "스프린트 목표"}
  ],
  "ai_features": [
    {"name": "AI 기능명", "description": "설명", "integration_point": "통합 지점"}
  ],
  "success_criteria": ["기준1", "기준2"]
}
```
"""


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

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        config = AgentConfig(
            name="planner",
            model=model,
            max_tokens=16000,
            temperature=0.8,
        )
        super().__init__(config)

    def get_system_prompt(self) -> str:
        return PLANNER_SYSTEM_PROMPT

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
        return self.run(message)
