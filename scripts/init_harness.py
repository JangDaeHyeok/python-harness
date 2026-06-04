"""프로젝트 초기 환경 부트스트랩 CLI.

자연어 요청과 프로젝트 경로를 받아 ``docs/adr/``, ``docs/code-convention.yaml``,
``harness_structure.yaml``, ``.harness/project-policy.yaml``, ``CLAUDE.md`` 를
한 번에 생성하거나 누락된 항목을 보강한다.

사용 예:
    harness-init "사내 청구 자동화 도구를 만들고 있다" --project-dir ./billing
    harness-init --offline --only adr,policy "데이터 파이프라인 PoC"
    harness-init --with-coderabbit --offline "GitHub PR 리뷰 자동화"
    harness-init --migrate --offline "기존 Python 서비스에 하네스 적용"
    harness-init --force --dry-run "스토어 백엔드 개편"
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.bootstrap.initializer import (
    ALL_TARGETS,
    SCAFFOLD_TARGETS,
    SUPPORTED_TARGETS,
    BootstrapInitializer,
    TargetKind,
)
from harness.tools.api_client import ENDPOINT_ENV_VAR, HarnessClient

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_targets(raw: str | None) -> list[TargetKind]:
    if not raw:
        return list(ALL_TARGETS)
    valid = {t.value: t for t in SUPPORTED_TARGETS}
    selected: list[TargetKind] = []
    for token in raw.split(","):
        key = token.strip().lower()
        if not key:
            continue
        if key not in valid:
            choices = ", ".join(t.value for t in SUPPORTED_TARGETS)
            raise SystemExit(f"알 수 없는 --only 항목: {key!r} (가능: {choices})")
        if valid[key] not in selected:
            selected.append(valid[key])
    return selected or list(ALL_TARGETS)


def _resolve_client(offline: bool, api_endpoint: str | None) -> HarnessClient | None:
    if offline:
        return None
    endpoint = api_endpoint or os.environ.get(ENDPOINT_ENV_VAR, "")
    if not endpoint.strip():
        logger.info("API 엔드포인트가 설정되지 않아 템플릿 모드로 실행합니다.")
        return None
    try:
        return HarnessClient(endpoint=endpoint)
    except ValueError as e:
        logger.warning("API 엔드포인트 검증 실패(%s) — 템플릿 모드로 실행합니다.", e)
        return None


def main(argv: list[str] | None = None) -> None:
    """harness-init 진입점."""
    parser = argparse.ArgumentParser(
        description="프로젝트 초기 환경(ADR, 컨벤션, 구조 규칙, 정책 파일)을 부트스트랩합니다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default="",
        help="프로젝트 의도를 설명하는 자연어 (1~4문장)",
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="대상 프로젝트 루트 (기본: 현재 디렉터리)",
    )
    parser.add_argument(
        "--only",
        default=None,
        help=(
            "초기화할 대상만 지정 (콤마 구분). 가능한 값: "
            + ", ".join(t.value for t in SUPPORTED_TARGETS)
        ),
    )
    parser.add_argument(
        "--with-coderabbit",
        action="store_true",
        help=(
            ".coderabbit.yaml 템플릿도 함께 생성한다 (GitHub App 설치는 별도). "
            "--only와 함께 쓰면 해당 목록에 coderabbit를 추가한다."
        ),
    )
    parser.add_argument(
        "--scaffold",
        action="store_true",
        help=(
            "새 Python 프로젝트 골격(pyproject.toml, 패키지 __init__.py, "
            "tests/test_smoke.py, .gitignore, .github/workflows/ci.yml)도 함께 생성한다."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="이미 존재하는 파일도 덮어쓴다",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="LLM 호출 없이 내장 템플릿만 사용한다",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제로 파일을 쓰지 않고 결과만 출력한다",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="기존 Python 프로젝트를 하네스 강제 구조에 맞게 보강한다",
    )
    parser.add_argument("--model", default="claude-sonnet-4-6", help="LLM 모델명")
    parser.add_argument(
        "--api-endpoint",
        default=None,
        help=f"API 엔드포인트 (미지정 시 {ENDPOINT_ENV_VAR} 환경변수 사용)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="상세 로그")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    project_dir = Path(args.project_dir).resolve()
    # dry-run에서는 대상 디렉터리 생성도 부작용으로 보고 건너뛴다.
    # 실제 쓰기 모드일 때만 누락된 부모 경로를 생성한다.
    if not args.dry_run:
        project_dir.mkdir(parents=True, exist_ok=True)

    targets = _parse_targets(args.only)
    if args.with_coderabbit and TargetKind.CODERABBIT not in targets:
        targets.append(TargetKind.CODERABBIT)
    if args.scaffold:
        for kind in SCAFFOLD_TARGETS:
            if kind not in targets:
                targets.append(kind)
    client = _resolve_client(args.offline, args.api_endpoint)

    initializer = BootstrapInitializer(
        project_dir=project_dir,
        prompt=args.prompt,
        client=client,
        model=args.model,
        force=args.force,
        offline=args.offline,
        dry_run=args.dry_run,
        targets=targets,
    )
    try:
        result = initializer.migrate_existing() if args.migrate else initializer.run()
    except ValueError as e:
        raise SystemExit(str(e)) from e

    print("=" * 60)
    print(f"프로젝트: {result.project_dir}")
    mode = "migrate" if args.migrate else "init"
    print(
        f"모드: {mode} / {'dry-run' if result.dry_run else '쓰기'} / "
        f"{'offline' if (args.offline or client is None) else 'llm'}"
    )
    print("-" * 60)
    for line in result.messages:
        print(line)
    for line in result.summary_lines():
        print(line)
    if not result.created_count and not result.updated_count:
        print("변경 사항 없음")
    print("-" * 60)
    print(
        f"생성 {result.created_count}개 / 업데이트 {result.updated_count}개 / "
        f"스킵 {result.skipped_count}개"
    )
    if args.migrate:
        print("[MIGRATE] 완료. 다음 단계:")
        print("  1) docs/adr/0001-* 를 검토하세요.")
        print("  2) harness 명령으로 첫 실행을 시도하세요.")
    if TargetKind.CODERABBIT in targets:
        print("[CodeRabbit] GitHub 저장소에 CodeRabbit App을 별도로 설치해야 리뷰가 실행됩니다.")
    print("=" * 60)


if __name__ == "__main__":
    main()
