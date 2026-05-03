"""헤드리스 Phase 실행기.

claude --print 모드로 Phase별 독립 세션을 순차 실행한다.
메인 세션의 컨텍스트를 보존하면서 구현 컨텍스트를 하위 세션에 격리한다.

사용법:
    python scripts/run_phases.py --sprint 1 --project-dir ./my-project
    python scripts/run_phases.py --sprint 1 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.context.phase_manager import PhaseManager, PhaseStatus
from harness.review.docs_diff import DocsDiffGenerator

logger = logging.getLogger(__name__)

_PHASE_TIMEOUT = 600
_CLAUDE_CMD = "claude"


class PhaseExecutionError(RuntimeError):
    """Phase 실행 실패."""


def _find_claude_cmd() -> str:
    """claude CLI가 설치되어 있는지 확인한다."""
    try:
        result = subprocess.run(
            ["which", _CLAUDE_CMD],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return _CLAUDE_CMD
    except (subprocess.SubprocessError, OSError):
        pass
    return _CLAUDE_CMD


def execute_phase_headless(
    prompt: str,
    project_dir: Path,
    timeout: int = _PHASE_TIMEOUT,
) -> str:
    """claude --print 모드로 단일 Phase를 실행한다.

    Returns:
        claude 출력 텍스트.

    Raises:
        PhaseExecutionError: 실행 실패 시.
    """
    cmd = _find_claude_cmd()
    try:
        result = subprocess.run(
            [cmd, "--print", "-p", prompt],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() or f"exit code {result.returncode}"
            raise PhaseExecutionError(f"claude --print 실패: {error_msg}")
        return result.stdout
    except subprocess.TimeoutExpired as e:
        raise PhaseExecutionError(f"Phase 실행 타임아웃 ({timeout}초)") from e
    except FileNotFoundError as e:
        raise PhaseExecutionError(
            "claude CLI를 찾을 수 없습니다. Claude Code가 설치되어 있는지 확인하세요."
        ) from e


def run_sprint_phases(
    project_dir: Path,
    sprint_number: int,
    *,
    dry_run: bool = False,
    timeout: int = _PHASE_TIMEOUT,
    require_docs_diff: bool = False,
) -> dict[str, str]:
    """스프린트의 모든 Phase를 순차 실행한다.

    Returns:
        {phase_id: status} 결과 매핑.
    """
    mgr = PhaseManager(project_dir)
    docs_diff_gen = DocsDiffGenerator(project_dir)
    index = mgr.load_task_index(sprint_number)
    if index is None:
        raise PhaseExecutionError(f"Sprint {sprint_number}의 task-index.json이 없습니다.")

    results: dict[str, str] = {}
    phases = sorted(index.phases, key=lambda p: p.order)

    for phase in phases:
        if phase.status == PhaseStatus.DONE.value:
            logger.info("[Phase %s] 이미 완료 — 건너뛰기", phase.phase_id)
            results[phase.phase_id] = PhaseStatus.DONE.value
            continue

        if phase.status == PhaseStatus.SKIPPED.value:
            results[phase.phase_id] = PhaseStatus.SKIPPED.value
            continue

        for dep_id in phase.depends_on:
            dep_status = results.get(dep_id, "")
            if dep_status != PhaseStatus.DONE.value:
                logger.warning(
                    "[Phase %s] 의존성 %s가 완료되지 않음 — 건너뛰기", phase.phase_id, dep_id,
                )
                results[phase.phase_id] = PhaseStatus.SKIPPED.value
                mgr.update_phase_status(sprint_number, phase.phase_id, PhaseStatus.SKIPPED)
                break
        else:
            prompt = mgr.load_phase_prompt(sprint_number, phase)
            if not prompt:
                logger.warning("[Phase %s] 프롬프트 파일 없음 — 건너뛰기", phase.phase_id)
                results[phase.phase_id] = PhaseStatus.SKIPPED.value
                mgr.update_phase_status(sprint_number, phase.phase_id, PhaseStatus.SKIPPED)
                continue

            logger.info("[Phase %s] 실행 시작: %s", phase.phase_id, phase.name)
            mgr.update_phase_status(sprint_number, phase.phase_id, PhaseStatus.RUNNING)

            if dry_run:
                logger.info("[Phase %s] DRY RUN — 실행 건너뛰기", phase.phase_id)
                results[phase.phase_id] = PhaseStatus.DONE.value
                mgr.update_phase_status(sprint_number, phase.phase_id, PhaseStatus.DONE)
                continue

            start = time.time()
            try:
                output = execute_phase_headless(prompt, project_dir, timeout=timeout)
                elapsed = time.time() - start
                logger.info(
                    "[Phase %s] 완료 (%.1f초, 출력 %d자)",
                    phase.phase_id, elapsed, len(output),
                )

                output_path = mgr.tasks_dir / f"sprint-{sprint_number}" / f"{phase.phase_id}-output.md"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(output, encoding="utf-8")

                if _is_docs_update_phase(phase.phase_id):
                    docs_diff = docs_diff_gen.generate()
                    docs_diff_path = mgr.tasks_dir / f"sprint-{sprint_number}" / "docs-diff.md"
                    docs_diff_path.write_text(docs_diff.to_markdown(), encoding="utf-8")
                    logger.info(
                        "[Phase %s] docs-diff 갱신 (%d개 파일): %s",
                        phase.phase_id,
                        len(docs_diff.changed_files),
                        docs_diff_path,
                    )
                    if require_docs_diff and not docs_diff.has_changes:
                        raise PhaseExecutionError(
                            "docs-update Phase 이후 docs-diff가 비어 있습니다. "
                            "문서 업데이트가 필요한 작업이면 docs/ 문서를 먼저 수정하세요."
                        )

                results[phase.phase_id] = PhaseStatus.DONE.value
                mgr.update_phase_status(sprint_number, phase.phase_id, PhaseStatus.DONE)

            except PhaseExecutionError as e:
                elapsed = time.time() - start
                logger.error(
                    "[Phase %s] 실패 (%.1f초): %s", phase.phase_id, elapsed, e,
                )
                results[phase.phase_id] = PhaseStatus.FAILED.value
                mgr.update_phase_status(sprint_number, phase.phase_id, PhaseStatus.FAILED)

    return results


def _is_docs_update_phase(phase_id: str) -> bool:
    return phase_id.startswith("phase-01-") and "docs-update" in phase_id


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase별 헤드리스 Claude Code 실행기")
    parser.add_argument("--sprint", type=int, required=True, help="실행할 스프린트 번호")
    parser.add_argument(
        "--project-dir", default=".", help="프로젝트 디렉터리 (기본값: 현재 디렉터리)",
    )
    parser.add_argument("--timeout", type=int, default=_PHASE_TIMEOUT, help="Phase당 타임아웃(초)")
    parser.add_argument("--dry-run", action="store_true", help="실제 실행 없이 순서만 확인")
    parser.add_argument(
        "--require-docs-diff",
        action="store_true",
        help="docs-update Phase 이후 docs-diff가 비어 있으면 실패",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="상세 로그")

    args = parser.parse_args()
    setup_logging(args.verbose)

    project_dir = Path(args.project_dir).resolve()

    try:
        results = run_sprint_phases(
            project_dir,
            args.sprint,
            dry_run=args.dry_run,
            timeout=args.timeout,
            require_docs_diff=args.require_docs_diff,
        )
        print(json.dumps(results, indent=2, ensure_ascii=False))
        failed = [pid for pid, s in results.items() if s == PhaseStatus.FAILED.value]
        if failed:
            print(f"\n실패한 Phase: {', '.join(failed)}")
            sys.exit(1)
    except PhaseExecutionError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
