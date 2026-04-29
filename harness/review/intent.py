"""설계 의도 문서 생성.

스프린트 정보와 계약을 기반으로 design-intent.md를 생성한다.
LLM 없이 결정적 로직으로 구조화된 문서를 생성한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DesignIntent:
    """설계 의도 문서 데이터."""

    task_overview: str
    key_decisions: list[str] = field(default_factory=list)
    alternatives_considered: list[dict[str, str]] = field(default_factory=list)
    intentionally_excluded: list[str] = field(default_factory=list)
    review_notes: list[str] = field(default_factory=list)
    sprint_number: int = 0
    task_description: str = ""


class IntentGenerator:
    """스프린트 정보로부터 설계 의도 문서를 생성한다."""

    def generate_from_spec(
        self,
        task_description: str,
        sprint_info: dict[str, Any] | None = None,
        sprint_contract: str | None = None,
    ) -> DesignIntent:
        """스펙과 스프린트 정보로 설계 의도를 생성한다."""
        sprint_number: int = sprint_info.get("number", 0) if sprint_info else 0
        sprint_name: str = str(sprint_info.get("name", "미정")) if sprint_info else "미정"
        sprint_goal: str = str(sprint_info.get("goal", "")) if sprint_info else ""
        features: list[Any] = list(sprint_info.get("features", [])) if sprint_info else []

        overview_parts = [f"스프린트 {sprint_number}: {sprint_name}"]
        if sprint_goal:
            overview_parts.append(f"목표: {sprint_goal}")
        overview = "\n".join(overview_parts)

        key_decisions: list[str] = []
        if features:
            feature_names = ", ".join(str(f) for f in features)
            key_decisions.append(f"구현 대상 기능: {feature_names}")
        if sprint_contract:
            key_decisions.append("스프린트 계약에 따라 검증 기준이 사전 협의됨")
        if not key_decisions:
            key_decisions.append("별도 설계 결정 없음")

        review_notes = [
            "이 문서는 구현 전 설계 의도를 기록합니다.",
            "구현 중 변경이 발생하면 문서를 업데이트하세요.",
        ]

        return DesignIntent(
            task_overview=overview,
            key_decisions=key_decisions,
            alternatives_considered=[],
            intentionally_excluded=[],
            review_notes=review_notes,
            sprint_number=sprint_number,
            task_description=task_description,
        )

    def to_markdown(self, intent: DesignIntent) -> str:
        """설계 의도를 마크다운 문서로 변환한다."""
        lines: list[str] = [
            "# 설계 의도 (Design Intent)\n",
            f"**스프린트**: {intent.sprint_number}\n",
            "## 작업 개요\n",
            intent.task_overview,
            "",
        ]

        if intent.task_description:
            lines += ["\n## 요청 설명\n", intent.task_description, ""]

        if intent.key_decisions:
            lines.append("\n## 핵심 설계 결정\n")
            for decision in intent.key_decisions:
                lines.append(f"- {decision}")
            lines.append("")

        if intent.alternatives_considered:
            lines.append("\n## 고려한 선택지\n")
            for alt in intent.alternatives_considered:
                option = alt.get("option", "")
                reason = alt.get("reason", "")
                lines.append(f"- **{option}**: {reason}")
            lines.append("")

        if intent.intentionally_excluded:
            lines.append("\n## 의도적으로 제외한 것\n")
            for excl in intent.intentionally_excluded:
                lines.append(f"- {excl}")
            lines.append("")

        if intent.review_notes:
            lines.append("\n## 구현/리뷰 시 주의사항\n")
            for note in intent.review_notes:
                lines.append(f"- {note}")
            lines.append("")

        return "\n".join(lines)
