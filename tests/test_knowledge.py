"""harness/context/knowledge.py 테스트."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from harness.context.knowledge import KnowledgeEntry, KnowledgeStore

if TYPE_CHECKING:
    from pathlib import Path


class TestKnowledgeStore:
    def test_record_and_load(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        store.record(KnowledgeEntry(
            task="구조 게이트 수정",
            run_id="abc",
            sprint_number=1,
            attempt=1,
            passed=True,
            score=9.0,
            applied_adrs=["0010-structure.md"],
        ))
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].task == "구조 게이트 수정"
        assert loaded[0].timestamp  # 자동 채워짐

    def test_index_written(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        store.record(KnowledgeEntry(
            applied_adrs=["0010.md"], failure_causes=["pytest 실패"], passed=False,
        ))
        index_path = tmp_path / ".harness" / "knowledge" / "index.json"
        assert index_path.exists()
        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert data["total_entries"] == 1
        assert data["adr_application_counts"]["0010.md"] == 1
        assert "pytest 실패" in data["top_failure_causes"]

    def test_recent_returns_latest_first(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        store.record(KnowledgeEntry(task="첫 번째", sprint_number=1))
        store.record(KnowledgeEntry(task="두 번째", sprint_number=2))
        recent = store.recent(limit=1)
        assert len(recent) == 1
        assert recent[0].task == "두 번째"

    def test_relevant_keyword_match(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        store.record(KnowledgeEntry(task="센서 의존성 정리", sprint_number=1))
        store.record(KnowledgeEntry(task="PR 본문 개선", sprint_number=2))
        relevant = store.relevant("센서 단방향 의존성")
        assert relevant
        assert relevant[0].task == "센서 의존성 정리"

    def test_relevant_falls_back_to_recent(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        store.record(KnowledgeEntry(task="무관한 작업", sprint_number=1))
        relevant = store.relevant("전혀다른키워드xyz")
        assert len(relevant) == 1

    def test_relevant_no_fallback_on_zero_match(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        store.record(KnowledgeEntry(task="무관한 작업", sprint_number=1))
        relevant = store.relevant("전혀다른키워드xyz", fallback_to_recent=False)
        assert relevant == []

    def test_relevant_no_fallback_on_empty_keywords(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        store.record(KnowledgeEntry(task="작업", sprint_number=1))
        relevant = store.relevant("", fallback_to_recent=False)
        assert relevant == []

    def test_load_all_skips_corrupt_lines(self, tmp_path: Path) -> None:
        knowledge_dir = tmp_path / ".harness" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "entries.jsonl").write_text(
            '{"task": "정상"}\n깨진 줄\n{"task": "정상2"}\n', encoding="utf-8",
        )
        store = KnowledgeStore(tmp_path)
        loaded = store.load_all()
        assert [e.task for e in loaded] == ["정상", "정상2"]

    def test_missing_store_returns_empty(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        assert store.load_all() == []
        assert store.recent() == []
        assert store.relevant("무엇이든") == []

    def test_to_markdown_empty(self) -> None:
        md = KnowledgeStore.to_markdown([])
        assert "과거 실행 이력이 없습니다" in md

    def test_to_markdown_renders_entries(self) -> None:
        md = KnowledgeStore.to_markdown([
            KnowledgeEntry(
                task="작업 A", sprint_number=1, attempt=2, passed=False,
                applied_adrs=["0010.md"], failure_causes=["mypy 타입 실패"],
            )
        ])
        assert "Sprint 1 시도 2" in md
        assert "실패" in md
        assert "0010.md" in md
        assert "mypy 타입 실패" in md
