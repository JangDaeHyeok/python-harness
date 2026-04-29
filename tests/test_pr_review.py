"""pr_review 스크립트 단위 테스트."""

from __future__ import annotations

from unittest.mock import patch

from harness.sensors.inferential.code_reviewer import ReviewComment, ReviewResult

# pr_review.py is a script (sys.path manipulation), import the relevant functions directly
from scripts.pr_review import _count_inline_candidates, post_review_comment


class TestCountInlineCandidates:
    def test_counts_only_valid_file_and_line(self) -> None:
        result = ReviewResult(
            approved=False,
            overall_assessment="test",
            comments=[
                ReviewComment(file="a.py", line=10, severity="major", category="bug", message="m", suggestion=""),
                ReviewComment(file="", line=0, severity="minor", category="style", message="m", suggestion=""),
                ReviewComment(file="b.py", line=0, severity="minor", category="style", message="m", suggestion=""),
                ReviewComment(file="c.py", line=5, severity="minor", category="style", message="m", suggestion=""),
            ],
            summary_for_llm="",
        )
        assert _count_inline_candidates(result) == 2

    def test_zero_when_no_comments(self) -> None:
        result = ReviewResult(approved=True, overall_assessment="ok", comments=[], summary_for_llm="")
        assert _count_inline_candidates(result) == 0


class TestPostReviewCommentNoDuplication:
    def test_inline_comments_posted_exactly_once(self) -> None:
        """_post_inline_comments가 정확히 한 번만 호출되는지 검증한다."""
        result = ReviewResult(
            approved=False,
            overall_assessment="문제 발견",
            comments=[
                ReviewComment(file="a.py", line=10, severity="major", category="bug", message="msg", suggestion="fix"),
            ],
            summary_for_llm="",
        )

        with patch("scripts.pr_review._post_inline_comments") as mock_post, \
             patch("scripts.pr_review.subprocess.run"), \
             patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo"}):
            mock_post.return_value = [{"file": "a.py", "line": 10}]
            post_review_comment(result, "reflection", "42")

        assert mock_post.call_count == 1

    def test_no_inline_post_when_no_comments(self) -> None:
        result = ReviewResult(approved=True, overall_assessment="ok", comments=[], summary_for_llm="")

        with patch("scripts.pr_review._post_inline_comments") as mock_post, \
             patch("scripts.pr_review.subprocess.run"), \
             patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo"}):
            post_review_comment(result, "reflection", "42")

        mock_post.assert_not_called()
