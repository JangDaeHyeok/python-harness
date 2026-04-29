"""GuideRegistry 단위 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness.agents.evaluator import EVALUATOR_SYSTEM_PROMPT, EvaluatorAgent
from harness.agents.generator import GENERATOR_SYSTEM_PROMPT, GeneratorAgent
from harness.agents.planner import PLANNER_SYSTEM_PROMPT, PlannerAgent
from harness.guides import GuideRegistry
from harness.guides.prompts import (
    MODIFY_EVALUATOR_SYSTEM_PROMPT,
    MODIFY_GENERATOR_SYSTEM_PROMPT,
    MODIFY_PLANNER_SYSTEM_PROMPT,
)

if TYPE_CHECKING:
    from pathlib import Path

ACCEPTED_ADR = """\
---
status: accepted
date: 2026-04-28
---

# ADR-0007: Guide Registry

## Context
에이전트 시스템 프롬프트와 문서 기반 컨텍스트를 점진적으로 분리한다.
"""

CONVENTION_YAML = """\
conventions:
  - id: public-type-hints
    description: "모든 public 함수에 타입 힌트 필수"
    category: type-safety
    severity: error
    tags: [typing]
"""


def setup_project(tmp_path: Path) -> Path:
    """GuideRegistry 테스트용 프로젝트 문서를 생성한다."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0007-guide-registry.md").write_text(ACCEPTED_ADR, encoding="utf-8")
    (tmp_path / "docs" / "code-convention.yaml").write_text(
        CONVENTION_YAML,
        encoding="utf-8",
    )
    return tmp_path


class TestGuideRegistry:
    def test_registry_returns_default_agent_prompts(self) -> None:
        registry = GuideRegistry()
        assert registry.get_system_prompt("planner") == PLANNER_SYSTEM_PROMPT
        assert registry.get_system_prompt("generator") == GENERATOR_SYSTEM_PROMPT
        assert registry.get_system_prompt("evaluator") == EVALUATOR_SYSTEM_PROMPT

    def test_agents_read_system_prompts_from_registry(self, tmp_path: Path) -> None:
        assert PlannerAgent().get_system_prompt() == PLANNER_SYSTEM_PROMPT
        assert GeneratorAgent(str(tmp_path)).get_system_prompt() == GENERATOR_SYSTEM_PROMPT
        assert EvaluatorAgent(str(tmp_path)).get_system_prompt() == EVALUATOR_SYSTEM_PROMPT

    def test_build_context_assembles_docs(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        registry = GuideRegistry(project)
        context = registry.build_context("Guide Registry")

        assert len(context.adrs) == 1
        assert context.adrs[0].filename == "0007-guide-registry.md"
        assert "public-type-hints" in context.code_convention
        assert "adr-0007" in context.criteria_markdown

    def test_build_context_accepts_explicit_criteria_markdown(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        registry = GuideRegistry(project)
        context = registry.build_context(criteria_markdown="## Custom Criteria\n")

        assert context.criteria_markdown == "## Custom Criteria\n"

    def test_modify_mode_returns_modify_prompts(self) -> None:
        registry = GuideRegistry(mode="modify")
        assert registry.get_system_prompt("planner") == MODIFY_PLANNER_SYSTEM_PROMPT
        assert registry.get_system_prompt("generator") == MODIFY_GENERATOR_SYSTEM_PROMPT
        assert registry.get_system_prompt("evaluator") == MODIFY_EVALUATOR_SYSTEM_PROMPT

    def test_modify_mode_agents_use_modify_prompts(self, tmp_path: Path) -> None:
        planner = PlannerAgent(mode="modify")
        assert planner.get_system_prompt() == MODIFY_PLANNER_SYSTEM_PROMPT
        gen = GeneratorAgent(str(tmp_path), mode="modify")
        assert gen.get_system_prompt() == MODIFY_GENERATOR_SYSTEM_PROMPT
        evaluator = EvaluatorAgent(str(tmp_path), mode="modify")
        assert evaluator.get_system_prompt() == MODIFY_EVALUATOR_SYSTEM_PROMPT

    def test_guide_context_to_markdown_is_stable(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        registry = GuideRegistry(project)
        markdown = registry.build_context("Guide Registry").to_markdown()

        assert markdown.startswith("## Guide Context")
        assert "### Architecture Decisions" in markdown
        assert "### Code Convention" in markdown
        assert "### Evaluation Criteria" in markdown
