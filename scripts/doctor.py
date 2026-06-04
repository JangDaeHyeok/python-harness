"""GitHub/Python 환경 사전 점검 CLI.

하네스를 실행하기 전에 git 저장소·원격·gh 인증·도구 설치·정책 파일 등
준비 상태를 점검하고 누락 항목별 다음 조치를 한국어로 안내한다.

사용 예:
    harness-doctor
    harness-doctor --project-dir ./billing
    harness-doctor --api-endpoint https://example.invalid/v1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.bootstrap.doctor import run_doctor


def main(argv: list[str] | None = None) -> None:
    """harness-doctor 진입점."""
    parser = argparse.ArgumentParser(
        description="하네스 실행 전 GitHub/Python 준비 상태를 점검합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="점검할 프로젝트 루트 (기본: 현재 디렉터리)",
    )
    parser.add_argument(
        "--api-endpoint",
        default=None,
        help="API 엔드포인트 (미지정 시 HARNESS_API_ENDPOINT 환경변수 사용)",
    )
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve()
    checks = run_doctor(project_dir, api_endpoint=args.api_endpoint)

    print("=" * 60)
    print(f"프로젝트: {project_dir}")
    print("-" * 60)
    failed = 0
    for check in checks:
        mark = "OK  " if check.ok else "FAIL"
        print(f"[{mark}] {check.name}: {check.detail}")
        if not check.ok:
            failed += 1
            if check.fix:
                print(f"        → 조치: {check.fix}")
    print("-" * 60)
    total = len(checks)
    print(f"점검 {total}개 / 통과 {total - failed}개 / 실패 {failed}개")
    print("=" * 60)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
