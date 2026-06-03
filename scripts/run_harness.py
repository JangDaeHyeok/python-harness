"""
하네스 메인 실행 스크립트.

사용법:
    python3 scripts/run_harness.py "2D 레트로 게임 메이커를 만들어주세요"

    python3 scripts/run_harness.py \
        --project-dir ./my-project \
        --model claude-sonnet-4-6 \
        --max-retries 3 \
        --use-headless-phases \
        "브라우저에서 동작하는 DAW를 만들어주세요"

    # 구현 완료 후 PR 자동화까지 한 번에
    python3 scripts/run_harness.py \
        --mode modify \
        --use-headless-phases \
        --auto-pr --pr-base main \
        "로그인 에러 메시지를 개선해주세요"

    # 기존 PR 리뷰만 다시 처리
    python3 scripts/run_harness.py \
        --mode modify \
        --auto-pr --pr-current-pr --pr-no-poll \
        "현재 PR 리뷰 코멘트를 반영해주세요"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.agents.orchestrator import HarnessConfig, HarnessOrchestrator
from harness.context.structure_gate import check_structure, format_structure_violation
from harness.tools.api_client import ENDPOINT_ENV_VAR
from harness.tools.file_io import atomic_write_text

if TYPE_CHECKING:
    from scripts.auto_pr_pipeline import PipelineResult


def _checkpoint_exists(project_dir: Path, resume_run_id: str) -> bool:
    """재개 대상 체크포인트가 해당 프로젝트 디렉터리에 있는지 확인한다."""
    checkpoints_dir = project_dir / ".harness" / "checkpoints"
    if resume_run_id == "latest":
        return (checkpoints_dir / "latest.json").exists()
    return (checkpoints_dir / f"{resume_run_id}.json").exists()


def _resolve_project_dir(
    project_dir_arg: str | None,
    mode: str,
    resume_run_id: str,
) -> tuple[Path, str]:
    """CLI 옵션 조합에 따라 프로젝트 디렉터리와 실행 모드를 결정한다."""
    if project_dir_arg:
        return Path(project_dir_arg).resolve(), mode

    current_dir = Path(".").resolve()
    if mode == "modify":
        return current_dir, mode

    if resume_run_id and _checkpoint_exists(current_dir, resume_run_id):
        return current_dir, "modify"

    return Path("./project"), mode


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def enforce_structure_gate(project_dir: Path) -> None:
    """하네스 실행 전 고정 구조를 강제한다."""
    report = check_structure(project_dir)
    if report.ok:
        return
    print(format_structure_violation(report), file=sys.stderr)
    sys.exit(1)


def should_enforce_structure_gate(mode: str, resume_run_id: str) -> bool:
    """기존 프로젝트를 다루는 실행에서만 고정 구조를 강제한다."""
    return mode == "modify" or bool(resume_run_id)


def _save_auto_pr_artifact(
    project_dir: Path, result: PipelineResult | None, pipeline_failed: str
) -> None:
    """PR 자동화 결과를 구현 결과와 분리해 artifact로 기록한다."""
    artifact = {
        "pipeline_failed": pipeline_failed,
        "pr_url": result.pr_info.url if result else "",
        "pr_number": result.pr_info.number if result else 0,
        "review_comments": len(result.review_comments) if result else 0,
        "actionable_comments": len(result.actionable_comments) if result else 0,
        "review_applied": result.review_applied if result else False,
        "replies_posted": result.replies_posted if result else 0,
        "merged": result.merged if result else False,
        "warnings": list(result.warnings) if result else [],
        "errors": list(result.errors) if result else [],
    }
    artifact_path = project_dir / ".harness" / "artifacts" / "auto-pr-result.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        artifact_path, json.dumps(artifact, ensure_ascii=False, indent=2)
    )


def _run_auto_pr(
    project_dir: Path, args: argparse.Namespace
) -> PipelineResult | None:
    """구현 성공 후 PR 자동화 파이프라인을 실행하고 결과를 반환한다."""
    from scripts.auto_pr_pipeline import PipelineError, run_pipeline

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("PR 자동화 파이프라인 시작 (base=%s)", args.pr_base)
    logger.info("=" * 60)

    try:
        result = run_pipeline(
            project_dir,
            args.pr_base,
            title=args.pr_title,
            skip_review=args.pr_skip_review,
            auto_merge=args.pr_auto_merge,
            poll_reviews=not args.pr_no_poll,
            pr_number=args.pr_number,
            current_pr=args.pr_current_pr,
            confirm_github_writes=args.pr_confirm_github_writes,
        )
    except PipelineError as e:
        logger.error("PR 파이프라인 실패: %s", e)
        print("\n" + "!" * 60)
        print(f"  [PR 자동화 실패] {e}")
        print("  구현은 완료되었으나 PR 파이프라인이 중단되었습니다.")
        print("!" * 60)
        _save_auto_pr_artifact(project_dir, None, pipeline_failed=str(e))
        return None

    print(f"\n  PR: {result.pr_info.url or '생성 실패'}")
    print(f"  리뷰 코멘트: {len(result.review_comments)}개")
    print(f"  반영 대상: {len(result.actionable_comments)}개")
    print(f"  리뷰 반영: {'완료' if result.review_applied else '미반영'}")
    print(f"  리뷰 답글: {result.replies_posted}개")
    print(f"  머지: {'완료' if result.merged else '미실행'}")
    if result.warnings:
        logger.warning("PR 파이프라인 주의: %s", "; ".join(result.warnings))
        for warning in result.warnings:
            print(f"  [주의] {warning}")
    if result.errors:
        logger.warning("PR 파이프라인 오류: %s", "; ".join(result.errors))
        print("\n" + "!" * 60)
        for error in result.errors:
            print(f"  [PR 오류] {error}")
        print("!" * 60)

    _save_auto_pr_artifact(project_dir, result, pipeline_failed="")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="하네스 엔지니어링 프레임워크 실행")
    parser.add_argument("prompt", nargs="?", default="", help="프로젝트 설명 (1~4문장)")
    parser.add_argument(
        "--project-dir",
        default=None,
        help="프로젝트 디렉터리 (create 기본값: ./project, modify 기본값: 현재 디렉터리)",
    )
    parser.add_argument("--model", default="claude-sonnet-4-6", help="사용할 모델")
    parser.add_argument(
        "--api-endpoint",
        help=f"API 엔드포인트. 미지정 시 {ENDPOINT_ENV_VAR} 환경변수를 사용",
    )
    parser.add_argument(
        "--mode",
        choices=["create", "modify"],
        default="create",
        help="실행 모드: create(새 프로젝트 생성) 또는 modify(기존 코드베이스 수정)",
    )
    parser.add_argument("--max-retries", type=int, default=3, help="스프린트당 최대 재시도")
    parser.add_argument("--max-sprints", type=int, default=15, help="최대 스프린트 수")
    parser.add_argument("--app-url", default="http://localhost:3000", help="앱 URL")
    parser.add_argument("--no-context-reset", action="store_true", help="컨텍스트 리셋 비활성화")
    parser.add_argument("--run-id", default="", help="재개할 run_id (체크포인트)")
    parser.add_argument("--resume", action="store_true", help="가장 최근 체크포인트에서 재개")
    parser.add_argument(
        "--use-worktree",
        action="store_true",
        help="스프린트 구현을 임시 git worktree에서 격리 실행",
    )
    parser.add_argument(
        "--use-headless-phases",
        action="store_true",
        help="스프린트 구현을 Phase별 claude --print 독립 세션으로 실행",
    )
    parser.add_argument(
        "--headless-phase-timeout",
        type=int,
        default=600,
        help="헤드리스 Phase당 타임아웃(초)",
    )
    parser.add_argument(
        "--allow-empty-docs-diff",
        action="store_true",
        help="헤드리스 실행에서 docs-update 이후 docs-diff가 비어 있어도 계속 진행",
    )
    parser.add_argument(
        "--worktree-sync-exclude",
        action="append",
        default=[],
        metavar="PATH",
        help="worktree 구현 결과 동기화에서 제외할 파일/디렉터리명 (반복 지정 가능)",
    )
    pr_group = parser.add_argument_group("PR 자동화", "구현 완료 후 PR 파이프라인 연결")
    pr_group.add_argument(
        "--auto-pr",
        action="store_true",
        help="구현 성공 후 PR 자동화 파이프라인(push→PR→리뷰 반영)을 이어서 실행",
    )
    pr_group.add_argument(
        "--pr-base",
        default="main",
        help="PR 대상 브랜치 (--auto-pr 사용 시, 기본값: main)",
    )
    pr_group.add_argument(
        "--pr-title",
        default="",
        help="PR 제목 직접 지정 (--auto-pr로 새 PR 생성 시)",
    )
    pr_group.add_argument(
        "--pr-number",
        type=int,
        default=None,
        help="새 PR을 만들지 않고 기존 PR 번호의 리뷰를 처리 (--auto-pr 사용 시)",
    )
    pr_group.add_argument(
        "--pr-current-pr",
        action="store_true",
        help="현재 브랜치에 연결된 기존 PR 리뷰를 처리 (--auto-pr 사용 시)",
    )
    pr_group.add_argument(
        "--pr-no-poll",
        action="store_true",
        help="PR 리뷰 코멘트 폴링 비활성화 (--auto-pr 사용 시)",
    )
    pr_group.add_argument(
        "--pr-skip-review",
        action="store_true",
        help="PR 생성 후 리뷰 수집/반영 단계 건너뛰기 (--auto-pr 사용 시)",
    )
    pr_group.add_argument(
        "--pr-auto-merge",
        action="store_true",
        help="리뷰 반영 후 PR 자동 머지 (--auto-pr 사용 시)",
    )
    pr_group.add_argument(
        "--pr-confirm-github-writes",
        action="store_true",
        help=(
            "팀 공유 allow 밖 GitHub 쓰기 작업(리뷰 답글 gh api POST, gh pr merge)을 "
            "--auto-pr 흐름에서 명시적으로 승인"
        ),
    )
    pr_group.add_argument(
        "--fail-on-pr-error",
        action="store_true",
        help=(
            "PR 자동화가 실패하거나 오류를 기록하면 종료 코드 1로 종료 "
            "(구현 자체는 성공해도 PR 단계 실패를 CI에서 감지하려는 경우)"
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="상세 로그")

    args = parser.parse_args()
    if args.pr_number is not None and args.pr_current_pr:
        parser.error("--pr-number와 --pr-current-pr는 함께 사용할 수 없습니다.")
    setup_logging(args.verbose)

    if args.api_endpoint:
        os.environ[ENDPOINT_ENV_VAR] = args.api_endpoint

    resume_run_id = ""
    if args.resume:
        resume_run_id = "latest"
    elif args.run_id:
        resume_run_id = args.run_id

    project_dir, mode = _resolve_project_dir(args.project_dir, args.mode, resume_run_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    config = HarnessConfig(
        project_dir=str(project_dir),
        model=args.model,
        max_sprint_retries=args.max_retries,
        max_total_sprints=args.max_sprints,
        app_url=args.app_url,
        enable_context_reset=not args.no_context_reset,
        mode=mode,
        use_worktree_isolation=args.use_worktree,
        worktree_sync_excludes=args.worktree_sync_exclude,
        use_headless_phases=args.use_headless_phases,
        headless_phase_timeout=args.headless_phase_timeout,
        require_docs_diff_for_headless=not args.allow_empty_docs_diff,
    )

    if not resume_run_id and not args.prompt:
        parser.error("prompt가 필요합니다. 중단된 실행을 재개하려면 --resume 또는 --run-id를 사용하세요.")

    if should_enforce_structure_gate(mode, resume_run_id):
        enforce_structure_gate(project_dir)

    orchestrator = HarnessOrchestrator(config)

    try:
        summary = orchestrator.run(args.prompt, resume_run_id=resume_run_id)
        print("\n" + "=" * 60)
        print("실행 완료!")
        print(f"  프로젝트: {summary['title']}")
        print(f"  스프린트: {summary['passed_sprints']}/{summary['total_sprints']} 통과")
        print(f"  비용: ${summary['total_cost_usd']}")
        print(f"  소요 시간: {summary['elapsed_human']}")
        print("=" * 60)

        if args.auto_pr and summary.get("passed_sprints", 0) > 0:
            pr_result = _run_auto_pr(project_dir, args)
            if args.fail_on_pr_error and (
                pr_result is None or pr_result.errors
            ):
                sys.exit(1)
        elif args.auto_pr:
            logging.getLogger(__name__).warning(
                "통과한 스프린트가 없어 PR 자동화를 건너뜁니다."
            )
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단됨")
        sys.exit(1)


if __name__ == "__main__":
    main()
