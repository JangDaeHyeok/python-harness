"""추론적 센서: AI 코드 리뷰. LLM을 사용하여 코드 변경을 의미론적으로 분석한다."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.tools.api_client import DEFAULT_MODEL, HarnessClient

logger = logging.getLogger(__name__)


@dataclass
class ReviewComment:
    """리뷰 코멘트."""

    file: str
    line: int
    severity: str  # "critical", "major", "minor", "suggestion"
    category: str  # "bug", "security", "performance", "style", "logic"
    message: str
    suggestion: str


@dataclass
class ReviewResult:
    """코드 리뷰 결과."""

    approved: bool
    overall_assessment: str
    comments: list[ReviewComment]
    summary_for_llm: str


REVIEW_SYSTEM_PROMPT = """당신은 시니어 코드 리뷰어입니다.
git diff를 분석하고 구체적이고 실행 가능한 피드백을 제공하는 것이 임무입니다.

## 리뷰 기준

1. **버그**: 로직 오류, 경계 조건, null/None 처리
2. **보안**: 인젝션, 인증/인가, 데이터 노출
3. **성능**: 불필요한 연산, N+1 쿼리, 메모리 누수
4. **스타일**: 네이밍, 구조, 가독성
5. **로직**: 비즈니스 로직 정확성

## 출력 형식

반드시 JSON으로 출력하세요:

```json
{
  "approved": true,
  "overall_assessment": "전체 평가 요약",
  "comments": [
    {
      "file": "파일경로",
      "line": 10,
      "severity": "major",
      "category": "bug",
      "message": "문제 설명",
      "suggestion": "수정 제안"
    }
  ]
}
```
"""


class CodeReviewer:
    """추론적 센서: AI 코드 리뷰어."""

    def __init__(
        self,
        project_dir: str,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.model = model
        self.client = HarnessClient()

    def review_diff(self, base_branch: str = "main") -> ReviewResult:
        """현재 브랜치의 diff를 리뷰한다."""
        diff = self._get_diff(base_branch)
        if not diff.strip():
            return ReviewResult(
                approved=True,
                overall_assessment="변경사항이 없습니다.",
                comments=[],
                summary_for_llm="변경사항 없음.",
            )
        return self._review(diff)

    def review_diff_with_criteria(
        self, criteria_md: str, base_branch: str = "main"
    ) -> ReviewResult:
        """평가 기준을 포함하여 현재 브랜치의 diff를 리뷰한다.

        Args:
            criteria_md: CriteriaGenerator.to_markdown() 출력 문자열
            base_branch: 비교 기준 브랜치
        """
        diff = self._get_diff(base_branch)
        if not diff.strip():
            return ReviewResult(
                approved=True,
                overall_assessment="변경사항이 없습니다.",
                comments=[],
                summary_for_llm="변경사항 없음.",
            )
        return self._review(diff, extra_context=criteria_md)

    def review_staged(self) -> ReviewResult:
        """staged 변경사항을 리뷰한다."""
        diff = self._get_staged_diff()
        if not diff.strip():
            return ReviewResult(
                approved=True,
                overall_assessment="staged 변경사항이 없습니다.",
                comments=[],
                summary_for_llm="staged 변경사항 없음.",
            )
        return self._review(diff)

    def _review(self, diff: str, extra_context: str = "") -> ReviewResult:
        if len(diff) > 50000:
            diff = diff[:50000] + "\n\n... [diff 잘림: 50000자 초과]"

        user_content = f"다음 diff를 리뷰해주세요:\n\n```diff\n{diff}\n```"
        if extra_context:
            user_content = f"## 프로젝트 평가 기준\n\n{extra_context}\n\n---\n\n{user_content}"

        response = self.client.create_message(
            model=self.model,
            max_tokens=8000,
            temperature=0.2,
            system=REVIEW_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        return self._parse_response(text)

    def _parse_response(self, text: str) -> ReviewResult:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return ReviewResult(
                approved=False,
                overall_assessment="리뷰 응답 파싱 실패",
                comments=[],
                summary_for_llm=f"리뷰 파싱 실패. 원본:\n{text[:1000]}",
            )

        comments = [
            ReviewComment(
                file=c.get("file", ""),
                line=c.get("line", 0),
                severity=c.get("severity", "minor"),
                category=c.get("category", "style"),
                message=c.get("message", ""),
                suggestion=c.get("suggestion", ""),
            )
            for c in data.get("comments", [])
        ]

        return ReviewResult(
            approved=data.get("approved", False),
            overall_assessment=data.get("overall_assessment", ""),
            comments=comments,
            summary_for_llm=self._build_summary(data.get("approved", False), comments),
        )

    def _get_diff(self, base_branch: str) -> str:
        try:
            ref = self._resolve_base_ref(base_branch)
            result = subprocess.run(
                ["git", "diff", f"{ref}...HEAD"],
                cwd=str(self.project_dir),
                capture_output=True, text=True, timeout=30,
            )
        except Exception as e:
            raise RuntimeError(f"git diff 실행 실패: {e}") from e
        if result.returncode != 0:
            raise RuntimeError(
                f"git diff 실패 (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout

    def _resolve_base_ref(self, base_branch: str) -> str:
        """로컬 브랜치가 없으면 origin/{base_branch}로 폴백한다."""
        check = subprocess.run(
            ["git", "rev-parse", "--verify", base_branch],
            cwd=str(self.project_dir),
            capture_output=True, text=True, timeout=10,
        )
        if check.returncode == 0:
            return base_branch

        remote_ref = f"origin/{base_branch}"
        check_remote = subprocess.run(
            ["git", "rev-parse", "--verify", remote_ref],
            cwd=str(self.project_dir),
            capture_output=True, text=True, timeout=10,
        )
        if check_remote.returncode == 0:
            return remote_ref

        return base_branch

    def _get_staged_diff(self) -> str:
        try:
            result = subprocess.run(
                ["git", "diff", "--cached"],
                cwd=str(self.project_dir),
                capture_output=True, text=True, timeout=30,
            )
        except Exception as e:
            raise RuntimeError(f"git diff --cached 실행 실패: {e}") from e
        if result.returncode != 0:
            raise RuntimeError(
                f"git diff --cached 실패 (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout

    def format_as_pr_comments(self, result: ReviewResult) -> list[dict[str, Any]]:
        """리뷰 결과를 GitHub PR 코멘트 형식으로 변환한다."""
        pr_comments: list[dict[str, Any]] = []
        for comment in result.comments:
            body = f"**[{comment.severity.upper()}]** ({comment.category})\n\n"
            body += f"{comment.message}\n\n"
            if comment.suggestion:
                body += f"**제안**: {comment.suggestion}"

            pr_comments.append({
                "path": comment.file,
                "line": comment.line,
                "body": body,
            })
        return pr_comments

    def _build_summary(self, approved: bool, comments: list[ReviewComment]) -> str:
        status = "승인" if approved else "변경 요청"
        lines = [f"코드 리뷰 결과: {status}"]

        by_severity: dict[str, int] = {}
        for c in comments:
            by_severity[c.severity] = by_severity.get(c.severity, 0) + 1

        if by_severity:
            lines.append("심각도별: " + ", ".join(f"{k}: {v}개" for k, v in by_severity.items()))

        for c in comments:
            lines.append(f"- [{c.severity}] {c.file}:{c.line} — {c.message[:100]}")

        return "\n".join(lines)
