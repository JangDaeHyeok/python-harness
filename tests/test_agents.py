"""에이전트 단위 테스트 (API 호출 없이 구조만 검증)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from harness.agents.base_agent import AgentConfig, AgentMessage, BaseAgent
from harness.agents.evaluator import EvaluatorAgent
from harness.agents.generator import GeneratorAgent
from harness.agents.planner import PlannerAgent, ProductSpec
from harness.tools.api_client import APIResponse, TextBlock, ToolUseBlock, Usage

if TYPE_CHECKING:
    from pathlib import Path


class TestAgentConfig:
    def test_default_config(self) -> None:
        config = AgentConfig(name="test")
        assert config.name == "test"
        assert config.model == "claude-sonnet-4-6"
        assert config.max_tokens == 16000
        assert config.tools == []

    def test_custom_config(self) -> None:
        config = AgentConfig(
            name="custom",
            model="claude-opus-4-6",
            temperature=0.2,
        )
        assert config.model == "claude-opus-4-6"
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

    def test_planner_process_response_invalid_json_falls_back(self) -> None:
        """파싱 실패 시 예외 대신 안전 기본 스펙(스프린트 없음)을 반환한다."""
        planner = PlannerAgent()

        result = planner.process_response("not json at all {{{")

        assert isinstance(result, ProductSpec)
        assert result.title == "파싱 실패"
        assert result.sprints == []

    def test_planner_process_response_non_object_falls_back(self) -> None:
        """JSON이지만 객체가 아니면 안전 기본 스펙을 반환한다."""
        planner = PlannerAgent()

        result = planner.process_response("[1, 2, 3]")

        assert isinstance(result, ProductSpec)
        assert result.sprints == []

    def test_from_dict_tolerates_missing_keys(self) -> None:
        """필수 키가 없어도 KeyError 없이 기본값으로 채운다."""
        spec = ProductSpec.from_dict({"title": "only-title"})

        assert spec.title == "only-title"
        assert spec.features == []
        assert spec.sprints == []


class _DummyAgent(BaseAgent):
    def get_system_prompt(self) -> str:
        return ""

    def process_response(self, response: str) -> Any:
        return response


class TestBaseAgentTokenUsage:
    def test_token_usage_returns_copy(self) -> None:
        agent = _DummyAgent(AgentConfig(name="test"))
        usage = agent.token_usage
        usage["input"] = 9999
        assert agent.token_usage["input"] == 0

    def test_merge_token_usage(self) -> None:
        a = _DummyAgent(AgentConfig(name="a"))
        b = _DummyAgent(AgentConfig(name="b"))
        a._token_usage = {"input": 10, "output": 5}
        b._token_usage = {"input": 100, "output": 50}
        a.merge_token_usage(b)
        assert a.token_usage == {"input": 110, "output": 55}


class _FakeToolClient:
    def __init__(self) -> None:
        self.calls = 0

    def create_message(self, **kwargs: Any) -> APIResponse:
        self.calls += 1
        if self.calls == 1:
            return APIResponse(
                content=[
                    ToolUseBlock(
                        id="toolu_1",
                        name="echo",
                        input={"message": "hello"},
                    )
                ],
                stop_reason="tool_use",
                usage=Usage(input_tokens=10, output_tokens=4),
            )
        return APIResponse(
            content=[TextBlock(text="done")],
            stop_reason="end_turn",
            usage=Usage(input_tokens=6, output_tokens=2),
        )


class _ToolAgent(_DummyAgent):
    def _run_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        return f"{tool_name}:{tool_input['message']}"


class TestBaseAgentToolUseLoop:
    def test_run_preserves_tool_use_blocks_and_appends_tool_results(self) -> None:
        agent = _ToolAgent(AgentConfig(name="tool-agent"))
        agent.client = _FakeToolClient()

        result = agent.run("use a tool")

        assert result == "done"
        assert agent.token_usage == {"input": 16, "output": 6}
        assistant_message = agent.conversation_history[1]
        tool_result_message = agent.conversation_history[2]
        assert assistant_message["role"] == "assistant"
        assert isinstance(assistant_message["content"][0], ToolUseBlock)
        assert tool_result_message == {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "echo:hello",
                }
            ],
        }


class TestGeneratorToolPathSafety:
    def test_run_command_rejects_cwd_outside_project(self, tmp_path: Path) -> None:
        generator = GeneratorAgent(str(tmp_path))

        result = generator._run_command("pwd", "/tmp")

        assert result.startswith("Error:")
        assert "프로젝트 디렉터리 밖" in result

    def test_list_files_rejects_path_outside_project(self, tmp_path: Path) -> None:
        generator = GeneratorAgent(str(tmp_path))

        result = generator._list_files("/tmp", recursive=False)

        assert result.startswith("Error:")
        assert "프로젝트 디렉터리 밖" in result

    def test_write_file_writes_within_project(self, tmp_path: Path) -> None:
        generator = GeneratorAgent(str(tmp_path))

        result = generator._write_file("out/hello.txt", "world")

        assert "파일 작성 완료" in result
        assert (tmp_path / "out" / "hello.txt").read_text(encoding="utf-8") == "world"

    def test_write_file_rejects_traversal(self, tmp_path: Path) -> None:
        generator = GeneratorAgent(str(tmp_path))

        result = generator._write_file("../escape.txt", "x")

        assert result.startswith("Error:")
        assert not (tmp_path.parent / "escape.txt").exists()

    def test_write_file_rejects_symlink_escape(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "gen_outside"
        outside.mkdir(exist_ok=True)
        (tmp_path / "link").symlink_to(outside)
        generator = GeneratorAgent(str(tmp_path))

        result = generator._write_file("link/pwn.txt", "x")

        assert result.startswith("Error:")
        assert not (outside / "pwn.txt").exists()


class TestEvaluatorUrlSafety:
    def test_check_url_blocks_file_scheme(self, tmp_path: Path) -> None:
        evaluator = EvaluatorAgent(str(tmp_path))

        result = evaluator._check_url("file:///etc/passwd")

        assert result.startswith("Error:")
        assert "스킴" in result

    def test_check_url_blocks_link_local_metadata(self, tmp_path: Path) -> None:
        evaluator = EvaluatorAgent(str(tmp_path))

        result = evaluator._check_url("http://169.254.169.254/latest/meta-data/")

        assert result.startswith("Error:")
        assert "link-local" in result

    def test_read_file_rejects_symlink_escape(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "eval_outside"
        outside.mkdir(exist_ok=True)
        (outside / "secret.txt").write_text("top-secret", encoding="utf-8")
        (tmp_path / "link").symlink_to(outside)
        evaluator = EvaluatorAgent(str(tmp_path))

        result = evaluator._read_file("link/secret.txt")

        assert result.startswith("Error:")
        assert "top-secret" not in result

    def test_process_response_tolerates_missing_criteria_keys(self, tmp_path: Path) -> None:
        """criteria 항목에 키가 없어도 KeyError 없이 폴백한다."""
        evaluator = EvaluatorAgent(str(tmp_path))
        payload = json.dumps({
            "passed": True,
            "overall_score": 7.0,
            "criteria": [{"name": "functionality"}, "not-a-dict"],
        })

        result = evaluator.process_response(payload)

        assert result.passed
        assert len(result.criteria_scores) == 1
        assert result.criteria_scores[0].name == "functionality"
        assert result.criteria_scores[0].score == 0.0
