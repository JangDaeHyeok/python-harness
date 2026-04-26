"""에이전트 단위 테스트 (API 호출 없이 구조만 검증)."""

from __future__ import annotations

import json

from harness.agents.base_agent import AgentConfig, AgentMessage
from harness.agents.planner import PlannerAgent, ProductSpec


class TestAgentConfig:
    def test_default_config(self) -> None:
        config = AgentConfig(name="test")
        assert config.name == "test"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.max_tokens == 16000
        assert config.tools == []

    def test_custom_config(self) -> None:
        config = AgentConfig(
            name="custom",
            model="claude-opus-4-20250514",
            temperature=0.2,
        )
        assert config.model == "claude-opus-4-20250514"
        assert config.temperature == 0.2


class TestAgentMessage:
    def test_message_creation(self) -> None:
        msg = AgentMessage(role="planner", content="hello")
        assert msg.role == "planner"
        assert msg.content == "hello"
        assert msg.timestamp > 0


class TestProductSpec:
    def test_from_dict(self) -> None:
        data = {
            "title": "Test",
            "description": "A test project",
            "features": [{"name": "f1", "user_story": "us1", "priority": 1, "sprint": 1}],
            "design_language": {"mood": "modern"},
            "tech_stack": {"frontend": "React"},
            "sprints": [{"number": 1, "name": "s1", "features": ["f1"], "goal": "g1"}],
            "ai_features": [],
            "success_criteria": ["works"],
        }
        spec = ProductSpec.from_dict(data)
        assert spec.title == "Test"
        assert len(spec.features) == 1
        assert len(spec.sprints) == 1

    def test_to_json(self) -> None:
        spec = ProductSpec(
            title="T",
            description="D",
            features=[],
            design_language={},
            tech_stack={},
            sprints=[],
        )
        parsed = json.loads(spec.to_json())
        assert parsed["title"] == "T"

    def test_planner_process_response(self) -> None:
        planner = PlannerAgent()
        spec_json = json.dumps({
            "title": "Test",
            "description": "desc",
            "features": [],
            "design_language": {},
            "tech_stack": {},
            "sprints": [],
        })
        result = planner.process_response(spec_json)
        assert isinstance(result, ProductSpec)
        assert result.title == "Test"

    def test_planner_process_response_code_block(self) -> None:
        planner = PlannerAgent()
        spec_json = '```json\n{"title":"T","description":"D","features":[],"design_language":{},"tech_stack":{},"sprints":[]}\n```'
        result = planner.process_response(spec_json)
        assert result.title == "T"
