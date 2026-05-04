"""harness/guides/context_filter.py 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from harness.guides.context_filter import (
    ContextFilter,
    FilteredContext,
    _extract_key_sections,
    _extract_keywords,
)


class TestExtractKeywords:
    def test_basic_extraction(self) -> None:
        keywords = _extract_keywords("리뷰 워크플로 설계 의도 문서 생성")
        assert "리뷰" not in keywords  # 2자 이하
        assert "워크플로" in keywords
        assert "설계" not in keywords  # 2자 이하
        assert "의도" not in keywords  # 2자 이하
        assert "문서" not in keywords  # 2자 이하

    def test_english_keywords(self) -> None:
        keywords = _extract_keywords("implement phase execution and context isolation")
        assert "implement" in keywords
        assert "phase" in keywords
        assert "execution" in keywords
        assert "and" not in keywords  # stopword

    def test_empty_input(self) -> None:
        assert _extract_keywords("") == []

    def test_deduplication(self) -> None:
        keywords = _extract_keywords("test test test")
        assert keywords.count("test") == 1


class TestExtractKeySections:
    def test_extract_decision_section(self) -> None:
        content = (
            "# ADR-0001\n\n"
            "## Context\n\nSome context.\n\n"
            "## 결정\n\n결정 내용입니다.\n\n"
            "## 이유\n\n이유 설명.\n\n"
            "## 결과\n\n결과 내용.\n"
        )
        result = _extract_key_sections(content)
        assert "결정 내용" in result
        assert "이유 설명" in result
        assert "결과 내용" not in result

    def test_fallback_to_trimmed_content(self) -> None:
        content = "짧은 내용만 있는 ADR."
        result = _extract_key_sections(content)
        assert "짧은 내용" in result


class TestFilteredContext:
    def test_to_markdown_empty(self) -> None:
        ctx = FilteredContext(task_description="테스트")
        md = ctx.to_markdown()
        assert "관련된 ADR/컨벤션이 없습니다" in md

    def test_to_markdown_with_adrs(self) -> None:
        ctx = FilteredContext(
            task_description="테스트",
            relevant_adrs=[{
                "filename": "0001.md",
                "title": "테스트 ADR",
                "content": "내용",
            }],
            relevance_scores={"0001.md": 3.5},
        )
        md = ctx.to_markdown()
        assert "0001.md" in md
        assert "테스트 ADR" in md
        assert "3.5" in md


class TestContextFilter:
    def test_filter_empty_project(self, tmp_path: Path) -> None:
        cf = ContextFilter(tmp_path)
        result = cf.filter("리뷰 워크플로")
        assert isinstance(result, FilteredContext)
        assert result.relevant_adrs == []
        assert result.relevant_conventions == []

    def test_filter_with_adrs(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "0001-test.md").write_text(
            "# 테스트 아키텍처\n\nstatus: accepted\n\n## 결정\n\n"
            "에이전트 아키텍처를 도입한다.\n",
            encoding="utf-8",
        )
        (adr_dir / "0002-other.md").write_text(
            "# 다른 결정\n\nstatus: accepted\n\n## 결정\n\n"
            "관계없는 내용.\n",
            encoding="utf-8",
        )

        cf = ContextFilter(tmp_path)
        result = cf.filter("에이전트 아키텍처 구현")
        assert len(result.relevant_adrs) >= 1
        assert any("0001" in adr.get("filename", "") for adr in result.relevant_adrs)

    def test_filter_with_conventions(self, tmp_path: Path) -> None:
        conv_path = tmp_path / "docs" / "code-convention.yaml"
        conv_path.parent.mkdir(parents=True, exist_ok=True)
        conv_path.write_text(
            "conventions:\n"
            "  - id: shell-safe\n"
            "    description: 셸 명령은 안전하게 실행\n"
            "    tags: [security, shell]\n"
            "    severity: error\n"
            "    category: security\n"
            "  - id: no-print\n"
            "    description: print 대신 logging 사용\n"
            "    tags: [logging]\n"
            "    severity: warning\n"
            "    category: maintainability\n",
            encoding="utf-8",
        )

        cf = ContextFilter(tmp_path)
        result = cf.filter("shell 보안 검증")
        assert len(result.relevant_conventions) >= 1
        assert any(c.id == "shell-safe" for c in result.relevant_conventions)

    def test_filter_empty_description(self, tmp_path: Path) -> None:
        cf = ContextFilter(tmp_path)
        result = cf.filter("")
        assert result.relevant_adrs == []
        assert result.relevant_conventions == []

    def test_filter_with_external_adr_sources(self, tmp_path: Path) -> None:
        ext_dir = tmp_path / "external" / "adr"
        ext_dir.mkdir(parents=True)
        (ext_dir / "0001-ext.md").write_text(
            "# 외부 에이전트 아키텍처\n\nstatus: accepted\n\n## 결정\n\n"
            "에이전트 기반 아키텍처 채택.\n",
            encoding="utf-8",
        )
        cf = ContextFilter(tmp_path, external_adr_sources=[str(ext_dir)])
        result = cf.filter("에이전트 아키텍처")
        assert len(result.relevant_adrs) >= 1
        assert any("0001-ext" in adr.get("filename", "") for adr in result.relevant_adrs)

    def test_filter_with_missing_external_source(self, tmp_path: Path) -> None:
        cf = ContextFilter(tmp_path, external_adr_sources=[str(tmp_path / "nonexistent")])
        result = cf.filter("에이전트")
        assert result.relevant_adrs == []

    def test_score_adrs_ordering(self) -> None:
        adrs = [
            {"filename": "a.md", "title": "관련 없는 ADR", "content": "무관한 내용", "status": "accepted"},
            {"filename": "b.md", "title": "테스트 에이전트", "content": "에이전트 아키텍처 설명", "status": "accepted"},
        ]
        scored = ContextFilter._score_adrs(adrs, ["에이전트", "아키텍처"])
        assert scored[0][0]["filename"] == "b.md"
        assert scored[0][1] > scored[1][1]
