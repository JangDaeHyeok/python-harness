"""PR 본문 생성 스크립트.

현재 브랜치의 diff와 리뷰 산출물을 기반으로 pr-body.md를 생성한다.

사용 예:
    python scripts/create_pr_body.py --base main
    python scripts/create_pr_body.py --base main --output pr-body.md
    python scripts/create_pr_body.py --base main --summary "인증 모듈 리팩터링"
    python scripts/create_pr_body.py --base main --use-worktree
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _generate_body(project_dir: Path, base: str, summary: str, branch: str | None) -> str:
    """PR 본문을 생성하고 반환한다. worktree/직접 실행 모두에서 호출된다."""
    from harness.review.artifacts import ReviewArtifactManager
    from harness.review.pr_body import PRBodyGenerator

    artifact_manager = ReviewArtifactManager(project_dir, branch=branch)
    generator = PRBodyGenerator(project_dir)
    body = generator.generate(
        artifact_manager=artifact_manager,
        base_branch=base,
        summary=summary,
    )
    artifact_manager.save("pr-body.md", body)
    return body


def main() -> None:
    """PR 본문 생성 진입점."""
    parser = argparse.ArgumentParser(
        description="PR 본문(pr-body.md)을 생성합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--base", default="main", help="기준 브랜치 (기본: main)")
    parser.add_argument(
        "--project-dir",
        default=".",
        help="프로젝트 루트 디렉터리 (기본: 현재 디렉터리)",
    )
    parser.add_argument(
        "--summary",
        default="",
        help="PR 요약 텍스트 (없으면 design-intent.md에서 추출)",
    )
    parser.add_argument("--output", default=None, help="출력 파일 경로 (없으면 표준 출력)")
    parser.add_argument(
        "--branch",
        default=None,
        help="산출물 브랜치명 오버라이드 (기본: 현재 git 브랜치)",
    )
    parser.add_argument(
        "--use-worktree",
        action="store_true",
        help="git worktree에서 격리 실행 (메인 작업 트리를 변경하지 않음)",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists():
        print(f"오류: 프로젝트 디렉터리를 찾을 수 없음 - {project_dir}", file=sys.stderr)
        sys.exit(1)

    if args.use_worktree:
        body = _run_in_worktree(project_dir, args.base, args.summary, args.branch)
    else:
        body = _generate_body(project_dir, args.base, args.summary, args.branch)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(body, encoding="utf-8")
        print(f"PR 본문 저장 완료: {output_path}")
    else:
        print(body)


def _run_in_worktree(
    project_dir: Path, base: str, summary: str, branch: str | None
) -> str:
    """worktree에서 격리 실행하여 PR 본문을 생성한다.

    메인 작업 트리의 staged/unstaged 변경사항이 없는 깨끗한 스냅샷에서
    git diff 등을 실행하므로 더 일관된 결과를 보장한다.
    worktree 생성에 실패하면 WorktreeError를 발생시킨다 (자동 fallback 금지).
    """
    from harness.review.worktree import WorktreeManager

    mgr = WorktreeManager(project_dir)
    worktree_path = mgr.create_worktree()

    try:
        body = _generate_body(worktree_path, base, summary, branch)
        return body
    finally:
        mgr.cleanup_worktree(worktree_path)


if __name__ == "__main__":
    main()
