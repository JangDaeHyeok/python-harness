"""코드 컨벤션 YAML 로더.

docs/code-convention.yaml을 읽고 필터링하여 평가 기준 생성에 활용한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONVENTION_PATH = Path("docs") / "code-convention.yaml"


@dataclass
class CodeConvention:
    """코드 컨벤션 규칙 항목."""

    id: str
    description: str
    tags: list[str] = field(default_factory=list)
    severity: str = "warning"  # "error" | "warning" | "info"
    category: str = "general"


class ConventionLoader:
    """docs/code-convention.yaml을 읽고 필터링하는 로더."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)  # normalize
        self._conventions: list[CodeConvention] | None = None

    def load(self) -> list[CodeConvention]:
        """컨벤션 파일을 읽어 반환한다. 파일 없으면 빈 목록."""
        if self._conventions is not None:
            return self._conventions

        path = self.project_dir / DEFAULT_CONVENTION_PATH
        if not path.exists():
            logger.warning("컨벤션 파일 없음: %s", path)
            self._conventions = []
            return self._conventions

        try:
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            logger.error("컨벤션 YAML 파싱 실패: %s", e)
            self._conventions = []
            return self._conventions

        if not isinstance(raw, dict):
            logger.warning("컨벤션 파일 형식 오류: 최상위 dict 필요")
            self._conventions = []
            return self._conventions

        conventions: list[CodeConvention] = []
        for item in raw.get("conventions", []):
            if not isinstance(item, dict):
                continue
            conventions.append(
                CodeConvention(
                    id=str(item.get("id", "")),
                    description=str(item.get("description", "")),
                    tags=list(item.get("tags", [])),
                    severity=str(item.get("severity", "warning")),
                    category=str(item.get("category", "general")),
                )
            )
        self._conventions = conventions
        logger.info("컨벤션 %d개 로드 완료", len(conventions))
        return conventions

    def filter_by_tags(self, tags: list[str]) -> list[CodeConvention]:
        """태그 중 하나라도 일치하는 컨벤션만 반환한다."""
        tag_set = set(tags)
        return [c for c in self.load() if tag_set.intersection(c.tags)]

    def filter_by_category(self, category: str) -> list[CodeConvention]:
        """카테고리가 일치하는 컨벤션만 반환한다."""
        return [c for c in self.load() if c.category == category]
