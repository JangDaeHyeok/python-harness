"""scripts/run_phases.py 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from harness.context.phase_manager import PhaseManager, PhaseStatus
from harness.review.docs_diff import DocsDiff, FileDiff
from scripts.run_phases import PhaseExecutionError, run_sprint_phases


class TestRunSprintPhases:
    @staticmethod
    def _write_handoff(tmp_path: Path, phase_id: str, lines: list[str] | None = None) -> None:
        handoff = tmp_path / ".harness" / "tasks" / "sprint-1" / f"{phase_id}-handoff.md"
        handoff.parent.mkdir(parents=True, exist_ok=True)
        handoff.write_text(
            "\n".join(lines or ["수정 파일: 없음", "결정적 파이프라인 결과: skipped(테스트)"]),
            encoding="utf-8",
        )

    def test_no_task_index(self, tmp_path: Path) -> None:
        with pytest.raises(PhaseExecutionError, match=r"task-index\.json"):
            run_sprint_phases(tmp_path, sprint_number=1)

    def test_dry_run_all_phases(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        index = mgr.create_phases(1, "드라이런 테스트")
        mgr.save_task_index(index)

        for phase in index.phases:
            mgr.save_phase_prompt(1, phase, f"# {phase.name}\n테스트 프롬프트")

        results = run_sprint_phases(tmp_path, sprint_number=1, dry_run=True)
        assert all(s == PhaseStatus.DONE.value for s in results.values())
        assert len(results) == 5

    def test_skip_completed_phases(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        index = mgr.create_phases(1, "스킵 테스트")
        index.phases[0].status = PhaseStatus.DONE.value
        mgr.save_task_index(index)

        for phase in index.phases[1:]:
            mgr.save_phase_prompt(1, phase, f"# {phase.name}\n테스트")

        results = run_sprint_phases(tmp_path, sprint_number=1, dry_run=True)
        assert results["phase-01-docs-update"] == PhaseStatus.DONE.value

    def test_skip_no_prompt_phases(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        custom = [("only", "유일한 Phase", "테스트")]
        index = mgr.create_phases(1, "프롬프트 없음", phase_specs=custom)
        mgr.save_task_index(index)

        results = run_sprint_phases(tmp_path, sprint_number=1, dry_run=True)
        assert results["phase-01-only"] == PhaseStatus.SKIPPED.value

    def test_dependency_skip(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        custom = [("a", "A", ""), ("b", "B", "")]
        index = mgr.create_phases(1, "의존성", phase_specs=custom)
        mgr.save_task_index(index)
        # Phase A에 프롬프트 없으므로 SKIPPED → Phase B도 SKIPPED
        mgr.save_phase_prompt(1, index.phases[1], "# B\n프롬프트")

        results = run_sprint_phases(tmp_path, sprint_number=1, dry_run=True)
        assert results["phase-01-a"] == PhaseStatus.SKIPPED.value
        assert results["phase-02-b"] == PhaseStatus.SKIPPED.value

    def test_docs_update_writes_docs_diff(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        custom = [("docs-update", "문서 업데이트", "문서")]
        index = mgr.create_phases(1, "docs", phase_specs=custom)
        mgr.save_task_index(index)
        mgr.save_phase_prompt(1, index.phases[0], "# docs\n")

        docs_diff = DocsDiff(
            base_ref="HEAD",
            file_diffs=[FileDiff(path="docs/spec.md", added_lines=[(1, "new")])],
        )

        with (
            pytest.MonkeyPatch.context() as mp,
        ):
            def fake_execute(*args: object, **kwargs: object) -> str:
                self._write_handoff(tmp_path, "phase-01-docs-update")
                return "ok"

            mp.setattr("scripts.run_phases.execute_phase_headless", fake_execute)
            mock_gen = type("MockDocsDiffGenerator", (), {"generate": lambda self: docs_diff})
            mp.setattr("scripts.run_phases.DocsDiffGenerator", lambda project_dir: mock_gen())
            results = run_sprint_phases(tmp_path, sprint_number=1)

        assert results["phase-01-docs-update"] == PhaseStatus.DONE.value
        docs_diff_path = tmp_path / ".harness" / "tasks" / "sprint-1" / "docs-diff.md"
        assert "docs/spec.md" in docs_diff_path.read_text(encoding="utf-8")

    def test_missing_handoff_fails_phase(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        custom = [("core", "구현", "구현")]
        index = mgr.create_phases(1, "core", phase_specs=custom)
        mgr.save_task_index(index)
        mgr.save_phase_prompt(1, index.phases[0], "# core\n")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("scripts.run_phases.execute_phase_headless", lambda *args, **kwargs: "ok")
            results = run_sprint_phases(tmp_path, sprint_number=1)

        assert results["phase-01-core"] == PhaseStatus.FAILED.value

    def test_handoff_over_twenty_lines_fails_phase(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        custom = [("core", "구현", "구현")]
        index = mgr.create_phases(1, "core", phase_specs=custom)
        mgr.save_task_index(index)
        mgr.save_phase_prompt(1, index.phases[0], "# core\n")

        with pytest.MonkeyPatch.context() as mp:
            def fake_execute(*args: object, **kwargs: object) -> str:
                lines = [f"line {i}" for i in range(21)]
                lines[0] = "결정적 파이프라인 결과: skipped(테스트)"
                self._write_handoff(tmp_path, "phase-01-core", lines)
                return "ok"

            mp.setattr("scripts.run_phases.execute_phase_headless", fake_execute)
            results = run_sprint_phases(tmp_path, sprint_number=1)

        assert results["phase-01-core"] == PhaseStatus.FAILED.value

    def test_handoff_requires_deterministic_pipeline_line(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        custom = [("core", "구현", "구현")]
        index = mgr.create_phases(1, "core", phase_specs=custom)
        mgr.save_task_index(index)
        mgr.save_phase_prompt(1, index.phases[0], "# core\n")

        with pytest.MonkeyPatch.context() as mp:
            def fake_execute(*args: object, **kwargs: object) -> str:
                self._write_handoff(tmp_path, "phase-01-core", ["수정 파일: 없음"])
                return "ok"

            mp.setattr("scripts.run_phases.execute_phase_headless", fake_execute)
            results = run_sprint_phases(tmp_path, sprint_number=1)

        assert results["phase-01-core"] == PhaseStatus.FAILED.value

    def test_outside_allowed_file_change_fails_and_stops_next_phase(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        custom = [("core", "구현", "구현"), ("tests", "테스트", "테스트")]
        index = mgr.create_phases(1, "core", phase_specs=custom)
        index.phases[0].allowed_files = ["harness/**"]
        mgr.save_task_index(index)
        for phase in index.phases:
            mgr.save_phase_prompt(1, phase, f"# {phase.phase_id}\n")

        snapshots = iter([{}, {"outside.txt": "changed"}])

        with pytest.MonkeyPatch.context() as mp:
            def fake_execute(*args: object, **kwargs: object) -> str:
                self._write_handoff(tmp_path, "phase-01-core")
                return "ok"

            mp.setattr("scripts.run_phases.execute_phase_headless", fake_execute)
            mp.setattr(
                "scripts.run_phases._snapshot_worktree_changes",
                lambda project_dir: next(snapshots),
            )
            results = run_sprint_phases(tmp_path, sprint_number=1)

        assert results["phase-01-core"] == PhaseStatus.FAILED.value
        assert results["phase-02-tests"] == PhaseStatus.SKIPPED.value

    def test_require_docs_diff_fails_when_empty(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        custom = [("docs-update", "문서 업데이트", "문서")]
        index = mgr.create_phases(1, "docs", phase_specs=custom)
        mgr.save_task_index(index)
        mgr.save_phase_prompt(1, index.phases[0], "# docs\n")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("scripts.run_phases.execute_phase_headless", lambda *args, **kwargs: "ok")
            mock_gen = type(
                "MockDocsDiffGenerator",
                (),
                {"generate": lambda self: DocsDiff(base_ref="HEAD")},
            )
            mp.setattr("scripts.run_phases.DocsDiffGenerator", lambda project_dir: mock_gen())
            results = run_sprint_phases(tmp_path, sprint_number=1, require_docs_diff=True)

        assert results["phase-01-docs-update"] == PhaseStatus.FAILED.value
