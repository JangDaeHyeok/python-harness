"""체크포인트 저장/복원. 하네스 실행 상태를 파일로 저장하여 중단 후 재시작을 지원한다."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)


class Phase(StrEnum):
    """실행 단계."""

    INIT = "init"
    PLANNING_DONE = "planning_done"
    SPRINT_START = "sprint_start"
    ATTEMPT_START = "attempt_start"
    IMPL_DONE = "impl_done"
    EVAL_DONE = "eval_done"
    SPRINT_DONE = "sprint_done"
    RUN_DONE = "run_done"


@dataclass
class AttemptState:
    """단일 구현 시도의 상태."""

    attempt: int
    impl_done: bool = False
    eval_done: bool = False
    passed: bool | None = None
    score: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AttemptState:
        return cls(
            attempt=int(str(data.get("attempt", 0))),
            impl_done=bool(data.get("impl_done", False)),
            eval_done=bool(data.get("eval_done", False)),
            passed=bool(data["passed"]) if data.get("passed") is not None else None,
            score=float(str(data["score"])) if data.get("score") is not None else None,
        )


@dataclass
class SprintState:
    """단일 스프린트의 상태."""

    sprint_number: int
    started: bool = False
    done: bool = False
    passed: bool | None = None
    current_attempt: int = 0
    attempts: list[AttemptState] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = asdict(self)
        d["attempts"] = [a.to_dict() for a in self.attempts]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SprintState:
        raw_attempts = data.get("attempts", [])
        attempts = [
            AttemptState.from_dict(a)
            for a in (raw_attempts if isinstance(raw_attempts, list) else [])
            if isinstance(a, dict)
        ]
        return cls(
            sprint_number=int(str(data.get("sprint_number", 0))),
            started=bool(data.get("started", False)),
            done=bool(data.get("done", False)),
            passed=bool(data["passed"]) if data.get("passed") is not None else None,
            current_attempt=int(str(data.get("current_attempt", 0))),
            attempts=attempts,
        )


@dataclass
class SessionState:
    """전체 실행 세션의 상태."""

    run_id: str
    user_prompt: str
    phase: str = Phase.INIT.value
    spec_json: str = ""
    sprints: list[SprintState] = field(default_factory=list)
    completed_sprint_numbers: list[int] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(tz=UTC).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def touch(self) -> None:
        self.updated_at = datetime.now(tz=UTC).isoformat()

    def to_json(self) -> str:
        d: dict[str, object] = {
            "run_id": self.run_id,
            "user_prompt": self.user_prompt,
            "phase": self.phase,
            "spec_json": self.spec_json,
            "sprints": [s.to_dict() for s in self.sprints],
            "completed_sprint_numbers": self.completed_sprint_numbers,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return json.dumps(d, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> SessionState:
        data = json.loads(text)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SessionState:
        raw_sprints = data.get("sprints", [])
        sprints = [
            SprintState.from_dict(s)
            for s in (raw_sprints if isinstance(raw_sprints, list) else [])
            if isinstance(s, dict)
        ]
        raw_completed = data.get("completed_sprint_numbers", [])
        completed = [
            int(str(n))
            for n in (raw_completed if isinstance(raw_completed, list) else [])
        ]
        return cls(
            run_id=str(data.get("run_id", "")),
            user_prompt=str(data.get("user_prompt", "")),
            phase=str(data.get("phase", Phase.INIT.value)),
            spec_json=str(data.get("spec_json", "")),
            sprints=sprints,
            completed_sprint_numbers=completed,
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


_CHECKPOINTS_DIR = Path(".harness") / "checkpoints"
_LATEST_FILENAME = "latest.json"


class CheckpointStore:
    """체크포인트 파일 저장소. atomic write로 안전하게 저장한다."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self._base_dir = self.project_dir / _CHECKPOINTS_DIR

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            raise ValueError(f"안전하지 않은 run_id입니다: {run_id!r}")

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def save(self, state: SessionState) -> Path:
        """체크포인트를 atomic write로 저장하고 latest 포인터를 갱신한다."""
        self._validate_run_id(state.run_id)
        state.touch()
        self._base_dir.mkdir(parents=True, exist_ok=True)

        path = self._path_for(state.run_id)
        self._atomic_write(path, state.to_json())

        latest_path = self._base_dir / _LATEST_FILENAME
        self._atomic_write(latest_path, json.dumps(
            {"run_id": state.run_id}, ensure_ascii=False,
        ))

        logger.info("체크포인트 저장: %s (phase=%s)", state.run_id, state.phase)
        return path

    def load(self, run_id: str) -> SessionState | None:
        """run_id로 체크포인트를 로드한다."""
        self._validate_run_id(run_id)
        path = self._path_for(run_id)
        if not path.exists():
            return None
        try:
            return SessionState.from_json(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("체크포인트 파싱 실패 (%s): %s", run_id, e)
            return None

    def load_latest(self) -> SessionState | None:
        """가장 최근 체크포인트를 로드한다."""
        latest_path = self._base_dir / _LATEST_FILENAME
        if not latest_path.exists():
            return None
        try:
            data = json.loads(latest_path.read_text(encoding="utf-8"))
            run_id = str(data.get("run_id", ""))
            if not run_id:
                return None
            return self.load(run_id)
        except (json.JSONDecodeError, KeyError):
            return None

    def exists(self, run_id: str) -> bool:
        self._validate_run_id(run_id)
        return self._path_for(run_id).exists()

    def list_runs(self) -> list[str]:
        """저장된 체크포인트의 run_id 목록을 반환한다."""
        if not self._base_dir.exists():
            return []
        return sorted(
            p.stem for p in self._base_dir.glob("*.json")
            if p.name != _LATEST_FILENAME
        )

    def _path_for(self, run_id: str) -> Path:
        return self._base_dir / f"{run_id}.json"

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix=".ckpt-",
        )
        closed = False
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            closed = True
            os.replace(tmp_path, str(path))
        except BaseException:
            if not closed:
                os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
