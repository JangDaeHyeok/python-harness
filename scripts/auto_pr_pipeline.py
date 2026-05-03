"""PR 자동화 파이프라인.

Git 커밋 → PR 생성 → 리뷰 수집 → 에이전트 리뷰 반영까지 전 과정을 자동화한다.

사용법:
    python scripts/auto_pr_pipeline.py --base main
    python scripts/auto_pr_pipeline.py --base main --auto-merge
    python scripts/auto_pr_pipeline.py --base main --skip-review
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.review.artifacts import ReviewArtifactManager
from harness.review.pr_body import PRBodyGenerator

logger = logging.getLogger(__name__)

_GH_TIMEOUT = 30
_REVIEW_POLL_INTERVAL = 30
_REVIEW_POLL_MAX_ATTEMPTS = 20

_ACTIONABLE_KEYWORDS = frozenset({
    "bug", "broken", "crash", "error", "fail", "failure", "fix", "incorrect",
    "missing", "must", "null", "race", "regression", "security", "should",
    "unsafe", "wrong",
    "고쳐", "누락", "버그", "실패", "오류", "위험", "잘못", "필수", "해야",
})

_NON_ACTIONABLE_KEYWORDS = frozenset({
    "awesome", "great", "looks good", "nice", "nit", "optional", "thanks",
    "좋습니다", "선택", "칭찬",
})


class PipelineError(RuntimeError):
    """PR 파이프라인 실행 실패."""


class ReviewDecision(StrEnum):
    """리뷰 코멘트 처리 판정."""

    ACCEPT = "accept"
    DEFER = "defer"
    IGNORE = "ignore"


@dataclass
class PRInfo:
    """생성된 PR 정보."""

    number: int = 0
    url: str = ""
    branch: str = ""
    title: str = ""


@dataclass
class ReviewComment:
    """외부 리뷰어(CodeRabbit 등)의 리뷰 코멘트."""

    comment_id: int = 0
    body: str = ""
    path: str = ""
    line: int = 0
    author: str = ""
    url: str = ""
    decision: ReviewDecision = ReviewDecision.DEFER
    reason: str = ""

    @property
    def is_actionable(self) -> bool:
        return self.decision == ReviewDecision.ACCEPT


@dataclass
class PipelineResult:
    """파이프라인 실행 결과."""

    pr_info: PRInfo = field(default_factory=PRInfo)
    review_comments: list[ReviewComment] = field(default_factory=list)
    actionable_comments: list[ReviewComment] = field(default_factory=list)
    review_applied: bool = False
    replies_posted: int = 0
    merged: bool = False
    errors: list[str] = field(default_factory=list)


def _run_gh(args: list[str], cwd: str, timeout: int = _GH_TIMEOUT) -> str:
    """gh CLI 명령을 실행한다."""
    try:
        result = subprocess.run(
            ["gh", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise PipelineError(f"gh {' '.join(args)} 실패: {result.stderr.strip()}")
        return result.stdout.strip()
    except FileNotFoundError as e:
        raise PipelineError("gh CLI를 찾을 수 없습니다. GitHub CLI가 설치되어 있는지 확인하세요.") from e


def _run_git(args: list[str], cwd: str, timeout: int = _GH_TIMEOUT) -> str:
    """git 명령을 실행한다."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise PipelineError(f"git {' '.join(args)} 실패: {result.stderr.strip()}")
    return result.stdout.strip()


def push_branch(project_dir: Path) -> str:
    """현재 브랜치를 원격에 푸시한다."""
    branch = _run_git(["branch", "--show-current"], str(project_dir))
    if not branch:
        raise PipelineError("현재 브랜치를 확인할 수 없습니다.")
    _run_git(["push", "-u", "origin", branch], str(project_dir))
    logger.info("브랜치 push 완료: %s", branch)
    return branch


def create_pr(
    project_dir: Path,
    base_branch: str,
    title: str = "",
    body: str = "",
) -> PRInfo:
    """GitHub PR을 생성한다."""
    if not title:
        branch = _run_git(["branch", "--show-current"], str(project_dir))
        title = f"feat: {branch}"

    if not body:
        artifact_mgr = ReviewArtifactManager(project_dir)
        pr_gen = PRBodyGenerator(project_dir)
        body = pr_gen.generate(artifact_mgr, base_branch)

    args = [
        "pr", "create",
        "--base", base_branch,
        "--title", title,
        "--body", body,
    ]
    output = _run_gh(args, str(project_dir))

    pr_url = output.strip().splitlines()[-1] if output else ""
    pr_number = 0
    if pr_url:
        with contextlib.suppress(ValueError, IndexError):
            pr_number = int(pr_url.rstrip("/").split("/")[-1])

    branch = _run_git(["branch", "--show-current"], str(project_dir))
    info = PRInfo(number=pr_number, url=pr_url, branch=branch, title=title)
    logger.info("PR 생성 완료: #%d %s", pr_number, pr_url)
    return info


def collect_review_comments(
    project_dir: Path,
    pr_number: int,
    *,
    poll: bool = False,
    max_attempts: int = _REVIEW_POLL_MAX_ATTEMPTS,
) -> list[ReviewComment]:
    """PR의 리뷰 코멘트를 수집한다. poll=True이면 코멘트가 올 때까지 대기한다."""
    comments: list[ReviewComment] = []

    for attempt in range(1, max_attempts + 1):
        raw = _run_gh(
            ["api", f"repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments"],
            str(project_dir),
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = []

        if isinstance(data, list):
            comments = [
                classify_review_comment(_comment_from_api(c))
                for c in data
                if isinstance(c, dict)
            ]

        if comments or not poll:
            break

        logger.info("리뷰 대기 중... (시도 %d/%d)", attempt, max_attempts)
        time.sleep(_REVIEW_POLL_INTERVAL)

    logger.info("리뷰 코멘트 %d개 수집", len(comments))
    return comments


def _comment_from_api(data: dict[str, object]) -> ReviewComment:
    user = data.get("user", {})
    author = ""
    if isinstance(user, dict):
        author = str(user.get("login", ""))
    return ReviewComment(
        comment_id=int(data.get("id", 0) or 0),
        body=str(data.get("body", "")),
        path=str(data.get("path", "")),
        line=int(data.get("line", 0) or 0),
        author=author,
        url=str(data.get("html_url", "")),
    )


def classify_review_comment(comment: ReviewComment) -> ReviewComment:
    """리뷰 코멘트가 자동 반영 대상인지 결정한다."""
    body = comment.body.lower()
    if not body.strip():
        comment.decision = ReviewDecision.IGNORE
        comment.reason = "빈 리뷰 코멘트"
        return comment

    if any(keyword in body for keyword in _ACTIONABLE_KEYWORDS):
        comment.decision = ReviewDecision.ACCEPT
        comment.reason = "수정 필요 키워드 감지"
        return comment

    if any(keyword in body for keyword in _NON_ACTIONABLE_KEYWORDS):
        comment.decision = ReviewDecision.DEFER
        comment.reason = "비필수 또는 칭찬성 코멘트"
        return comment

    if comment.path and comment.line > 0:
        comment.decision = ReviewDecision.ACCEPT
        comment.reason = "파일/라인이 지정된 인라인 리뷰"
        return comment

    comment.decision = ReviewDecision.DEFER
    comment.reason = "자동 반영 여부가 불명확함"
    return comment


def filter_actionable_comments(comments: list[ReviewComment]) -> list[ReviewComment]:
    """자동 반영 대상 코멘트만 반환한다."""
    return [c for c in comments if c.is_actionable]


def build_review_decision_markdown(comments: list[ReviewComment]) -> str:
    """리뷰 자동화 판정 로그를 마크다운으로 만든다."""
    lines = ["# PR 리뷰 자동화 판단 로그\n"]
    if not comments:
        lines.append("_수집된 리뷰 코멘트 없음_\n")
        return "\n".join(lines)

    for decision in ReviewDecision:
        items = [c for c in comments if c.decision == decision]
        if not items:
            continue
        lines.append(f"## {decision.value.upper()}\n")
        for c in items:
            location = f"{c.path}:{c.line}" if c.path else "conversation"
            lines.append(f"- `{location}` by `{c.author or 'unknown'}`")
            lines.append(f"  - 이유: {c.reason}")
            summary = " ".join(c.body.split())[:240]
            lines.append(f"  - 내용: {summary}")
        lines.append("")

    return "\n".join(lines)


def save_review_decision_log(project_dir: Path, comments: list[ReviewComment]) -> None:
    """브랜치별 review-comments.md에 자동화 판정 로그를 저장한다."""
    artifact_mgr = ReviewArtifactManager(project_dir)
    artifact_mgr.save("review-comments.md", build_review_decision_markdown(comments))


def apply_review_headless(
    project_dir: Path,
    comments: list[ReviewComment],
) -> bool:
    """리뷰 코멘트를 에이전트에게 전달하여 반영한다."""
    if not comments:
        return True

    review_summary_lines = [
        "다음 코드 리뷰 코멘트 중 자동 반영 대상으로 분류된 항목만 반영해주세요.\n",
        "사소한 리팩터링이나 요청 밖 변경은 하지 말고, 기존 테스트를 보존하세요.\n",
    ]
    for i, c in enumerate(comments, start=1):
        review_summary_lines.append(f"## 코멘트 {i}")
        if c.comment_id:
            review_summary_lines.append(f"**댓글 ID**: {c.comment_id}")
        if c.path:
            review_summary_lines.append(f"**파일**: {c.path}:{c.line}")
        review_summary_lines.append(f"**리뷰어**: {c.author}")
        review_summary_lines.append(f"**자동화 판정 이유**: {c.reason}")
        review_summary_lines.append(f"**내용**: {c.body}\n")

    prompt = "\n".join(review_summary_lines)

    try:
        result = subprocess.run(
            ["claude", "--print", "-p", prompt],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            logger.error("리뷰 반영 실패: %s", result.stderr.strip())
            return False
        logger.info("리뷰 반영 완료 (출력 %d자)", len(result.stdout))
        return True
    except (subprocess.SubprocessError, OSError) as e:
        logger.error("리뷰 반영 중 오류: %s", e)
        return False


def post_review_replies(
    project_dir: Path,
    pr_number: int,
    comments: list[ReviewComment],
    *,
    applied: bool,
) -> int:
    """반영 대상 리뷰 코멘트에 답글을 남긴다."""
    if not applied:
        return 0

    posted = 0
    for comment in comments:
        if comment.comment_id <= 0:
            continue
        body = (
            "자동 리뷰 반영 파이프라인에서 이 코멘트를 반영 대상으로 분류했고, "
            "수정 커밋에 반영했습니다."
        )
        try:
            _run_gh(
                [
                    "api",
                    f"repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments/{comment.comment_id}/replies",
                    "--method",
                    "POST",
                    "-f",
                    f"body={body}",
                ],
                str(project_dir),
            )
            posted += 1
        except PipelineError as e:
            logger.warning("리뷰 답글 작성 실패(comment_id=%d): %s", comment.comment_id, e)

    return posted


def merge_pr(project_dir: Path, pr_number: int, strategy: str = "squash") -> bool:
    """PR을 머지한다."""
    try:
        _run_gh(
            ["pr", "merge", str(pr_number), f"--{strategy}", "--delete-branch"],
            str(project_dir),
        )
        logger.info("PR #%d 머지 완료 (%s)", pr_number, strategy)
        return True
    except PipelineError as e:
        logger.error("PR 머지 실패: %s", e)
        return False


def run_pipeline(
    project_dir: Path,
    base_branch: str = "main",
    *,
    title: str = "",
    skip_review: bool = False,
    auto_merge: bool = False,
    poll_reviews: bool = True,
) -> PipelineResult:
    """PR 자동화 파이프라인 전체를 실행한다."""
    result = PipelineResult()

    try:
        push_branch(project_dir)
    except PipelineError as e:
        result.errors.append(f"push 실패: {e}")
        return result

    try:
        pr_info = create_pr(project_dir, base_branch, title=title)
        result.pr_info = pr_info
    except PipelineError as e:
        result.errors.append(f"PR 생성 실패: {e}")
        return result

    if not skip_review and pr_info.number > 0:
        comments = collect_review_comments(
            project_dir, pr_info.number, poll=poll_reviews,
        )
        result.review_comments = comments
        result.actionable_comments = filter_actionable_comments(comments)
        save_review_decision_log(project_dir, comments)

        if result.actionable_comments:
            applied = apply_review_headless(project_dir, result.actionable_comments)
            result.review_applied = applied

            if applied:
                try:
                    _run_git(["add", "-A"], str(project_dir))
                    _run_git(
                        ["commit", "-m", "fix: apply review comments"],
                        str(project_dir),
                    )
                    _run_git(["push"], str(project_dir))
                except PipelineError as e:
                    result.errors.append(f"리뷰 반영 커밋 실패: {e}")
                result.replies_posted = post_review_replies(
                    project_dir,
                    pr_info.number,
                    result.actionable_comments,
                    applied=applied,
                )

    if auto_merge and pr_info.number > 0:
        merged = merge_pr(project_dir, pr_info.number)
        result.merged = merged

    return result


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PR 자동화 파이프라인")
    parser.add_argument("--base", default="main", help="베이스 브랜치")
    parser.add_argument("--project-dir", default=".", help="프로젝트 디렉터리")
    parser.add_argument("--title", default="", help="PR 제목")
    parser.add_argument("--skip-review", action="store_true", help="리뷰 수집/반영 건너뛰기")
    parser.add_argument("--auto-merge", action="store_true", help="자동 머지")
    parser.add_argument("--no-poll", action="store_true", help="리뷰 폴링 비활성화")
    parser.add_argument("-v", "--verbose", action="store_true", help="상세 로그")

    args = parser.parse_args()
    setup_logging(args.verbose)

    project_dir = Path(args.project_dir).resolve()
    result = run_pipeline(
        project_dir,
        args.base,
        title=args.title,
        skip_review=args.skip_review,
        auto_merge=args.auto_merge,
        poll_reviews=not args.no_poll,
    )

    print(f"\nPR: {result.pr_info.url or '생성 실패'}")
    print(f"리뷰 코멘트: {len(result.review_comments)}개")
    print(f"반영 대상: {len(result.actionable_comments)}개")
    print(f"리뷰 반영: {'완료' if result.review_applied else '미반영'}")
    print(f"리뷰 답글: {result.replies_posted}개")
    print(f"머지: {'완료' if result.merged else '미실행'}")
    if result.errors:
        print(f"오류: {'; '.join(result.errors)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
