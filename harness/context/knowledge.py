"""실행 이력 기반 지식 스토어.

스프린트/시도 단위로 적용된 ADR, 평가 판정, 실패 원인, 점수를
`.harness/knowledge/` 아래에 로컬 파일(JSONL + 인덱스)로 누적 저장한다.
이후 Planner/Generator/Evaluator/PR 본문이 과거 결정 근거와 실패 패턴을
결정적으로 조회할 수 있게 한다. 외부 벡터 DB나 별도 서버는 쓰지 않는다.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from harness.tools.file_io import atomic_write_text

logger = logging.getLogger(__name__)

KNOWLEDGE_DIRNAME = "knowledge"
_ENTRIES_FILENAME = "entries.jsonl"
_INDEX_FILENAME = "index.json"
_MAX_ENTRIES = 500
_STOPWORDS = frozenset({
    "은", "는", "이", "가", "을", "를", "의", "에", "에서", "으로", "로",
    "the", "and", "for", "with",
})


@dataclass
class KnowledgeEntry:
    """단일 실행(스프린트 시도)에서 누적할 지식 항목."""

    task: str = ""
    mode: str = ""
    run_id: str = ""
    sprint_number: int = 0
    attempt: int = 0
    passed: bool = False
    score: float = 0.0
    applied_adrs: list[str] = field(default_factory=list)
    failure_causes: list[str] = field(default_factory=list)
    verdict_summary: str = ""
    changed_files: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> KnowledgeEntry:
        return cls(
            task=str(data.get("task", "")),
            mode=str(data.get("mode", "")),
            run_id=str(data.get("run_id", "")),
            sprint_number=_as_int(data.get("sprint_number")),
            attempt=_as_int(data.get("attempt")),
            passed=bool(data.get("passed", False)),
            score=_as_float(data.get("score")),
            applied_adrs=_as_str_list(data.get("applied_adrs")),
            failure_causes=_as_str_list(data.get("failure_causes")),
            verdict_summary=str(data.get("verdict_summary", "")),
            changed_files=_as_str_list(data.get("changed_files")),
            timestamp=str(data.get("timestamp", "")),
        )


class KnowledgeStore:
    """로컬 파일 기반 지식 누적 스토어."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self._dir = self.project_dir / ".harness" / KNOWLEDGE_DIRNAME
        self._entries_path = self._dir / _ENTRIES_FILENAME
        self._index_path = self._dir / _INDEX_FILENAME

    def record(self, entry: KnowledgeEntry) -> None:
        """지식 항목을 누적 저장하고 인덱스를 갱신한다 (실패해도 예외 전파 금지)."""
        try:
            if not entry.timestamp:
                entry.timestamp = datetime.now(UTC).isoformat(timespec="seconds")
            entries = self.load_all()
            entries.append(entry)
            if len(entries) > _MAX_ENTRIES:
                entries = entries[-_MAX_ENTRIES:]
            self._dir.mkdir(parents=True, exist_ok=True)
            payload = "\n".join(
                json.dumps(e.to_dict(), ensure_ascii=False) for e in entries
            )
            atomic_write_text(self._entries_path, payload + "\n", prefix=".knowledge-")
            self._write_index(entries)
            logger.info(
                "지식 기록: run=%s sprint=%d attempt=%d passed=%s",
                entry.run_id, entry.sprint_number, entry.attempt, entry.passed,
            )
        except (OSError, ValueError, TypeError) as e:
            logger.warning("지식 기록 실패 (무시하고 진행): %s", e)

    def load_all(self) -> list[KnowledgeEntry]:
        """저장된 모든 지식 항목을 읽는다. 파일이 없거나 손상되면 빈 목록."""
        if not self._entries_path.exists():
            return []
        entries: list[KnowledgeEntry] = []
        try:
            for line in self._entries_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("지식 항목 파싱 실패 — 건너뜀")
                    continue
                if isinstance(data, dict):
                    entries.append(KnowledgeEntry.from_dict(data))
        except OSError as e:
            logger.warning("지식 파일 읽기 실패: %s", e)
            return []
        return entries

    def recent(self, limit: int = 5) -> list[KnowledgeEntry]:
        """최근 항목을 최신순으로 반환한다."""
        return list(reversed(self.load_all()))[:limit]

    def relevant(
        self,
        task_description: str,
        limit: int = 5,
        *,
        fallback_to_recent: bool = True,
    ) -> list[KnowledgeEntry]:
        """작업 설명과 관련도가 높은 과거 항목을 반환한다.

        키워드가 없거나 매칭이 0건일 때, 기본적으로 최근 항목으로 폴백한다.
        무관한 과거 이력이 근거로 들어가면 안 되는 경로(PR 본문 등)는
        ``fallback_to_recent=False``로 호출해 빈 목록을 받는다.
        """
        keywords = _keywords(task_description)
        if not keywords:
            return self.recent(limit) if fallback_to_recent else []
        scored: list[tuple[KnowledgeEntry, int]] = []
        for entry in self.load_all():
            haystack = " ".join((
                entry.task,
                " ".join(entry.applied_adrs),
                " ".join(entry.changed_files),
                " ".join(entry.failure_causes),
            )).lower()
            score = sum(1 for kw in keywords if kw in haystack)
            if score > 0:
                scored.append((entry, score))
        if not scored:
            return self.recent(limit) if fallback_to_recent else []
        scored.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in scored[:limit]]

    def _write_index(self, entries: list[KnowledgeEntry]) -> None:
        adr_counts: dict[str, int] = {}
        failure_counts: dict[str, int] = {}
        passed = 0
        for entry in entries:
            if entry.passed:
                passed += 1
            for adr in entry.applied_adrs:
                adr_counts[adr] = adr_counts.get(adr, 0) + 1
            for cause in entry.failure_causes:
                failure_counts[cause] = failure_counts.get(cause, 0) + 1
        index = {
            "total_entries": len(entries),
            "passed_entries": passed,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "adr_application_counts": dict(
                sorted(adr_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "top_failure_causes": dict(
                sorted(failure_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
        }
        atomic_write_text(
            self._index_path,
            json.dumps(index, ensure_ascii=False, indent=2),
            prefix=".knowledge-index-",
        )

    @staticmethod
    def to_markdown(entries: list[KnowledgeEntry], title: str = "과거 실행 지식") -> str:
        """지식 항목 목록을 컨텍스트 주입용 마크다운으로 변환한다."""
        if not entries:
            return f"## {title}\n\n_참고할 과거 실행 이력이 없습니다._\n"
        lines = [f"## {title}\n"]
        for entry in entries:
            verdict = "통과" if entry.passed else "실패"
            lines.append(
                f"### Sprint {entry.sprint_number} 시도 {entry.attempt} — "
                f"{verdict} (점수 {entry.score})"
            )
            if entry.task:
                lines.append(f"- 작업: {entry.task[:120]}")
            if entry.applied_adrs:
                lines.append(f"- 적용 ADR: {', '.join(entry.applied_adrs)}")
            if entry.failure_causes:
                lines.append(f"- 실패 원인: {'; '.join(entry.failure_causes[:5])}")
            if entry.verdict_summary:
                lines.append(f"- 판정 요약: {entry.verdict_summary[:200]}")
            lines.append("")
        return "\n".join(lines)


def _keywords(text: str) -> list[str]:
    words = re.findall(r"adr-\d{3,4}|[a-zA-Z]{3,}|[가-힣]{2,}|\d{3,4}", text.lower())
    return list(dict.fromkeys(w for w in words if w not in _STOPWORDS))


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return []
