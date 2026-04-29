"""계약 저장소. 스프린트 계약을 파일 시스템에 저장·로드한다."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from harness.contracts.models import SprintContract

logger = logging.getLogger(__name__)

_CONTRACTS_DIR = ".harness" / Path("contracts")


class ContractStore:
    """스프린트 계약 파일 저장소.

    저장 경로: {project_dir}/.harness/contracts/sprint_{N}.json
    """

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self._base_dir = self.project_dir / _CONTRACTS_DIR

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def save(self, contract: SprintContract) -> Path:
        """계약을 atomic write로 JSON 저장한다."""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(contract.sprint_number)
        self._atomic_write(path, contract.to_json())
        logger.info("계약 저장: %s", path)
        return path

    def load(self, sprint_number: int) -> SprintContract | None:
        """스프린트 번호로 계약을 로드한다. 없으면 None."""
        path = self._path_for(sprint_number)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SprintContract.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("계약 파싱 실패 (sprint %d): %s", sprint_number, e)
            return None

    def exists(self, sprint_number: int) -> bool:
        return self._path_for(sprint_number).exists()

    def list_sprints(self) -> list[int]:
        """저장된 계약의 스프린트 번호 목록을 정렬하여 반환한다."""
        if not self._base_dir.exists():
            return []
        numbers: list[int] = []
        for path in self._base_dir.glob("sprint_*.json"):
            stem = path.stem  # e.g. "sprint_1"
            parts = stem.split("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                numbers.append(int(parts[1]))
        return sorted(numbers)

    def _path_for(self, sprint_number: int) -> Path:
        return self._base_dir / f"sprint_{sprint_number}.json"

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix=".contract-",
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
