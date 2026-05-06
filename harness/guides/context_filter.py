"""유사 RAG 컨텍스트 필터.

방대한 ADR/컨벤션 문서에서 현재 작업에 관련된 항목만 추출하여
구현 에이전트와 리뷰 에이전트에 동일한 기준을 적용할 수 있게 한다.
LLM 없이 키워드·태그 기반 점수 매칭으로 동작한다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from harness.review.conventions import CodeConvention, ConventionLoader
from harness.tools.adr import ADRLoader

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "is", "it",
    "that", "this", "be", "are", "was", "with", "as", "by", "from", "not",
    "은", "는", "이", "가", "을", "를", "의", "에", "에서", "으로", "로",
    "하다", "되다", "있다", "없다", "한다", "된다",
})

_MIN_KEYWORD_LEN = 2


@dataclass
class FilteredContext:
    """필터링된 컨텍스트."""

    task_description: str
    relevant_adrs: list[dict[str, str]] = field(default_factory=list)
    relevant_conventions: list[CodeConvention] = field(default_factory=list)
    relevance_scores: dict[str, float] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """필터링된 컨텍스트를 콤팩트한 마크다운으로 변환한다."""
        lines: list[str] = ["# 작업 관련 평가 기준\n"]

        if self.relevant_adrs:
            lines.append("## 관련 ADR\n")
            for adr in self.relevant_adrs:
                score = self.relevance_scores.get(adr.get("filename", ""), 0.0)
                lines.append(f"### {adr.get('filename', '')} — {adr.get('title', '')} (관련도: {score:.1f})\n")
                content = adr.get("content", "")
                lines.append(_extract_key_sections(content))
                lines.append("")

        if self.relevant_conventions:
            lines.append("## 관련 코드 컨벤션\n")
            for conv in self.relevant_conventions:
                lines.append(f"- [{conv.severity.upper()}] **{conv.id}**: {conv.description}")
            lines.append("")

        if not self.relevant_adrs and not self.relevant_conventions:
            lines.append("_이 작업에 직접 관련된 ADR/컨벤션이 없습니다._\n")

        return "\n".join(lines)


class ContextFilter:
    """작업 설명 기반으로 ADR과 컨벤션을 지능적으로 필터링한다."""

    def __init__(
        self,
        project_dir: Path,
        external_adr_sources: list[str] | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self._adr_loader = ADRLoader(self.project_dir / "docs" / "adr")
        self._conv_loader = ConventionLoader(self.project_dir)
        self._external_adr_sources = external_adr_sources or []

    def filter(
        self,
        task_description: str,
        max_adrs: int = 5,
        max_conventions: int = 10,
    ) -> FilteredContext:
        """작업 설명과 관련도가 높은 ADR과 컨벤션을 추출한다."""
        keywords = _extract_keywords(task_description)
        if not keywords:
            return FilteredContext(task_description=task_description)

        all_adrs = self._adr_loader.load_all()
        if self._external_adr_sources:
            all_adrs.extend(ADRLoader.load_from_external_sources(self._external_adr_sources))
        scored_adrs = self._score_adrs(all_adrs, keywords)
        relevant_adrs = [
            adr for adr, score in scored_adrs[:max_adrs] if score > 0
        ]
        scores = {adr.get("filename", ""): score for adr, score in scored_adrs[:max_adrs] if score > 0}

        all_conventions = self._conv_loader.load()
        relevant_convs = self._filter_conventions(all_conventions, keywords, max_conventions)

        result = FilteredContext(
            task_description=task_description,
            relevant_adrs=relevant_adrs,
            relevant_conventions=relevant_convs,
            relevance_scores=scores,
        )
        logger.info(
            "컨텍스트 필터링 완료: %d/%d ADR, %d/%d 컨벤션",
            len(relevant_adrs), len(all_adrs),
            len(relevant_convs), len(all_conventions),
        )
        return result

    @staticmethod
    def _score_adrs(
        adrs: list[dict[str, str]], keywords: list[str],
    ) -> list[tuple[dict[str, str], float]]:
        """각 ADR의 관련도 점수를 계산하고 내림차순으로 정렬한다."""
        scored: list[tuple[dict[str, str], float]] = []
        for adr in adrs:
            text = (adr.get("title", "") + " " + adr.get("content", "")).lower()
            score = 0.0
            for kw in keywords:
                count = text.count(kw)
                if count > 0:
                    title_bonus = 2.0 if kw in adr.get("title", "").lower() else 0.0
                    score += min(count, 5) + title_bonus
            if adr.get("status", "") == "accepted":
                score *= 1.2
            scored.append((adr, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    @staticmethod
    def _filter_conventions(
        conventions: list[CodeConvention],
        keywords: list[str],
        max_count: int,
    ) -> list[CodeConvention]:
        """키워드와 태그가 매칭되는 컨벤션을 추출한다."""
        scored: list[tuple[CodeConvention, float]] = []
        for conv in conventions:
            text = (conv.description + " " + conv.category + " " + " ".join(conv.tags)).lower()
            score = sum(1.0 for kw in keywords if kw in text)
            tag_bonus = sum(2.0 for kw in keywords if kw in [t.lower() for t in conv.tags])
            total = score + tag_bonus
            if conv.severity == "error":
                total *= 1.5
            if total > 0:
                scored.append((conv, total))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [conv for conv, _ in scored[:max_count]]


def _extract_keywords(text: str) -> list[str]:
    """텍스트에서 의미 있는 키워드를 추출한다."""
    words = re.findall(r"[a-zA-Z가-힣_]+", text.lower())
    return list(dict.fromkeys(
        w for w in words if len(w) > _MIN_KEYWORD_LEN and w not in _STOPWORDS
    ))


def _extract_key_sections(content: str) -> str:
    """ADR 마크다운에서 핵심 섹션(결정, 이유)만 추출한다."""
    lines = content.splitlines()
    result: list[str] = []
    in_key_section = False

    for line in lines:
        lower = line.lower().strip()
        if any(key in lower for key in ("## 결정", "## decision", "## 이유", "## rationale", "## context")):
            in_key_section = True
            result.append(line)
            continue
        if in_key_section:
            if line.startswith("## ") and not any(
                key in lower for key in ("## 결정", "## decision", "## 이유", "## rationale", "## context")
            ):
                in_key_section = False
                continue
            result.append(line)

    if not result:
        trimmed = content[:500]
        if len(content) > 500:
            trimmed += "\n..."
        return trimmed

    return "\n".join(result)
