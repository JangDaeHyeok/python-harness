"""ADR 파일 로딩 유틸리티."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class ADRLoader:
    """ADR 디렉터리의 마크다운 파일을 읽고 키워드 기반으로 필터링한다."""

    def __init__(self, adr_dir: Path) -> None:
        self.adr_dir = Path(adr_dir)

    def load_all(self) -> list[dict[str, str]]:
        """ADR 디렉터리의 모든 .md 파일을 메타데이터와 함께 반환한다."""
        return self._load_from_dir(self.adr_dir)

    @staticmethod
    def _load_from_dir(adr_dir: Path, source: str = "") -> list[dict[str, str]]:
        """단일 디렉터리에서 ADR을 로드한다."""
        if not adr_dir.is_dir():
            return []
        adrs: list[dict[str, str]] = []
        for path in sorted(adr_dir.glob("*.md")):
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning("ADR 파일 읽기 실패 (%s): %s", path, e)
                continue
            entry: dict[str, str] = {
                "filename": path.name,
                "content": content,
                "title": ADRLoader._extract_title(content),
                "status": ADRLoader._extract_status(content),
            }
            if source:
                entry["source"] = source
            adrs.append(entry)
        return adrs

    @staticmethod
    def load_from_external_sources(sources: list[str]) -> list[dict[str, str]]:
        """외부 ADR 소스 경로 목록에서 ADR을 로드한다."""
        adrs: list[dict[str, str]] = []
        for raw_path in sources:
            resolved = Path(raw_path).expanduser().resolve()
            if not resolved.is_dir():
                logger.info("외부 ADR 소스 건너뜀 (존재하지 않거나 디렉터리가 아님): %s", raw_path)
                continue
            loaded = ADRLoader._load_from_dir(resolved, source=str(resolved))
            logger.info("외부 ADR 소스 로드: %s (%d개)", raw_path, len(loaded))
            adrs.extend(loaded)
        return adrs

    def filter_relevant(
        self, task_description: str, adrs: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """task_description 키워드와 관련 있는 ADR만 반환한다."""
        if not task_description.strip():
            return adrs

        keywords = self._extract_keywords(task_description)
        if not keywords:
            return adrs

        relevant: list[dict[str, str]] = []
        for adr in adrs:
            text = (adr["title"] + " " + adr["content"]).lower()
            if any(kw in text for kw in keywords):
                relevant.append(adr)

        return relevant if relevant else adrs[:3]

    @staticmethod
    def _extract_title(content: str) -> str:
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return "제목 없음"

    @staticmethod
    def _extract_status(content: str) -> str:
        match = re.search(r"status:\s*(\w+)", content)
        return match.group(1) if match else "unknown"

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """텍스트에서 3자 이상 단어를 추출하고 불용어를 제거한다."""
        stopwords = {
            "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of",
            "은", "는", "이", "가", "을", "를", "의", "에", "에서",
        }
        words = re.findall(r"[a-zA-Z가-힣]{3,}", text.lower())
        return [w for w in words if w not in stopwords]
