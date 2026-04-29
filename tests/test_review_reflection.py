"""ReviewReflection 단위 테스트."""

from __future__ import annotations

from harness.review.reflection import (
    SEVERITY_TO_PRIORITY,
    CommentDecision,
    Decision,
    Priority,
    ReviewReflection,
)
from harness.sensors.inferential.code_reviewer import ReviewComment


def make_comment(
    severity: str = "minor",
    category: str = "style",
    file: str = "foo.py",
    line: int = 10,
    message: str = "문제 설명",
    suggestion: str = "수정 제안",
) -> ReviewComment:
    return ReviewComment(
        file=file,
        line=line,
        severity=severity,
        category=category,
        message=message,
        suggestion=suggestion,
    )


class TestDecisionEnum:
    def test_values(self) -> None:
        assert Decision.ACCEPT.value == "ACCEPT"
        assert Decision.REJECT.value == "REJECT"
        assert Decision.DEFER.value == "DEFER"


class TestPriorityEnum:
    def test_values(self) -> None:
        assert Priority.P1.value == "p1"
        assert Priority.P4.value == "p4"


class TestSeverityToPriority:
    def test_critical_is_p1(self) -> None:
        assert SEVERITY_TO_PRIORITY["critical"] == Priority.P1

    def test_major_is_p2(self) -> None:
        assert SEVERITY_TO_PRIORITY["major"] == Priority.P2

    def test_minor_is_p3(self) -> None:
        assert SEVERITY_TO_PRIORITY["minor"] == Priority.P3

    def test_suggestion_is_p4(self) -> None:
        assert SEVERITY_TO_PRIORITY["suggestion"] == Priority.P4


class TestCommentDecision:
    def test_priority_auto_set_from_severity(self) -> None:
        cd = CommentDecision(
            comment_id="rc-001",
            file="foo.py",
            line=1,
            severity="critical",
            category="bug",
            message="msg",
            suggestion="",
            decision=Decision.ACCEPT,
            reason="reason",
        )
        assert cd.priority == Priority.P1

    def test_priority_unknown_severity_defaults_to_p3(self) -> None:
        cd = CommentDecision(
            comment_id="rc-002",
            file="bar.py",
            line=1,
            severity="unknown-sev",
            category="style",
            message="msg",
            suggestion="",
            decision=Decision.DEFER,
            reason="reason",
        )
        assert cd.priority == Priority.P3


class TestReviewReflection:
    def test_add_decision_returns_comment_decision(self) -> None:
        reflection = ReviewReflection(sprint_number=1)
        comment = make_comment(severity="critical")
        cd = reflection.add_decision(comment, Decision.ACCEPT, "즉시 수정 필요")

        assert isinstance(cd, CommentDecision)
        assert cd.decision == Decision.ACCEPT
        assert cd.reason == "즉시 수정 필요"
        assert cd.priority == Priority.P1

    def test_add_decision_increments_id(self) -> None:
        reflection = ReviewReflection()
        c1 = reflection.add_decision(make_comment(), Decision.ACCEPT, "r")
        c2 = reflection.add_decision(make_comment(), Decision.DEFER, "r")
        assert c1.comment_id != c2.comment_id
        assert c1.comment_id < c2.comment_id  # lexicographic order: rc-001 < rc-002

    def test_add_decision_stores_in_log(self) -> None:
        reflection = ReviewReflection(sprint_number=2)
        reflection.add_decision(make_comment(), Decision.ACCEPT, "ok")
        assert len(reflection.log.decisions) == 1
        assert reflection.log.sprint_number == 2

    def test_auto_classify_critical_returns_accept(self) -> None:
        reflection = ReviewReflection()
        comment = make_comment(severity="critical")
        assert reflection.auto_classify(comment) == Decision.ACCEPT

    def test_auto_classify_major_returns_accept(self) -> None:
        reflection = ReviewReflection()
        comment = make_comment(severity="major")
        assert reflection.auto_classify(comment) == Decision.ACCEPT

    def test_auto_classify_minor_returns_defer(self) -> None:
        reflection = ReviewReflection()
        comment = make_comment(severity="minor")
        assert reflection.auto_classify(comment) == Decision.DEFER

    def test_auto_classify_suggestion_returns_defer(self) -> None:
        reflection = ReviewReflection()
        comment = make_comment(severity="suggestion")
        assert reflection.auto_classify(comment) == Decision.DEFER

    def test_get_accepted(self) -> None:
        reflection = ReviewReflection()
        reflection.add_decision(make_comment(), Decision.ACCEPT, "r")
        reflection.add_decision(make_comment(), Decision.REJECT, "r")
        reflection.add_decision(make_comment(), Decision.ACCEPT, "r")

        assert len(reflection.get_accepted()) == 2
        assert all(d.decision == Decision.ACCEPT for d in reflection.get_accepted())

    def test_get_rejected(self) -> None:
        reflection = ReviewReflection()
        reflection.add_decision(make_comment(), Decision.REJECT, "r")
        assert len(reflection.get_rejected()) == 1

    def test_get_deferred(self) -> None:
        reflection = ReviewReflection()
        reflection.add_decision(make_comment(), Decision.DEFER, "r")
        reflection.add_decision(make_comment(), Decision.DEFER, "r")
        assert len(reflection.get_deferred()) == 2

    def test_to_markdown_empty_decisions(self) -> None:
        reflection = ReviewReflection(sprint_number=1)
        md = reflection.to_markdown()
        assert "리뷰 반영 판단 로그" in md
        assert "없음" in md

    def test_to_markdown_includes_decisions(self) -> None:
        reflection = ReviewReflection(sprint_number=3)
        comment = make_comment(
            severity="critical", file="harness/review/foo.py", line=42, message="버그 발견"
        )
        reflection.add_decision(comment, Decision.ACCEPT, "즉시 수정 필요")
        md = reflection.to_markdown()

        assert "harness/review/foo.py" in md
        assert "42" in md
        assert "ACCEPT" in md
        assert "즉시 수정 필요" in md

    def test_to_markdown_groups_by_priority(self) -> None:
        reflection = ReviewReflection()
        reflection.add_decision(make_comment(severity="critical"), Decision.ACCEPT, "r")
        reflection.add_decision(make_comment(severity="suggestion"), Decision.DEFER, "r")
        md = reflection.to_markdown()

        assert "[P1]" in md
        assert "[P4]" in md

    def test_to_markdown_includes_statistics(self) -> None:
        reflection = ReviewReflection()
        reflection.add_decision(make_comment(), Decision.ACCEPT, "r")
        reflection.add_decision(make_comment(), Decision.REJECT, "r")
        reflection.add_decision(make_comment(), Decision.DEFER, "r")
        md = reflection.to_markdown()

        assert "ACCEPT: 1개" in md
        assert "REJECT: 1개" in md
        assert "DEFER: 1개" in md
        assert "합계: 3개" in md

    def test_to_markdown_sprint_number(self) -> None:
        reflection = ReviewReflection(sprint_number=7)
        md = reflection.to_markdown()
        assert "Sprint 7" in md
