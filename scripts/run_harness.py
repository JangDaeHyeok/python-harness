"""
하네스 메인 실행 스크립트.

사용법:
    python scripts/run_harness.py "2D 레트로 게임 메이커를 만들어주세요"

    python scripts/run_harness.py \
        --project-dir ./my-project \
        --model claude-sonnet-4-6 \
        --max-retries 3 \
        --use-headless-phases \
        "브라우저에서 동작하는 DAW를 만들어주세요"
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.agents.orchestrator import HarnessConfig, HarnessOrchestrator
from harness.tools.api_client import ENDPOINT_ENV_VAR


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
    parser.add_argument("-v", "--verbose", action="store_true", help="상세 로그")

    args = parser.parse_args()
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

    orchestrator = HarnessOrchestrator(config)

    if not resume_run_id and not args.prompt:
        parser.error("prompt가 필요합니다. 중단된 실행을 재개하려면 --resume 또는 --run-id를 사용하세요.")

    try:
        summary = orchestrator.run(args.prompt, resume_run_id=resume_run_id)
        print("\n" + "=" * 60)
        print("실행 완료!")
        print(f"  프로젝트: {summary['title']}")
        print(f"  스프린트: {summary['passed_sprints']}/{summary['total_sprints']} 통과")
        print(f"  비용: ${summary['total_cost_usd']}")
        print(f"  소요 시간: {summary['elapsed_human']}")
        print("=" * 60)
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단됨")
        sys.exit(1)


if __name__ == "__main__":
    main()
