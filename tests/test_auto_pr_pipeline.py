"""scripts/auto_pr_pipeline.py 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from scripts.auto_pr_pipeline import (
    PipelineResult,
    PRInfo,
    ReviewComment,
    ReviewDecision,
    build_review_decision_markdown,
    classify_review_comment,
    filter_actionable_comments,
    post_review_replies,
    run_pipeline,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestPRInfo:
    def test_defaults(self) -> None:
        info = PRInfo()
        assert info.number == 0
        assert info.url == ""
        assert info.branch == ""

    def test_with_values(self) -> None:
        info = PRInfo(number=42, url="https://github.com/org/repo/pull/42", branch="feat/test")
        assert info.number == 42
        assert "42" in info.url


class TestReviewComment:
    def test_defaults(self) -> None:
        rc = ReviewComment()
        assert rc.comment_id == 0
        assert rc.body == ""
        assert rc.path == ""
        assert rc.line == 0
        assert rc.decision == ReviewDecision.DEFER
        assert not rc.is_actionable

    def test_with_values(self) -> None:
        rc = ReviewComment(
            comment_id=123,
            body="수정 필요",
            path="src/main.py",
            line=42,
            author="coderabbit",
            decision=ReviewDecision.ACCEPT,
        )
        assert "수정 필요" in rc.body
        assert rc.author == "coderabbit"
        assert rc.is_actionable


class TestReviewClassification:
    def test_classifies_actionable_keyword(self) -> None:
        comment = classify_review_comment(
            ReviewComment(body="이 null 오류는 fix 해야 합니다", path="a.py", line=10)
        )
        assert comment.decision == ReviewDecision.ACCEPT
        assert "키워드" in comment.reason

    def test_classifies_inline_comment_as_actionable(self) -> None:
        comment = classify_review_comment(
            ReviewComment(body="이 로직을 확인해주세요", path="a.py", line=10)
        )
        assert comment.decision == ReviewDecision.ACCEPT

    def test_defers_non_actionable_comment(self) -> None:
        comment = classify_review_comment(
            ReviewComment(body="Looks good, optional nit입니다")
        )
        assert comment.decision == ReviewDecision.DEFER

    def test_ignores_empty_comment(self) -> None:
        comment = classify_review_comment(ReviewComment(body="   "))
        assert comment.decision == ReviewDecision.IGNORE

    def test_filter_actionable_comments(self) -> None:
        comments = [
            ReviewComment(body="fix this", decision=ReviewDecision.ACCEPT),
            ReviewComment(body="nice", decision=ReviewDecision.DEFER),
        ]
        assert filter_actionable_comments(comments) == [comments[0]]

    def test_build_review_decision_markdown(self) -> None:
        md = build_review_decision_markdown([
            ReviewComment(
                body="fix this bug",
                path="a.py",
                line=10,
                author="coderabbit",
                decision=ReviewDecision.ACCEPT,
                reason="수정 필요",
            )
        ])
        assert "PR 리뷰 자동화 판단 로그" in md
        assert "ACCEPT" in md
        assert "a.py:10" in md


class TestPipelineResult:
    def test_defaults(self) -> None:
        result = PipelineResult()
        assert result.pr_info.number == 0
        assert result.review_comments == []
        assert result.actionable_comments == []
        assert not result.review_applied
        assert result.replies_posted == 0
        assert not result.merged
        assert result.errors == []

    def test_with_errors(self) -> None:
        result = PipelineResult(errors=["push 실패", "PR 생성 실패"])
        assert len(result.errors) == 2

    def test_with_review(self) -> None:
        result = PipelineResult(
            pr_info=PRInfo(number=1),
            review_comments=[ReviewComment(body="좋은 코드!")],
            actionable_comments=[ReviewComment(body="fix", decision=ReviewDecision.ACCEPT)],
            review_applied=True,
            replies_posted=1,
        )
        assert len(result.review_comments) == 1
        assert len(result.actionable_comments) == 1
        assert result.review_applied
        assert result.replies_posted == 1


class TestReviewReplies:
    def test_post_review_replies_skips_when_not_applied(self, tmp_path: Path) -> None:
        with patch("scripts.auto_pr_pipeline._run_gh") as mock_gh:
            posted = post_review_replies(
                tmp_path,
                1,
                [ReviewComment(comment_id=10, decision=ReviewDecision.ACCEPT)],
                applied=False,
            )

        assert posted == 0
        mock_gh.assert_not_called()

    def test_post_review_replies_posts_for_comment_ids(self, tmp_path: Path) -> None:
        with patch("scripts.auto_pr_pipeline._run_gh", return_value="{}") as mock_gh:
            posted = post_review_replies(
                tmp_path,
                1,
                [
                    ReviewComment(comment_id=10, decision=ReviewDecision.ACCEPT),
                    ReviewComment(comment_id=0, decision=ReviewDecision.ACCEPT),
                ],
                applied=True,
            )

        assert posted == 1
        assert "comments/10/replies" in mock_gh.call_args.args[0][1]


class TestRunPipelineReviewAutomation:
    def test_pipeline_filters_applies_and_replies(self, tmp_path: Path) -> None:
        with (
            patch("scripts.auto_pr_pipeline.push_branch", return_value="feat/test"),
            patch(
                "scripts.auto_pr_pipeline.create_pr",
                return_value=PRInfo(number=7, url="https://github.com/o/r/pull/7"),
            ),
            patch(
                "scripts.auto_pr_pipeline.collect_review_comments",
                return_value=[
                    ReviewComment(
                        comment_id=1,
                        body="fix this bug",
                        path="a.py",
                        line=3,
                        author="coderabbit",
                        decision=ReviewDecision.ACCEPT,
                        reason="수정 필요",
                    ),
                    ReviewComment(
                        comment_id=2,
                        body="looks good",
                        author="coderabbit",
                        decision=ReviewDecision.DEFER,
                        reason="칭찬",
                    ),
                ],
            ),
            patch("scripts.auto_pr_pipeline.save_review_decision_log") as mock_save,
            patch("scripts.auto_pr_pipeline.apply_review_headless", return_value=True) as mock_apply,
            patch("scripts.auto_pr_pipeline._run_git", return_value=""),
            patch("scripts.auto_pr_pipeline.post_review_replies", return_value=1) as mock_replies,
        ):
            result = run_pipeline(tmp_path, poll_reviews=False)

        assert len(result.review_comments) == 2
        assert len(result.actionable_comments) == 1
        assert result.review_applied is True
        assert result.replies_posted == 1
        mock_save.assert_called_once()
        mock_apply.assert_called_once_with(tmp_path, [result.actionable_comments[0]])
        mock_replies.assert_called_once()
