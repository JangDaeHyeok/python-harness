"""리뷰 반영 판단 로그.

AI 코드 리뷰 결과에 대해 ACCEPT / REJECT / DEFER를 판정하고 기록한다.
우선순위는 severity → [p1] critical, [p2] major, [p3] minor, [p4] suggestion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.sensors.inferential.code_reviewer import ReviewComment

logger = logging.getLogger(__name__)


class Decision(Enum):
    """리뷰 코멘트에 대한 판정."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DEFER = "DEFER"


class Priority(Enum):
    """우선순위 레벨."""

    P1 = "p1"  # 즉시 수정 필요 (critical)
    P2 = "p2"  # 이번 PR에서 수정 (major)
    P3 = "p3"  # 다음 이터레이션 (minor)
    P4 = "p4"  # 백로그 (suggestion)


SEVERITY_TO_PRIORITY: dict[str, Priority] = {
    "critical": Priority.P1,
    "major": Priority.P2,
    "minor": Priority.P3,
    "suggestion": Priority.P4,
}


@dataclass
class CommentDecision:
    """개별 리뷰 코멘트에 대한 판정 기록."""

    comment_id: str
    file: str
    line: int
    severity: str
    category: str
    message: str
    suggestion: str
    decision: Decision
    reason: str
    priority: Priority = Priority.P3

    def __post_init__(self) -> None:
        self.priority = SEVERITY_TO_PRIORITY.get(self.severity, Priority.P3)


@dataclass
class ReflectionLog:
    """스프린트 단위 리뷰 반영 전체 로그."""

    sprint_number: int = 0
    decisions: list[CommentDecision] = field(default_factory=list)
    overall_summary: str = ""


class ReviewReflection:
    """리뷰 코멘트에 대한 판정을 기록하고 마크다운으로 출력한다."""

    def __init__(self, sprint_number: int = 0) -> None:
        self.log = ReflectionLog(sprint_number=sprint_number)
        self._counter = 0

    def add_decision(
        self,
        comment: ReviewComment,
        decision: Decision,
        reason: str,
    ) -> CommentDecision:
        """코멘트에 대한 판정을 추가하고 CommentDecision을 반환한다."""
        self._counter += 1
        cd = CommentDecision(
            comment_id=f"rc-{self._counter:03d}",
            file=comment.file,
            line=comment.line,
            severity=comment.severity,
            category=comment.category,
            message=comment.message,
            suggestion=comment.suggestion,
            decision=decision,
            reason=reason,
        )
        self.log.decisions.append(cd)
        logger.info(
            "리뷰 판정: [%s] %s:%d → %s",
            cd.priority.value,
            cd.file,
            cd.line,
            decision.value,
        )
        return cd

    def auto_classify(self, comment: ReviewComment) -> Decision:
        """severity 기반으로 기본 판정을 제안한다.

        critical/major → ACCEPT (즉시 반영)
        minor/suggestion → DEFER (보류)
        """
        priority = SEVERITY_TO_PRIORITY.get(comment.severity, Priority.P3)
        if priority in (Priority.P1, Priority.P2):
            return Decision.ACCEPT
        return Decision.DEFER

    def to_markdown(self) -> str:
        """판정 로그 전체를 마크다운 문서로 변환한다."""
        lines: list[str] = [
            f"# 리뷰 반영 판단 로그 (Sprint {self.log.sprint_number})\n",
        ]

        if self.log.overall_summary:
            lines += ["## 요약\n", self.log.overall_summary, ""]

        if not self.log.decisions:
            lines.append("_반영할 리뷰 코멘트 없음_\n")
            return "\n".join(lines)

        by_priority: dict[str, list[CommentDecision]] = {}
        for d in self.log.decisions:
            by_priority.setdefault(d.priority.value, []).append(d)

        for priority_val in ("p1", "p2", "p3", "p4"):
            items = by_priority.get(priority_val, [])
            if not items:
                continue
            lines.append(f"\n## [{priority_val.upper()}] 우선순위 항목\n")
            for d in items:
                lines.append(f"### {d.comment_id} — `{d.file}:{d.line}`\n")
                lines.append(f"- **심각도**: {d.severity} / **카테고리**: {d.category}")
                lines.append(f"- **문제**: {d.message}")
                if d.suggestion:
                    lines.append(f"- **제안**: {d.suggestion}")
                lines.append(f"- **판정**: **{d.decision.value}**")
                lines.append(f"- **사유**: {d.reason}")
                lines.append("")

        accept_count = sum(1 for d in self.log.decisions if d.decision == Decision.ACCEPT)
        reject_count = sum(1 for d in self.log.decisions if d.decision == Decision.REJECT)
        defer_count = sum(1 for d in self.log.decisions if d.decision == Decision.DEFER)
        lines.append(
            f"\n## 통계\n\n"
            f"- ACCEPT: {accept_count}개\n"
            f"- REJECT: {reject_count}개\n"
            f"- DEFER: {defer_count}개\n"
            f"- 합계: {len(self.log.decisions)}개\n"
        )

        return "\n".join(lines)

    def get_accepted(self) -> list[CommentDecision]:
        """ACCEPT 판정 목록."""
        return [d for d in self.log.decisions if d.decision == Decision.ACCEPT]

    def get_rejected(self) -> list[CommentDecision]:
        """REJECT 판정 목록."""
        return [d for d in self.log.decisions if d.decision == Decision.REJECT]

    def get_deferred(self) -> list[CommentDecision]:
        """DEFER 판정 목록."""
        return [d for d in self.log.decisions if d.decision == Decision.DEFER]
