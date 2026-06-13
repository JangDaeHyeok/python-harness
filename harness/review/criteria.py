"""스프린트별 평가 기준 생성.

ADR과 코드 컨벤션을 기반으로 평가 기준을 결정적 로직으로 필터링·생성한다.
LLM은 사용하지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from harness.review.conventions import CodeConvention, ConventionLoader
from harness.tools.adr import ADRLoader

logger = logging.getLogger(__name__)

__all__ = ["ADRLoader", "CriteriaGenerator", "EvalCriterion"]


@dataclass
class EvalCriterion:
    """평가 기준 항목."""

    id: str
    description: str
    source: str  # "adr" | "convention" | "manual"
    severity: str = "warning"  # "error" | "warning" | "info"
    category: str = "general"


class CriteriaGenerator:
    """ADR과 코드 컨벤션에서 평가 기준 목록을 생성한다."""

    def __init__(
        self,
        project_dir: Path,
        external_adr_sources: list[str] | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)  # normalize
        self.adr_loader = ADRLoader(self.project_dir / "docs" / "adr")
        self.convention_loader = ConventionLoader(self.project_dir)
        self._external_adr_sources = external_adr_sources or []

    def generate(self, task_description: str = "") -> list[EvalCriterion]:
        """ADR과 컨벤션 기반으로 평가 기준 목록을 생성한다."""
        criteria: list[EvalCriterion] = []
        criteria.extend(self._from_adrs(task_description))
        criteria.extend(self._from_conventions())
        return criteria

    def _from_adrs(self, task_description: str) -> list[EvalCriterion]:
        all_adrs = self.adr_loader.load_all()
        if self._external_adr_sources:
            all_adrs.extend(ADRLoader.load_from_external_sources(self._external_adr_sources))
        relevant = self.adr_loader.filter_relevant(task_description, all_adrs)

        criteria: list[EvalCriterion] = []
        seen: set[tuple[str, str]] = set()
        for adr in relevant:
            if adr["status"] != "accepted":
                continue
            adr_id = adr.get("number", "") or adr["filename"].split("-")[0]
            source = adr.get("source", "")
            # ADR 번호는 소스마다 로컬이므로 (소스, 번호)로 식별해야
            # 로컬 0010과 외부 0010이 충돌해 외부 ADR이 누락되지 않는다.
            dedup_key = (source, adr_id)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            criterion_id = f"adr-{Path(source).name}-{adr_id}" if source else f"adr-{adr_id}"
            source_tag = f" (외부: {source})" if source else ""
            criteria.append(
                EvalCriterion(
                    id=criterion_id,
                    description=f"[ADR] {adr['title']}{source_tag}",
                    source="adr",
                    severity="error",
                    category="architecture",
                )
            )
        return criteria

    def _from_conventions(self) -> list[EvalCriterion]:
        conventions: list[CodeConvention] = self.convention_loader.load()
        return [
            EvalCriterion(
                id=f"conv-{c.id}",
                description=c.description,
                source="convention",
                severity=c.severity,
                category=c.category,
            )
            for c in conventions
        ]

    def to_markdown(self, criteria: list[EvalCriterion]) -> str:
        """평가 기준 목록을 마크다운 문서로 변환한다."""
        if not criteria:
            return "## 평가 기준\n\n기준 없음.\n"

        lines = ["## 평가 기준\n"]
        by_category: dict[str, list[EvalCriterion]] = {}
        for c in criteria:
            by_category.setdefault(c.category, []).append(c)

        for category, items in sorted(by_category.items()):
            lines.append(f"\n### {category}\n")
            for item in items:
                badge = f"[{item.severity.upper()}]"
                lines.append(f"- {badge} **{item.id}**: {item.description}")

        return "\n".join(lines)
