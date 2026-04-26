"""
하네스 메인 실행 스크립트.

사용법:
    python scripts/run_harness.py "2D 레트로 게임 메이커를 만들어주세요"

    python scripts/run_harness.py \
        --project-dir ./my-project \
        --model claude-sonnet-4-20250514 \
        --max-retries 3 \
        "브라우저에서 동작하는 DAW를 만들어주세요"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.agents.orchestrator import HarnessConfig, HarnessOrchestrator


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="하네스 엔지니어링 프레임워크 실행")
    parser.add_argument("prompt", help="프로젝트 설명 (1~4문장)")
    parser.add_argument("--project-dir", default="./project", help="프로젝트 디렉터리")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="사용할 모델")
    parser.add_argument("--max-retries", type=int, default=3, help="스프린트당 최대 재시도")
    parser.add_argument("--max-sprints", type=int, default=15, help="최대 스프린트 수")
    parser.add_argument("--app-url", default="http://localhost:3000", help="앱 URL")
    parser.add_argument("--no-context-reset", action="store_true", help="컨텍스트 리셋 비활성화")
    parser.add_argument("-v", "--verbose", action="store_true", help="상세 로그")

    args = parser.parse_args()
    setup_logging(args.verbose)

    project_dir = Path(args.project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    config = HarnessConfig(
        project_dir=str(project_dir),
        model=args.model,
        max_sprint_retries=args.max_retries,
        max_total_sprints=args.max_sprints,
        app_url=args.app_url,
        enable_context_reset=not args.no_context_reset,
    )

    orchestrator = HarnessOrchestrator(config)

    try:
        summary = orchestrator.run(args.prompt)
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
