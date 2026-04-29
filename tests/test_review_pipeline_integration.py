"""tests/test_review_pipeline_integration.py — pipeline_integration 단위 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

from harness.review.pipeline_integration import (
    build_reflection_comment,
    classify_review_result,
    save_reflection_artifacts,
)
from harness.review.reflection import Decision, ReviewReflection
from harness.sensors.inferential.code_reviewer import ReviewComment, ReviewResult

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_result(comments: list[ReviewComment], approved: bool = True) -> ReviewResult:
    return ReviewResult(
        approved=approved,
        overall_assessment="테스트 평가",
        comments=comments,
        summary_for_llm="테스트 요약",
    )


def _make_comment(severity: str, file: str = "foo.py", line: int = 1) -> ReviewComment:
    return ReviewComment(
        file=file,
        line=line,
        severity=severity,
        category="bug",
        message=f"{severity} 문제 발견",
        suggestion="수정 필요",
    )


# ---------------------------------------------------------------------------
# classify_review_result
# ---------------------------------------------------------------------------

class TestClassifyReviewResult:
    def test_empty_comments_returns_reflection(self) -> None:
        result = _make_result([])
        reflection = classify_review_result(result)
        assert isinstance(reflection, ReviewReflection)
        assert len(reflection.log.decisions) == 0

    def test_overall_summary_copied(self) -> None:
        result = _make_result([])
        reflection = classify_review_result(result)
        assert reflection.log.overall_summary == "테스트 평가"

    def test_sprint_number_set(self) -> None:
        result = _make_result([])
        reflection = classify_review_result(result, sprint_number=3)
        assert reflection.log.sprint_number == 3

    def test_critical_classified_as_accept(self) -> None:
        result = _make_result([_make_comment("critical")])
        reflection = classify_review_result(result)
        accepted = reflection.get_accepted()
        assert len(accepted) == 1
        assert accepted[0].decision == Decision.ACCEPT

    def test_major_classified_as_accept(self) -> None:
        result = _make_result([_make_comment("major")])
        reflection = classify_review_result(result)
        assert len(reflection.get_accepted()) == 1

    def test_minor_classified_as_defer(self) -> None:
        result = _make_result([_make_comment("minor")])
        reflection = classify_review_result(result)
        assert len(reflection.get_deferred()) == 1

    def test_suggestion_classified_as_defer(self) -> None:
        result = _make_result([_make_comment("suggestion")])
        reflection = classify_review_result(result)
        assert len(reflection.get_deferred()) == 1

    def test_mixed_severities(self) -> None:
        comments = [
            _make_comment("critical", "a.py", 1),
            _make_comment("major", "b.py", 2),
            _make_comment("minor", "c.py", 3),
            _make_comment("suggestion", "d.py", 4),
        ]
        result = _make_result(comments)
        reflection = classify_review_result(result)
        assert len(reflection.get_accepted()) == 2
        assert len(reflection.get_deferred()) == 2
        assert len(reflection.log.decisions) == 4

    def test_unknown_severity_classified_as_defer(self) -> None:
        # auto_classify maps unknown severity to P3 (default), which is DEFER
        comment = _make_comment("unknown_level")
        result = _make_result([comment])
        reflection = classify_review_result(result)
        deferred = reflection.get_deferred()
        assert len(deferred) == 1
        assert deferred[0].decision == Decision.DEFER


# ---------------------------------------------------------------------------
# save_reflection_artifacts
# ---------------------------------------------------------------------------

class TestSaveReflectionArtifacts:
    def test_saves_to_review_comments_md(self) -> None:
        reflection = ReviewReflection(sprint_number=1)
        reflection.log.overall_summary = "전체 요약"

        artifact_manager = MagicMock()
        save_reflection_artifacts(reflection, artifact_manager)

        artifact_manager.save.assert_called_once()
        call_args = artifact_manager.save.call_args
        assert call_args[0][0] == "review-comments.md"
        assert isinstance(call_args[0][1], str)

    def test_saved_content_is_markdown(self) -> None:
        reflection = ReviewReflection(sprint_number=2)
        reflection.log.overall_summary = "요약"

        saved_content: list[str] = []

        def capture_save(name: str, content: str) -> None:
            saved_content.append(content)

        artifact_manager = MagicMock()
        artifact_manager.save.side_effect = capture_save
        save_reflection_artifacts(reflection, artifact_manager)

        assert saved_content
        assert "리뷰 반영 판단" in saved_content[0]


# ---------------------------------------------------------------------------
# build_reflection_comment
# ---------------------------------------------------------------------------

class TestBuildReflectionComment:
    def _make_reflection_with_comments(self) -> ReviewReflection:
        reflection = ReviewReflection(sprint_number=1)
        reflection.log.overall_summary = "전반적으로 양호"
        for i, sev in enumerate(["critical", "major", "minor", "suggestion"]):
            reflection.add_decision(
                _make_comment(sev, f"file{i}.py", i + 1),
                Decision.ACCEPT if sev in ("critical", "major") else Decision.DEFER,
                "테스트 이유",
            )
        return reflection

    def test_returns_string(self) -> None:
        reflection = ReviewReflection(sprint_number=1)
        result = build_reflection_comment(reflection)
        assert isinstance(result, str)

    def test_contains_summary_table(self) -> None:
        reflection = self._make_reflection_with_comments()
        md = build_reflection_comment(reflection)
        assert "ACCEPT" in md
        assert "DEFER" in md
        assert "|" in md

    def test_contains_overall_summary(self) -> None:
        reflection = self._make_reflection_with_comments()
        md = build_reflection_comment(reflection)
        assert "전반적으로 양호" in md

    def test_shows_accept_items(self) -> None:
        reflection = self._make_reflection_with_comments()
        md = build_reflection_comment(reflection)
        assert "즉시 반영" in md

    def test_shows_defer_items(self) -> None:
        reflection = self._make_reflection_with_comments()
        md = build_reflection_comment(reflection)
        assert "보류" in md

    def test_empty_reflection_no_sections(self) -> None:
        reflection = ReviewReflection(sprint_number=0)
        md = build_reflection_comment(reflection)
        assert "즉시 반영 필요 항목" not in md
        assert "보류 항목" not in md

    def test_truncates_long_accepted_list(self) -> None:
        reflection = ReviewReflection(sprint_number=1)
        for i in range(8):
            reflection.add_decision(
                _make_comment("critical", f"f{i}.py", i + 1),
                Decision.ACCEPT,
                "이유",
            )
        md = build_reflection_comment(reflection)
        assert "추가 항목" in md

    def test_truncates_long_deferred_list(self) -> None:
        reflection = ReviewReflection(sprint_number=1)
        for i in range(5):
            reflection.add_decision(
                _make_comment("minor", f"f{i}.py", i + 1),
                Decision.DEFER,
                "이유",
            )
        md = build_reflection_comment(reflection)
        assert "추가 항목" in md

    def test_status_icon_warning_when_accepted_items_exist(self) -> None:
        reflection = ReviewReflection(sprint_number=1)
        reflection.add_decision(
            _make_comment("critical"), Decision.ACCEPT, "이유"
        )
        md = build_reflection_comment(reflection)
        assert "⚠️" in md

    def test_status_icon_ok_when_no_accepted_items(self) -> None:
        reflection = ReviewReflection(sprint_number=1)
        reflection.add_decision(
            _make_comment("minor"), Decision.DEFER, "이유"
        )
        md = build_reflection_comment(reflection)
        assert "✅" in md

    def test_status_icon_ok_when_empty(self) -> None:
        reflection = ReviewReflection(sprint_number=0)
        md = build_reflection_comment(reflection)
        assert "✅" in md
