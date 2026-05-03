"""Task/Phase 분할 관리.

스프린트를 세분화된 Phase 단위로 분할하고 상태를 추적한다.
각 Phase 파일은 자기 완결적(self-contained)이어서 독립 세션에서 실행 가능하다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

from harness.tools.file_io import atomic_write_text

logger = logging.getLogger(__name__)


class PhaseStatus(StrEnum):
    """Phase 실행 상태."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PhaseDefinition:
    """개별 Phase 정의."""

    phase_id: str
    name: str
    description: str
    order: int
    sprint_number: int
    status: str = PhaseStatus.PENDING.value
    prompt_file: str = ""
    depends_on: list[str] = field(default_factory=list)
    docs_diff_ref: str = ""
    inputs: list[str] = field(default_factory=list)
    allowed_files: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)
    verification: str = ""
    handoff_summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> PhaseDefinition:
        raw_depends = data.get("depends_on", [])
        raw_inputs = data.get("inputs", [])
        raw_allowed = data.get("allowed_files", [])
        raw_expected = data.get("expected_outputs", [])
        raw_outputs = data.get("output_files", [])
        return cls(
            phase_id=str(data.get("phase_id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            order=int(str(data.get("order", 0))),
            sprint_number=int(str(data.get("sprint_number", 0))),
            status=str(data.get("status", PhaseStatus.PENDING.value)),
            prompt_file=str(data.get("prompt_file", "")),
            depends_on=list(raw_depends) if isinstance(raw_depends, list) else [],
            docs_diff_ref=str(data.get("docs_diff_ref", "")),
            inputs=list(raw_inputs) if isinstance(raw_inputs, list) else [],
            allowed_files=list(raw_allowed) if isinstance(raw_allowed, list) else [],
            expected_outputs=list(raw_expected) if isinstance(raw_expected, list) else [],
            output_files=list(raw_outputs) if isinstance(raw_outputs, list) else [],
            verification=str(data.get("verification", "")),
            handoff_summary=str(data.get("handoff_summary", "")),
        )


@dataclass
class TaskIndex:
    """스프린트 내 Phase 목록 인덱스."""

    sprint_number: int
    task_name: str
    phases: list[PhaseDefinition] = field(default_factory=list)
    created_at: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "sprint_number": self.sprint_number,
                "task_name": self.task_name,
                "phases": [p.to_dict() for p in self.phases],
                "created_at": self.created_at,
            },
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> TaskIndex:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise TypeError(f"TaskIndex JSON 최상위 값이 dict가 아닙니다: {type(data).__name__}")
        raw_phases = data.get("phases", [])
        phases = [
            PhaseDefinition.from_dict(p)
            for p in (raw_phases if isinstance(raw_phases, list) else [])
            if isinstance(p, dict)
        ]
        return cls(
            sprint_number=int(str(data.get("sprint_number", 0))),
            task_name=str(data.get("task_name", "")),
            phases=phases,
            created_at=str(data.get("created_at", "")),
        )


_DEFAULT_PHASES = [
    ("docs-update", "문서 업데이트", "관련 스펙 문서를 먼저 업데이트하고 docs-diff를 생성한다."),
    ("core-impl", "핵심 구현", "핵심 로직과 데이터 모델을 구현한다."),
    ("integration", "통합", "기존 시스템과 연결하고 인터페이스를 조정한다."),
    ("tests", "테스트 작성", "단위 테스트와 통합 테스트를 작성한다."),
    ("validation", "품질 검증", "ruff, mypy, pytest, 구조 검사를 통과시킨다."),
]


class PhaseManager:
    """스프린트를 Phase 단위로 분할·관리한다."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self._tasks_dir = self.project_dir / ".harness" / "tasks"

    @property
    def tasks_dir(self) -> Path:
        return self._tasks_dir

    def create_phases(
        self,
        sprint_number: int,
        task_name: str,
        phase_specs: list[tuple[str, str, str]] | None = None,
    ) -> TaskIndex:
        """스프린트에 대한 Phase 목록을 생성한다.

        Args:
            sprint_number: 스프린트 번호.
            task_name: 작업 이름.
            phase_specs: (id_suffix, name, description) 튜플 목록. None이면 기본 Phase 사용.
        """
        specs = phase_specs or _DEFAULT_PHASES
        phases: list[PhaseDefinition] = []

        prev_id = ""
        for i, (id_suffix, name, description) in enumerate(specs, start=1):
            phase_id = f"phase-{i:02d}-{id_suffix}"
            prompt_file = f"{phase_id}.md"
            depends = [prev_id] if prev_id else []

            phase = PhaseDefinition(
                phase_id=phase_id,
                name=name,
                description=description,
                order=i,
                sprint_number=sprint_number,
                prompt_file=prompt_file,
                depends_on=depends,
                docs_diff_ref=f".harness/tasks/sprint-{sprint_number}/docs-diff.md",
                inputs=self._default_inputs_for_phase(i, sprint_number),
                allowed_files=self._default_allowed_files_for_phase(id_suffix),
                expected_outputs=self._default_expected_outputs_for_phase(id_suffix, sprint_number),
                verification=self._default_verification_for_phase(id_suffix),
            )
            phases.append(phase)
            prev_id = phase_id

        index = TaskIndex(
            sprint_number=sprint_number,
            task_name=task_name,
            phases=phases,
        )
        return index

    def save_task_index(self, index: TaskIndex) -> Path:
        """task-index.json을 저장한다."""
        sprint_dir = self._sprint_dir(index.sprint_number)
        sprint_dir.mkdir(parents=True, exist_ok=True)
        path = sprint_dir / "task-index.json"
        atomic_write_text(path, index.to_json(), prefix=".task-")
        logger.info("Task index 저장: %s", path)
        return path

    def load_task_index(self, sprint_number: int) -> TaskIndex | None:
        """task-index.json을 로드한다."""
        path = self._sprint_dir(sprint_number) / "task-index.json"
        if not path.exists():
            return None
        try:
            return TaskIndex.from_json(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError, KeyError, ValueError) as e:
            logger.warning("Task index 파싱 실패 (sprint %d): %s", sprint_number, e)
            return None

    def save_phase_prompt(
        self,
        sprint_number: int,
        phase: PhaseDefinition,
        prompt_content: str,
    ) -> Path:
        """Phase 프롬프트 파일을 저장한다."""
        sprint_dir = self._sprint_dir(sprint_number)
        sprint_dir.mkdir(parents=True, exist_ok=True)
        path = sprint_dir / phase.prompt_file
        atomic_write_text(path, prompt_content, prefix=".phase-")
        logger.info("Phase prompt 저장: %s", path)
        return path

    def load_phase_prompt(self, sprint_number: int, phase: PhaseDefinition) -> str:
        """Phase 프롬프트 파일을 로드한다."""
        path = self._sprint_dir(sprint_number) / phase.prompt_file
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def update_phase_status(
        self,
        sprint_number: int,
        phase_id: str,
        status: PhaseStatus,
    ) -> None:
        """특정 Phase의 상태를 업데이트한다."""
        index = self.load_task_index(sprint_number)
        if index is None:
            logger.warning("Task index 없음 (sprint %d), 상태 업데이트 건너뜀", sprint_number)
            return

        for phase in index.phases:
            if phase.phase_id == phase_id:
                phase.status = status.value
                break
        else:
            logger.warning("Phase 없음: %s (sprint %d)", phase_id, sprint_number)
            return

        self.save_task_index(index)

    def reset_incomplete_phases(self, sprint_number: int) -> None:
        """재시도를 위해 완료되지 않은 Phase 상태를 pending으로 되돌린다."""
        index = self.load_task_index(sprint_number)
        if index is None:
            logger.warning("Task index 없음 (sprint %d), Phase reset 건너뜀", sprint_number)
            return

        changed = False
        for phase in index.phases:
            if phase.status in (
                PhaseStatus.RUNNING.value,
                PhaseStatus.FAILED.value,
                PhaseStatus.SKIPPED.value,
            ):
                phase.status = PhaseStatus.PENDING.value
                changed = True

        if changed:
            self.save_task_index(index)

    def get_pending_phases(self, sprint_number: int) -> list[PhaseDefinition]:
        """아직 실행되지 않은 Phase 목록을 순서대로 반환한다."""
        index = self.load_task_index(sprint_number)
        if index is None:
            return []
        return [
            p for p in sorted(index.phases, key=lambda x: x.order)
            if p.status in (PhaseStatus.PENDING.value, PhaseStatus.FAILED.value)
        ]

    def build_phase_prompt(
        self,
        phase: PhaseDefinition,
        sprint_contract: str,
        docs_diff_md: str = "",
        extra_context: str = "",
    ) -> str:
        """Phase 프롬프트를 자기 완결적 마크다운으로 조립한다."""
        lines: list[str] = [
            f"# {phase.name}\n",
            f"**Phase**: {phase.phase_id}",
            f"**Sprint**: {phase.sprint_number}",
            f"**설명**: {phase.description}\n",
            "## 스프린트 계약\n",
            sprint_contract,
            "",
        ]

        if docs_diff_md:
            lines.append("## Docs Diff (이번 작업의 스펙 변경)\n")
            lines.append(docs_diff_md)
            lines.append("")

        if phase.depends_on:
            lines.append("## 이전 Phase 결과물\n")
            for dep in phase.depends_on:
                lines.append(f"- `.harness/tasks/sprint-{phase.sprint_number}/{dep}-handoff.md`")
                lines.append(f"- `.harness/tasks/sprint-{phase.sprint_number}/{dep}-output.md`")
            lines.append("")

        if phase.inputs:
            lines.append("## 입력 파일\n")
            for item in phase.inputs:
                lines.append(f"- `{item}`")
            lines.append("")

        if phase.docs_diff_ref:
            lines.append("## Docs Diff 참조\n")
            lines.append(f"- `{phase.docs_diff_ref}`")
            lines.append("- Phase 1 이후 생성되는 최신 docs-diff 파일을 읽고 스펙 변경점을 구현하세요.")
            lines.append("")

        if phase.allowed_files:
            lines.append("## 변경 허용 범위\n")
            for item in phase.allowed_files:
                lines.append(f"- `{item}`")
            lines.append("")

        if phase.expected_outputs:
            lines.append("## 기대 산출물\n")
            for item in phase.expected_outputs:
                lines.append(f"- {item}")
            lines.append("")

        lines.append("## 핸드오프 요구사항\n")
        lines.append(
            f"- 작업 완료 후 `.harness/tasks/sprint-{phase.sprint_number}/{phase.phase_id}-handoff.md`에 "
            "수정 파일, 남은 이슈, 다음 Phase가 알아야 할 내용을 20줄 이내로 기록하세요."
        )
        if phase.handoff_summary:
            lines.append(f"- 추가 지침: {phase.handoff_summary}")
        lines.append("")

        if extra_context:
            lines.append("## 추가 컨텍스트\n")
            lines.append(extra_context)
            lines.append("")

        if phase.verification:
            lines.append("## 검증 방법\n")
            lines.append(phase.verification)
            lines.append("")

        return "\n".join(lines)

    def _sprint_dir(self, sprint_number: int) -> Path:
        return self._tasks_dir / f"sprint-{sprint_number}"

    @staticmethod
    def _default_inputs_for_phase(order: int, sprint_number: int) -> list[str]:
        inputs = [
            f".harness/contracts/sprint_{sprint_number}.json",
            f".harness/tasks/sprint-{sprint_number}/task-index.json",
        ]
        if order > 1:
            inputs.append(f".harness/tasks/sprint-{sprint_number}/docs-diff.md")
        return inputs

    @staticmethod
    def _default_allowed_files_for_phase(id_suffix: str) -> list[str]:
        if id_suffix == "docs-update":
            return ["docs/**", ".harness/review-artifacts/**", ".harness/tasks/**"]
        if id_suffix == "tests":
            return ["tests/**", "harness/**", "scripts/**", "docs/**"]
        if id_suffix == "validation":
            return ["harness/**", "scripts/**", "tests/**", "docs/**", ".harness/tasks/**"]
        return ["harness/**", "scripts/**", "tests/**", "docs/**"]

    @staticmethod
    def _default_expected_outputs_for_phase(id_suffix: str, sprint_number: int) -> list[str]:
        if id_suffix == "docs-update":
            return [
                "관련 스펙/ADR/가이드 문서 업데이트",
                f"`.harness/tasks/sprint-{sprint_number}/docs-diff.md` 생성 가능 상태",
            ]
        if id_suffix == "tests":
            return ["변경 동작을 검증하는 단위/통합 테스트"]
        if id_suffix == "validation":
            return ["ruff, mypy, 구조 분석, pytest 결과 요약"]
        return ["스프린트 계약과 docs-diff에 맞는 최소 구현 변경"]

    @staticmethod
    def _default_verification_for_phase(id_suffix: str) -> str:
        if id_suffix == "validation":
            return "ruff check && mypy harness && python3 scripts/check_structure.py && pytest"
        if id_suffix == "tests":
            return "pytest"
        return "변경 범위에 맞는 관련 테스트를 실행하세요."
