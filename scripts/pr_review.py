"""PR 자동 리뷰 스크립트. GitHub Actions에서 실행되어 AI 코드 리뷰 코멘트를 생성한다."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.review.artifacts import ReviewArtifactManager
from harness.review.pipeline_integration import (
    build_reflection_comment,
    classify_review_result,
    save_reflection_artifacts,
)
from harness.sensors.inferential.code_reviewer import CodeReviewer, ReviewResult
from harness.tools.api_client import ENDPOINT_ENV_VAR, APIError


def _count_inline_candidates(result: ReviewResult) -> int:
    """인라인 코멘트로 게시 가능한 항목 수를 반환한다 (side effect 없음)."""
    return sum(1 for c in result.comments if c.file and c.line > 0)


def post_review_comment(result: ReviewResult, reflection_md: str, pr_number: str) -> None:
    """GitHub PR에 리뷰 요약 및 반영 판단 코멘트를 게시한다."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    status_icon = "✅" if result.approved else "⚠️"
    summary_block = (
        f"{status_icon} **AI 코드 리뷰**\n\n{result.overall_assessment}"
    )

    inline_count = _count_inline_candidates(result)
    if result.comments:
        summary_block += f"\n\n총 {len(result.comments)}개 코멘트 (인라인 코멘트 {inline_count}개 포함)"

    full_body = f"{summary_block}\n\n---\n\n{reflection_md}"

    if not repo:
        print("GITHUB_REPOSITORY가 설정되지 않아 로컬 출력으로 대체합니다.")
        print(full_body)
        return

    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--body", full_body],
        check=False,
    )

    if result.comments:
        try:
            posted = _post_inline_comments(result, pr_number, repo)
            expected = _count_inline_candidates(result)
            if len(posted) < expected:
                print(
                    f"인라인 코멘트 일부 게시 실패: {len(posted)}/{expected}개 성공",
                    file=sys.stderr,
                )
        except RuntimeError as e:
            print(f"인라인 코멘트 게시 실패: {e}", file=sys.stderr)


def _post_inline_comments(
    result: ReviewResult, pr_number: str, repo: str
) -> list[dict[str, object]]:
    """인라인 PR 코멘트를 게시하고 게시된 항목 목록을 반환한다."""
    head_sha = _get_head_sha()
    posted: list[dict[str, object]] = []

    for comment in result.comments:
        if not (comment.file and comment.line > 0):
            continue
        body = (
            f"**[{comment.severity.upper()}]** ({comment.category})\n\n"
            f"{comment.message}"
        )
        if comment.suggestion:
            body += f"\n\n**제안**: {comment.suggestion}"

        review_data = json.dumps({
            "body": body,
            "commit_id": head_sha,
            "path": comment.file,
            "line": comment.line,
            "side": "RIGHT",
        })
        api_result = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{pr_number}/comments",
             "--method", "POST", "--input", "-"],
            input=review_data, text=True, check=False,
            capture_output=True,
        )
        if api_result.returncode != 0:
            print(
                f"인라인 코멘트 게시 실패 ({comment.file}:{comment.line}): "
                f"{api_result.stderr.strip()}",
                file=sys.stderr,
            )
            continue
        posted.append({"file": comment.file, "line": comment.line})

    return posted


def _get_head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
    )
    sha = result.stdout.strip()
    if not sha:
        raise RuntimeError("HEAD SHA를 가져올 수 없습니다 (git rev-parse 실패)")
    return sha


def parse_args() -> argparse.Namespace:
    """명령줄 인자를 파싱한다."""
    parser = argparse.ArgumentParser(description="PR AI 코드 리뷰를 실행한다.")
    parser.add_argument(
        "--api-endpoint",
        help=f"API 엔드포인트. 미지정 시 {ENDPOINT_ENV_VAR} 환경변수를 사용",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.api_endpoint:
        os.environ[ENDPOINT_ENV_VAR] = args.api_endpoint

    pr_number = os.environ.get("PR_NUMBER", "")
    if not pr_number:
        print("PR_NUMBER 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    project_dir = Path(__file__).parent.parent
    reviewer = CodeReviewer(str(project_dir))
    artifact_manager = ReviewArtifactManager(project_dir)

    print(f"PR #{pr_number} 리뷰 시작...")

    try:
        result = reviewer.review_diff(base_branch="main")
    except APIError as e:
        print(f"API 에러: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"리뷰 완료: {'승인' if result.approved else '변경 요청'} (코멘트 {len(result.comments)}개)")

    reflection = classify_review_result(result)
    save_reflection_artifacts(reflection, artifact_manager)
    reflection_md = build_reflection_comment(reflection)

    post_review_comment(result, reflection_md, pr_number)
    print("PR 코멘트 게시 완료")


if __name__ == "__main__":
    main()
