"""리뷰 파이프라인 통합.

CodeReviewer의 ReviewResult를 ReviewReflection과 연결한다.
모든 코멘트를 severity 기반으로 자동 분류하고 review-comments.md에 기록한다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from harness.review.reflection import Decision, ReviewReflection

if TYPE_CHECKING:
    from harness.review.artifacts import ReviewArtifactManager
    from harness.sensors.inferential.code_reviewer import ReviewResult

logger = logging.getLogger(__name__)

# severity → 자동 판정 이유
_AUTO_REASON: dict[Decision, str] = {
    Decision.ACCEPT: "critical/major severity — 이번 PR에서 즉시 반영 권고",
    Decision.DEFER: "minor/suggestion severity — 다음 이터레이션에서 검토",
    Decision.REJECT: "자동 분류 불가 — 수동 검토 필요",
}


def classify_review_result(
    result: ReviewResult,
    sprint_number: int = 0,
) -> ReviewReflection:
    """ReviewResult의 모든 코멘트를 severity 기반으로 자동 분류한다.

    - critical/major  → ACCEPT (p1/p2: 즉시 반영)
    - minor/suggestion → DEFER  (p3/p4: 다음 이터레이션)
    """
    reflection = ReviewReflection(sprint_number=sprint_number)
    reflection.log.overall_summary = result.overall_assessment

    for comment in result.comments:
        decision = reflection.auto_classify(comment)
        reason = _AUTO_REASON.get(decision, "자동 분류")
        reflection.add_decision(comment, decision, reason)

    accepted = len(reflection.get_accepted())
    deferred = len(reflection.get_deferred())
    total = len(reflection.log.decisions)
    logger.info(
        "자동 분류 완료: ACCEPT %d개, DEFER %d개, 합계 %d개",
        accepted, deferred, total,
    )
    return reflection


def save_reflection_artifacts(
    reflection: ReviewReflection,
    artifact_manager: ReviewArtifactManager,
) -> None:
    """반영 판단 로그를 review-comments.md에 저장한다."""
    md = reflection.to_markdown()
    artifact_manager.save("review-comments.md", md)
    logger.info("review-comments.md 저장 완료")


def build_reflection_comment(reflection: ReviewReflection) -> str:
    """GitHub PR 코멘트용 반영 판단 요약 마크다운을 생성한다."""
    accepted = reflection.get_accepted()
    deferred = reflection.get_deferred()
    rejected = reflection.get_rejected()
    total = len(reflection.log.decisions)

    has_urgent_fixes = bool(accepted)
    status_icon = "⚠️" if has_urgent_fixes else "✅"
    lines = [
        f"{status_icon} **리뷰 반영 판단 (자동 분류)**\n",
    ]

    if reflection.log.overall_summary:
        lines.append(f"> {reflection.log.overall_summary}\n")

    lines += [
        "| 판정 | 건수 |",
        "|------|------|",
        f"| ✅ ACCEPT (즉시 반영) | {len(accepted)}개 |",
        f"| 🔜 DEFER (보류) | {len(deferred)}개 |",
        f"| ❌ REJECT | {len(rejected)}개 |",
        f"| 합계 | {total}개 |",
        "",
    ]

    if accepted:
        lines.append("### 즉시 반영 필요 항목 [p1/p2]\n")
        for d in accepted[:5]:  # 최대 5개만 표시
            lines.append(f"- **[{d.priority.value.upper()}]** `{d.file}:{d.line}` — {d.message[:80]}")
        if len(accepted) > 5:
            lines.append(f"- _{len(accepted) - 5}개 추가 항목은 review-comments.md 참조_")
        lines.append("")

    if deferred:
        lines.append("### 보류 항목 [p3/p4]\n")
        for d in deferred[:3]:  # 최대 3개만 표시
            lines.append(f"- **[{d.priority.value.upper()}]** `{d.file}:{d.line}` — {d.message[:60]}")
        if len(deferred) > 3:
            lines.append(f"- _{len(deferred) - 3}개 추가 항목은 review-comments.md 참조_")
        lines.append("")

    return "\n".join(lines)
