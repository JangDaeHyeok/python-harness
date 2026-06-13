"""유사 RAG 컨텍스트 필터.

방대한 ADR/컨벤션 문서에서 현재 작업에 관련된 항목만 추출하여
구현 에이전트와 리뷰 에이전트에 동일한 기준을 적용할 수 있게 한다.
LLM 없이 키워드·메타데이터(태그·범위·영향 경로·번호) 기반 결정적 점수
매칭으로 동작하며, 각 항목이 왜 선택됐는지 이유를 함께 기록한다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from harness.review.conventions import CodeConvention, ConventionLoader
from harness.tools.adr import ADRLoader, extract_key_sections

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "is", "it",
    "that", "this", "be", "are", "was", "with", "as", "by", "from", "not",
    "은", "는", "이", "가", "을", "를", "의", "에", "에서", "으로", "로",
    "하다", "되다", "있다", "없다", "한다", "된다",
})


@dataclass
class FilteredContext:
    """필터링된 컨텍스트."""

    task_description: str
    relevant_adrs: list[dict[str, str]] = field(default_factory=list)
    relevant_conventions: list[CodeConvention] = field(default_factory=list)
    relevance_scores: dict[str, float] = field(default_factory=dict)
    selection_reasons: dict[str, str] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """필터링된 컨텍스트를 콤팩트한 마크다운으로 변환한다."""
        lines: list[str] = ["# 작업 관련 평가 기준\n"]

        if self.relevant_adrs:
            lines.append("## 관련 ADR\n")
            for adr in self.relevant_adrs:
                key = adr.get("filename", "")
                score = self.relevance_scores.get(key, 0.0)
                lines.append(f"### {key} — {adr.get('title', '')} (관련도: {score:.1f})\n")
                reason = self.selection_reasons.get(key, "")
                if reason:
                    lines.append(f"_선택 이유: {reason}_\n")
                lines.append(extract_key_sections(adr.get("content", "")))
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
        affected_files: list[str] | None = None,
    ) -> FilteredContext:
        """작업 설명·변경 파일과 관련도가 높은 ADR과 컨벤션을 추출한다."""
        keywords = _extract_keywords(task_description)
        files = [f.lower() for f in (affected_files or [])]
        if not keywords and not files:
            return FilteredContext(task_description=task_description)

        all_adrs = self._adr_loader.load_all()
        if self._external_adr_sources:
            all_adrs.extend(ADRLoader.load_from_external_sources(self._external_adr_sources))
        scored_adrs = self._score_adrs(all_adrs, keywords, files)
        relevant_adrs: list[dict[str, str]] = []
        scores: dict[str, float] = {}
        reasons: dict[str, str] = {}
        for adr, score, reason in scored_adrs[:max_adrs]:
            if score <= 0:
                continue
            key = adr.get("filename", "")
            relevant_adrs.append(adr)
            scores[key] = score
            reasons[key] = reason

        all_conventions = self._conv_loader.load()
        relevant_convs = self._filter_conventions(all_conventions, keywords, max_conventions)

        result = FilteredContext(
            task_description=task_description,
            relevant_adrs=relevant_adrs,
            relevant_conventions=relevant_convs,
            relevance_scores=scores,
            selection_reasons=reasons,
        )
        logger.info(
            "컨텍스트 필터링 완료: %d/%d ADR, %d/%d 컨벤션",
            len(relevant_adrs), len(all_adrs),
            len(relevant_convs), len(all_conventions),
        )
        return result

    @staticmethod
    def _score_adrs(
        adrs: list[dict[str, str]],
        keywords: list[str],
        affected_files: list[str] | None = None,
    ) -> list[tuple[dict[str, str], float, str]]:
        """각 ADR의 관련도 점수와 선택 이유를 계산하고 내림차순으로 정렬한다."""
        files = affected_files or []
        scored: list[tuple[dict[str, str], float, str]] = []
        for adr in adrs:
            score, reason = ContextFilter._score_one_adr(adr, keywords, files)
            scored.append((adr, score, reason))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    @staticmethod
    def _score_one_adr(
        adr: dict[str, str], keywords: list[str], files: list[str],
    ) -> tuple[float, str]:
        title = adr.get("title", "").lower()
        tags = adr.get("tags", "").lower()
        scope = adr.get("scope", "").lower()
        body = adr.get("content", "").lower()
        number = adr.get("number", "")

        score = 0.0
        matched_kw: list[str] = []
        signals: list[str] = []

        for kw in keywords:
            count = body.count(kw)
            hit = False
            if count > 0:
                score += min(count, 5)
                hit = True
            # 메타데이터(제목/태그/범위)는 본문 매칭 여부와 무관한 독립 신호다.
            if kw in title:
                score += 2.0
                hit = True
            if kw in tags:
                score += 2.0
                hit = True
            if kw in scope:
                score += 1.5
                hit = True
            if hit:
                matched_kw.append(kw)
        if matched_kw:
            signals.append(f"키워드 {', '.join(matched_kw[:5])}")

        # ADR 번호 직접 언급 (예: "adr-0010", "0010")
        if number and any(number in kw or f"adr-{number}" in kw for kw in keywords):
            score += 5.0
            signals.append(f"ADR 번호 {number} 직접 언급")

        # 변경/영향 파일 경로 매칭
        path_hits = ContextFilter._path_overlap(adr.get("affected_paths", ""), files)
        if path_hits:
            score += 3.0 * len(path_hits)
            signals.append(f"영향 경로 {', '.join(path_hits[:3])}")

        if adr.get("status", "") == "accepted" and score > 0:
            score *= 1.2

        reason = "; ".join(signals) if signals else "직접 매칭 없음"
        return score, reason

    @staticmethod
    def _path_overlap(affected_paths: str, files: list[str]) -> list[str]:
        """ADR이 명시한 영향 경로와 변경 파일 경로의 교집합 신호를 찾는다."""
        if not affected_paths or not files:
            return []
        prefixes = [p.strip().lower() for p in affected_paths.split(",") if p.strip()]
        hits: list[str] = []
        for prefix in prefixes:
            normalized = prefix.rstrip("/*")
            if not normalized:
                continue
            if any(normalized in f or f.startswith(normalized) for f in files):
                hits.append(prefix)
        return hits

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
    """텍스트에서 의미 있는 키워드를 추출한다.

    한글은 2글자 이상, 영문은 3글자 이상을 키워드로 본다. 한국어 핵심어는
    2글자(센서, 정책, 계약 등)가 많아 과도하게 누락되지 않도록 한다.
    """
    words = re.findall(r"adr-\d{3,4}|[a-zA-Z]{3,}|[가-힣]{2,}|\d{3,4}", text.lower())
    return list(dict.fromkeys(w for w in words if w not in _STOPWORDS))


# 하위 호환: 기존 import 경로 유지.
_extract_key_sections = extract_key_sections
