"""harness/context/phase_manager.py 테스트."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from harness.context.phase_manager import (
    PhaseDefinition,
    PhaseManager,
    PhaseStatus,
    TaskIndex,
)


class TestPhaseDefinition:
    def test_to_dict_roundtrip(self) -> None:
        phase = PhaseDefinition(
            phase_id="phase-01-docs",
            name="문서 업데이트",
            description="스펙 문서를 업데이트한다.",
            order=1,
            sprint_number=1,
            depends_on=["prev"],
        )
        d = phase.to_dict()
        restored = PhaseDefinition.from_dict(d)
        assert restored.phase_id == "phase-01-docs"
        assert restored.name == "문서 업데이트"
        assert restored.depends_on == ["prev"]
        assert restored.status == PhaseStatus.PENDING.value
        assert restored.inputs == []
        assert restored.allowed_files == []
        assert restored.expected_outputs == []

    def test_from_dict_defaults(self) -> None:
        phase = PhaseDefinition.from_dict({"phase_id": "p1", "order": 1, "sprint_number": 1})
        assert phase.name == ""
        assert phase.status == PhaseStatus.PENDING.value
        assert phase.depends_on == []
        assert phase.inputs == []
        assert phase.allowed_files == []
        assert phase.expected_outputs == []
        assert phase.output_files == []


class TestTaskIndex:
    def test_json_roundtrip(self) -> None:
        index = TaskIndex(
            sprint_number=1,
            task_name="테스트 작업",
            phases=[
                PhaseDefinition(
                    phase_id="phase-01-docs",
                    name="문서",
                    description="문서 업데이트",
                    order=1,
                    sprint_number=1,
                ),
                PhaseDefinition(
                    phase_id="phase-02-impl",
                    name="구현",
                    description="핵심 구현",
                    order=2,
                    sprint_number=1,
                    depends_on=["phase-01-docs"],
                ),
            ],
        )
        text = index.to_json()
        restored = TaskIndex.from_json(text)
        assert restored.sprint_number == 1
        assert restored.task_name == "테스트 작업"
        assert len(restored.phases) == 2
        assert restored.phases[1].depends_on == ["phase-01-docs"]

    def test_from_json_invalid_type(self) -> None:
        try:
            TaskIndex.from_json(json.dumps([1, 2, 3]))
            raise AssertionError("TypeError expected")
        except TypeError:
            pass


class TestPhaseManager:
    def test_create_phases_default(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        index = mgr.create_phases(1, "테스트")
        assert len(index.phases) == 5
        assert index.phases[0].phase_id == "phase-01-docs-update"
        assert index.phases[1].depends_on == ["phase-01-docs-update"]
        assert index.phases[0].depends_on == []
        assert index.phases[0].docs_diff_ref == ".harness/tasks/sprint-1/docs-diff.md"
        assert "docs/**" in index.phases[0].allowed_files
        assert ".harness/tasks/sprint-1/docs-diff.md" in index.phases[1].inputs

    def test_create_phases_custom(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        custom = [("a", "Phase A", "Desc A"), ("b", "Phase B", "Desc B")]
        index = mgr.create_phases(2, "커스텀", phase_specs=custom)
        assert len(index.phases) == 2
        assert index.phases[0].phase_id == "phase-01-a"
        assert index.phases[1].phase_id == "phase-02-b"

    def test_save_and_load_task_index(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        index = mgr.create_phases(1, "저장 테스트")
        mgr.save_task_index(index)

        loaded = mgr.load_task_index(1)
        assert loaded is not None
        assert loaded.task_name == "저장 테스트"
        assert len(loaded.phases) == 5

    def test_load_nonexistent_index(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        assert mgr.load_task_index(99) is None

    def test_save_and_load_phase_prompt(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        index = mgr.create_phases(1, "프롬프트 테스트")
        phase = index.phases[0]
        mgr.save_phase_prompt(1, phase, "# Phase 프롬프트\n테스트 내용")

        loaded = mgr.load_phase_prompt(1, phase)
        assert "Phase 프롬프트" in loaded

    def test_update_phase_status(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        index = mgr.create_phases(1, "상태 테스트")
        mgr.save_task_index(index)

        mgr.update_phase_status(1, "phase-01-docs-update", PhaseStatus.DONE)

        loaded = mgr.load_task_index(1)
        assert loaded is not None
        assert loaded.phases[0].status == PhaseStatus.DONE.value

    def test_get_pending_phases(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        index = mgr.create_phases(1, "펜딩 테스트")
        index.phases[0].status = PhaseStatus.DONE.value
        mgr.save_task_index(index)

        pending = mgr.get_pending_phases(1)
        assert len(pending) == 4
        assert all(p.status in (PhaseStatus.PENDING.value, PhaseStatus.FAILED.value) for p in pending)

    def test_reset_incomplete_phases_keeps_done(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        index = mgr.create_phases(1, "재시도 테스트")
        index.phases[0].status = PhaseStatus.DONE.value
        index.phases[1].status = PhaseStatus.RUNNING.value
        index.phases[2].status = PhaseStatus.FAILED.value
        index.phases[3].status = PhaseStatus.SKIPPED.value
        mgr.save_task_index(index)

        mgr.reset_incomplete_phases(1)

        loaded = mgr.load_task_index(1)
        assert loaded is not None
        assert loaded.phases[0].status == PhaseStatus.DONE.value
        assert loaded.phases[1].status == PhaseStatus.PENDING.value
        assert loaded.phases[2].status == PhaseStatus.PENDING.value
        assert loaded.phases[3].status == PhaseStatus.PENDING.value

    def test_build_phase_prompt(self, tmp_path: Path) -> None:
        mgr = PhaseManager(tmp_path)
        phase = PhaseDefinition(
            phase_id="phase-01-test",
            name="테스트 Phase",
            description="테스트 설명",
            order=1,
            sprint_number=1,
            depends_on=["prev-phase"],
            verification="pytest 실행",
        )
        prompt = mgr.build_phase_prompt(
            phase=phase,
            sprint_contract="계약 내용",
            docs_diff_md="# Diff\n변경 있음",
            extra_context="추가 컨텍스트",
        )
        assert "테스트 Phase" in prompt
        assert "계약 내용" in prompt
        assert "Diff" in prompt
        assert "prev-phase" in prompt
        assert "pytest 실행" in prompt
        assert "추가 컨텍스트" in prompt
        assert "핸드오프 요구사항" in prompt
