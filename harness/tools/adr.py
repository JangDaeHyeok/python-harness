"""ADR 파일 로딩 유틸리티.

ADR을 지식 DB 항목으로 다루기 위해, 본문 외에 상태·번호·태그·범위·
영향 경로·관련 ADR 같은 메타데이터를 함께 추출한다. 메타데이터는 선택적인
YAML frontmatter와 한국어 헤더 불릿(`- **상태**: ...` 등) 두 형식을 모두
지원하며, 둘 다 없으면 빈 값으로 폴백한다(기존 ADR과 호환).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_KEY_SECTION_MARKERS = (
    "## 결정", "## decision",
    "## 이유", "## rationale",
    "## 배경", "## context",
    "## 결과", "## consequences",
)

# 한국어/영어 메타데이터 라벨 → 정규화 키 매핑.
_META_LABELS: dict[str, str] = {
    "status": "status", "상태": "status",
    "date": "date", "날짜": "date",
    "tags": "tags", "태그": "tags",
    "scope": "scope", "범위": "scope",
    "affected_paths": "affected_paths", "영향 경로": "affected_paths", "영향경로": "affected_paths",
    "related": "related_adrs", "관련 adr": "related_adrs", "관련": "related_adrs",
}

_LIST_META_KEYS = frozenset({"tags", "scope", "affected_paths", "related_adrs"})


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
            entry = ADRLoader._build_entry(path.name, content)
            if source:
                entry["source"] = source
            adrs.append(entry)
        return adrs

    @staticmethod
    def _build_entry(filename: str, content: str) -> dict[str, str]:
        """파일명과 본문에서 ADR 항목(메타데이터 포함)을 구성한다."""
        meta = ADRLoader._extract_metadata(content)
        entry: dict[str, str] = {
            "filename": filename,
            "content": content,
            "title": ADRLoader._extract_title(content),
            "status": ADRLoader._extract_status(content),
            "number": ADRLoader._extract_number(filename, content),
            "tags": meta.get("tags", ""),
            "scope": meta.get("scope", ""),
            "affected_paths": meta.get("affected_paths", ""),
            "related_adrs": meta.get("related_adrs", ""),
            "date": meta.get("date", ""),
        }
        return entry

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
        self,
        task_description: str,
        adrs: list[dict[str, str]],
        *,
        fallback_to_first: bool = True,
    ) -> list[dict[str, str]]:
        """task_description 키워드와 관련 있는 ADR만 반환한다.

        매칭이 0건일 때 기본적으로 앞 3개를 폴백으로 반환한다(컨텍스트 보강용).
        무관한 ADR이 근거로 들어가면 안 되는 경로(PR 본문 등)는
        ``fallback_to_first=False``로 호출해 빈 목록을 받는다.
        """
        if not task_description.strip():
            return adrs

        keywords = self._extract_keywords(task_description)
        if not keywords:
            return adrs

        relevant: list[dict[str, str]] = []
        for adr in adrs:
            haystack = " ".join((
                adr.get("title", ""),
                adr.get("content", ""),
                adr.get("tags", ""),
                adr.get("scope", ""),
            )).lower()
            if any(kw in haystack for kw in keywords):
                relevant.append(adr)

        if relevant:
            return relevant
        return adrs[:3] if fallback_to_first else []

    @staticmethod
    def _extract_title(content: str) -> str:
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return "제목 없음"

    @staticmethod
    def _extract_status(content: str) -> str:
        """상태를 추출한다.

        frontmatter `status: accepted`와 한국어 헤더 `- **상태**: Accepted`를
        모두 지원하며 대소문자를 무시하고 소문자로 정규화한다.
        """
        match = re.search(
            r"(?im)^\s*[-*]?\s*(?:\*\*)?\s*(?:status|상태)\s*(?:\*\*)?\s*[:：]\s*([^\s*]+)",  # noqa: RUF001
            content,
        )
        return match.group(1).strip().lower() if match else "unknown"

    @staticmethod
    def _extract_number(filename: str, content: str) -> str:
        """ADR 번호를 추출한다 (파일명 우선, 없으면 제목)."""
        name_match = re.match(r"(\d{3,4})", filename)
        if name_match:
            return name_match.group(1)
        title_match = re.search(r"ADR-(\d{3,4})", content)
        return title_match.group(1) if title_match else ""

    @staticmethod
    def _extract_metadata(content: str) -> dict[str, str]:
        """frontmatter와 한국어 헤더 불릿에서 메타데이터를 추출한다.

        리스트형 값(tags/scope/affected_paths/related_adrs)은 쉼표로 연결한 문자열로
        정규화한다. 값이 없으면 키를 생략한다.
        """
        meta: dict[str, str] = {}
        meta.update(ADRLoader._metadata_from_frontmatter(content))
        for label_key, value in ADRLoader._metadata_from_header_bullets(content):
            meta.setdefault(label_key, value)
        return meta

    @staticmethod
    def _metadata_from_frontmatter(content: str) -> dict[str, str]:
        fm = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not fm:
            return {}
        try:
            parsed = yaml.safe_load(fm.group(1))
        except yaml.YAMLError as e:
            logger.warning("ADR frontmatter 파싱 실패: %s", e)
            return {}
        if not isinstance(parsed, dict):
            return {}
        meta: dict[str, str] = {}
        for raw_key, raw_val in parsed.items():
            key = _META_LABELS.get(str(raw_key).strip().lower())
            if not key:
                continue
            meta[key] = ADRLoader._normalize_frontmatter_value(key, raw_val)
        return meta

    @staticmethod
    def _normalize_frontmatter_value(key: str, raw: object) -> str:
        """frontmatter 값(스칼라/리스트)을 정규화 문자열로 변환한다."""
        if isinstance(raw, list):
            if key not in _LIST_META_KEYS:
                return ", ".join(str(item).strip() for item in raw)
            parts = [str(item).strip().strip("`'\"") for item in raw if str(item).strip()]
            return ", ".join(parts)
        return ADRLoader._normalize_meta_value(key, str(raw if raw is not None else ""))

    @staticmethod
    def _metadata_from_header_bullets(content: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        for match in re.finditer(
            r"(?im)^\s*[-*]\s*(?:\*\*)?\s*([^:：*]+?)\s*(?:\*\*)?\s*[:：]\s*(.+)$",  # noqa: RUF001
            content,
        ):
            label = match.group(1).strip().lower()
            key = _META_LABELS.get(label)
            if not key:
                continue
            results.append((key, ADRLoader._normalize_meta_value(key, match.group(2))))
        return results

    @staticmethod
    def _normalize_meta_value(key: str, raw: str) -> str:
        value = raw.strip().strip("*").strip()
        value = value.strip("[]")
        if key not in _LIST_META_KEYS:
            return value
        parts = [p.strip().strip("`'\"") for p in re.split(r"[,，]", value) if p.strip()]  # noqa: RUF001
        return ", ".join(parts)

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """텍스트에서 의미 있는 단어를 추출하고 불용어를 제거한다.

        한글은 2글자 이상, 영문은 3글자 이상을 키워드로 본다.
        """
        stopwords = {
            "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of",
            "은", "는", "이", "가", "을", "를", "의", "에", "에서",
        }
        words = re.findall(r"[a-zA-Z]{3,}|[가-힣]{2,}", text.lower())
        return [w for w in words if w not in stopwords]


def extract_key_sections(content: str, fallback_limit: int = 500) -> str:
    """ADR 마크다운에서 핵심 섹션(배경/결정/이유/결과)만 추출한다.

    핵심 섹션을 찾지 못하면 본문 앞부분을 잘라 반환한다.
    """
    lines = content.splitlines()
    result: list[str] = []
    in_key_section = False

    for line in lines:
        lower = line.lower().strip()
        is_marker = any(key in lower for key in _KEY_SECTION_MARKERS)
        if is_marker:
            in_key_section = True
            result.append(line)
            continue
        if in_key_section:
            if line.startswith("## ") and not is_marker:
                in_key_section = False
                continue
            result.append(line)

    if not result:
        trimmed = content[:fallback_limit]
        if len(content) > fallback_limit:
            trimmed += "\n..."
        return trimmed

    return "\n".join(result)
