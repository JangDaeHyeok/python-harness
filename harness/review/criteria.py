"""스프린트별 평가 기준 생성.

ADR과 코드 컨벤션을 기반으로 평가 기준을 결정적 로직으로 필터링·생성한다.
LLM은 사용하지 않는다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from harness.review.conventions import CodeConvention, ConventionLoader

logger = logging.getLogger(__name__)


@dataclass
class EvalCriterion:
    """평가 기준 항목."""

    id: str
    description: str
    source: str  # "adr" | "convention" | "manual"
    severity: str = "warning"  # "error" | "warning" | "info"
    category: str = "general"


class ADRLoader:
    """ADR 디렉터리의 마크다운 파일을 읽고 키워드 기반으로 필터링한다."""

    def __init__(self, adr_dir: Path) -> None:
        self.adr_dir = Path(adr_dir)  # normalize

    def load_all(self) -> list[dict[str, str]]:
        """ADR 디렉터리의 모든 .md 파일을 메타데이터와 함께 반환한다."""
        if not self.adr_dir.exists():
            return []

        adrs: list[dict[str, str]] = []
        for path in sorted(self.adr_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            adrs.append({
                "filename": path.name,
                "content": content,
                "title": self._extract_title(content),
                "status": self._extract_status(content),
            })
        return adrs

    def filter_relevant(
        self, task_description: str, adrs: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """task_description 키워드와 관련 있는 ADR만 반환한다.

        관련 ADR이 없으면 처음 3개를 반환한다.
        """
        if not task_description.strip():
            return adrs

        keywords = self._extract_keywords(task_description)
        if not keywords:
            return adrs

        relevant: list[dict[str, str]] = []
        for adr in adrs:
            text = (adr["title"] + " " + adr["content"]).lower()
            if any(kw in text for kw in keywords):
                relevant.append(adr)

        return relevant if relevant else adrs[:3]

    @staticmethod
    def _extract_title(content: str) -> str:
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return "제목 없음"

    @staticmethod
    def _extract_status(content: str) -> str:
        match = re.search(r"status:\s*(\w+)", content)
        return match.group(1) if match else "unknown"

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """텍스트에서 3자 이상 단어를 추출하고 불용어를 제거한다."""
        stopwords = {
            "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of",
            "은", "는", "이", "가", "을", "를", "의", "에", "에서",
        }
        words = re.findall(r"[a-zA-Z가-힣]{3,}", text.lower())
        return [w for w in words if w not in stopwords]


class CriteriaGenerator:
    """ADR과 코드 컨벤션에서 평가 기준 목록을 생성한다."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)  # normalize
        self.adr_loader = ADRLoader(self.project_dir / "docs" / "adr")
        self.convention_loader = ConventionLoader(self.project_dir)

    def generate(self, task_description: str = "") -> list[EvalCriterion]:
        """ADR과 컨벤션 기반으로 평가 기준 목록을 생성한다."""
        criteria: list[EvalCriterion] = []
        criteria.extend(self._from_adrs(task_description))
        criteria.extend(self._from_conventions())
        return criteria

    def _from_adrs(self, task_description: str) -> list[EvalCriterion]:
        all_adrs = self.adr_loader.load_all()
        relevant = self.adr_loader.filter_relevant(task_description, all_adrs)

        criteria: list[EvalCriterion] = []
        for adr in relevant:
            if adr["status"] == "accepted":
                adr_id = adr["filename"].split("-")[0]
                criteria.append(
                    EvalCriterion(
                        id=f"adr-{adr_id}",
                        description=f"[ADR] {adr['title']}",
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
