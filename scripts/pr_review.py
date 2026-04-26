"""PR 자동 리뷰 스크립트. GitHub Actions에서 실행되어 AI 코드 리뷰 코멘트를 생성한다."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

import anthropic

REVIEW_SYSTEM_PROMPT = """당신은 시니어 코드 리뷰어입니다.
Pull Request의 diff를 분석하고 구체적이고 실행 가능한 피드백을 제공하세요.

## 리뷰 기준
1. 버그: 로직 오류, 경계 조건, null/None 처리
2. 보안: 인젝션, 인증/인가, 데이터 노출
3. 성능: 불필요한 연산, N+1 쿼리
4. 아키텍처: 의존성 방향, 레이어 격리, 네이밍

## 출력 형식
JSON으로 출력하세요:
```json
{
  "summary": "전체 평가 요약 (한국어)",
  "approved": true,
  "comments": [
    {
      "path": "파일경로",
      "line": 10,
      "body": "코멘트 내용 (마크다운 가능)"
    }
  ]
}
```

코멘트가 없으면 comments를 빈 배열로 반환하세요.
사소한 스타일 이슈는 무시하세요 — 린터가 처리합니다.
"""


def get_diff() -> str:
    """PR의 diff를 가져온다."""
    result = subprocess.run(
        ["git", "diff", "origin/main...HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout


def run_review(diff: str) -> dict[str, Any]:
    """AI 리뷰를 실행한다."""
    client = anthropic.Anthropic()

    if len(diff) > 80000:
        diff = diff[:80000] + "\n\n... [diff 잘림]"

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        temperature=0.2,
        system=REVIEW_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"다음 PR diff를 리뷰해주세요:\n\n```diff\n{diff}\n```"}],
    )

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]

    return json.loads(cleaned)


def post_review(review: dict[str, Any], pr_number: str) -> None:
    """GitHub PR에 리뷰 코멘트를 게시한다."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")

    if not repo or not token:
        print("GITHUB_REPOSITORY 또는 GITHUB_TOKEN이 설정되지 않았습니다.")
        print(f"리뷰 요약: {review.get('summary', 'N/A')}")
        return

    # PR 요약 코멘트 게시
    summary = review.get("summary", "리뷰 완료")
    approved = review.get("approved", True)
    status_icon = "✅" if approved else "⚠️"

    comment_body = f"{status_icon} **AI 코드 리뷰**\n\n{summary}"

    comments = review.get("comments", [])
    if comments:
        comment_body += f"\n\n총 {len(comments)}개 코멘트가 있습니다."

    # gh CLI로 코멘트 게시
    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--body", comment_body],
        check=False,
    )

    # 인라인 코멘트 게시 (review comments)
    for comment in comments:
        body = comment.get("body", "")
        path = comment.get("path", "")
        line = comment.get("line", 0)
        if path and body and line > 0:
            # gh api를 사용하여 인라인 코멘트 생성
            # 개별 코멘트를 PR review comment로 게시
            review_data = json.dumps({
                "body": body,
                "commit_id": _get_head_sha(),
                "path": path,
                "line": line,
                "side": "RIGHT",
            })
            subprocess.run(
                ["gh", "api", f"repos/{repo}/pulls/{pr_number}/comments",
                 "--method", "POST", "--input", "-"],
                input=review_data, text=True, check=False,
            )


def _get_head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
    )
    return result.stdout.strip()


def main() -> None:
    pr_number = os.environ.get("PR_NUMBER", "")
    if not pr_number:
        print("PR_NUMBER 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    diff = get_diff()
    if not diff.strip():
        print("변경사항이 없습니다.")
        return

    print(f"PR #{pr_number} 리뷰 시작... (diff: {len(diff)} chars)")

    try:
        review = run_review(diff)
        post_review(review, pr_number)
        print(f"리뷰 완료: {'승인' if review.get('approved') else '변경 요청'}")
    except json.JSONDecodeError as e:
        print(f"리뷰 응답 파싱 실패: {e}", file=sys.stderr)
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"Anthropic API 에러: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
