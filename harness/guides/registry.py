"""얇은 GuideRegistry.

에이전트 시스템 프롬프트 조회와 ADR/컨벤션/평가 기준 컨텍스트 조립만 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from harness.guides.prompts import DEFAULT_SYSTEM_PROMPTS
from harness.review.criteria import ADRLoader, CriteriaGenerator

GuideName = Literal["planner", "generator", "evaluator"]


@dataclass(frozen=True)
class ADRGuide:
    """가이드 컨텍스트에 포함될 ADR 요약."""

    filename: str
    title: str
    status: str
    content: str


@dataclass(frozen=True)
class GuideContext:
    """에이전트에게 전달할 문서 기반 가이드 컨텍스트."""

    adrs: list[ADRGuide]
    code_convention: str
    criteria_markdown: str

    def to_markdown(self) -> str:
        """가이드 컨텍스트를 안정적인 마크다운 문자열로 변환한다."""
        sections = ["## Guide Context\n"]

        sections.append("### Architecture Decisions")
        if self.adrs:
            for adr in self.adrs:
                sections.append(f"\n#### {adr.filename} - {adr.title}")
                sections.append(f"status: {adr.status}\n")
                sections.append(adr.content.strip())
        else:
            sections.append("\nADR 없음.")

        sections.append("\n### Code Convention")
        sections.append(self.code_convention.strip() or "코드 컨벤션 없음.")

        sections.append("\n### Evaluation Criteria")
        sections.append(self.criteria_markdown.strip() or "평가 기준 없음.")

        return "\n".join(sections).strip() + "\n"


class GuideRegistry:
    """에이전트 가이드 조회와 문서 컨텍스트 조립을 제공한다."""

    def __init__(
        self,
        project_dir: str | Path = ".",
        system_prompts: dict[str, str] | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self._system_prompts = dict(DEFAULT_SYSTEM_PROMPTS)
        if system_prompts:
            self._system_prompts.update(system_prompts)

    def get_system_prompt(self, guide_name: GuideName) -> str:
        """에이전트별 시스템 프롬프트를 반환한다."""
        return self._system_prompts[guide_name]

    def build_context(
        self,
        task_description: str = "",
        criteria_markdown: str | None = None,
    ) -> GuideContext:
        """ADR, 코드 컨벤션, 평가 기준 마크다운을 하나의 가이드 컨텍스트로 조립한다."""
        adr_loader = ADRLoader(self.project_dir / "docs" / "adr")
        adrs = [
            ADRGuide(
                filename=adr["filename"],
                title=adr["title"],
                status=adr["status"],
                content=adr["content"],
            )
            for adr in adr_loader.filter_relevant(task_description, adr_loader.load_all())
        ]

        criteria_generator = CriteriaGenerator(self.project_dir)
        criteria = criteria_markdown
        if criteria is None:
            criteria = criteria_generator.to_markdown(
                criteria_generator.generate(task_description)
            )

        return GuideContext(
            adrs=adrs,
            code_convention=self._read_code_convention(),
            criteria_markdown=criteria,
        )

    def _read_code_convention(self) -> str:
        path = self.project_dir / "docs" / "code-convention.yaml"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
