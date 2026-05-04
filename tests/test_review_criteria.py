"""CriteriaGenerator, ADRLoader 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from harness.review.criteria import ADRLoader, CriteriaGenerator, EvalCriterion

ACCEPTED_ADR = """\
---
status: accepted
date: 2026-04-26
---

# ADR-0001: 3-에이전트 아키텍처 채택

## Context
AI 에이전트 자기 평가 편향 문제.

## Decision
Planner, Generator, Evaluator 3-에이전트 구조 채택.

## Consequences
비용 증가, 품질 향상.
"""

DRAFT_ADR = """\
---
status: draft
---

# ADR-0099: 미완성 아키텍처

## Context
미완성.
"""

CONVENTION_YAML = """\
conventions:
  - id: type-hints-required
    description: "타입 힌트 필수"
    category: type-safety
    severity: error
    tags: [typing]
  - id: shell-safe
    description: "안전한 셸 실행"
    category: security
    severity: error
    tags: [security]
"""


def setup_project(tmp_path: Path) -> Path:
    """테스트용 프로젝트 구조를 생성한다."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-three-agent.md").write_text(ACCEPTED_ADR, encoding="utf-8")
    (adr_dir / "0099-draft.md").write_text(DRAFT_ADR, encoding="utf-8")

    docs_dir = tmp_path / "docs"
    (docs_dir / "code-convention.yaml").write_text(CONVENTION_YAML, encoding="utf-8")
    return tmp_path


class TestADRLoader:
    def test_load_all_reads_all_md(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        loader = ADRLoader(project / "docs" / "adr")
        adrs = loader.load_all()
        assert len(adrs) == 2

    def test_load_all_extracts_title(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        loader = ADRLoader(project / "docs" / "adr")
        adrs = loader.load_all()
        titles = [a["title"] for a in adrs]
        assert "ADR-0001: 3-에이전트 아키텍처 채택" in titles

    def test_load_all_extracts_status(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        loader = ADRLoader(project / "docs" / "adr")
        adrs = loader.load_all()
        statuses = {a["filename"]: a["status"] for a in adrs}
        assert statuses["0001-three-agent.md"] == "accepted"
        assert statuses["0099-draft.md"] == "draft"

    def test_load_all_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        loader = ADRLoader(tmp_path / "docs" / "nonexistent")
        assert loader.load_all() == []

    def test_filter_relevant_keyword_match(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        loader = ADRLoader(project / "docs" / "adr")
        adrs = loader.load_all()
        relevant = loader.filter_relevant("에이전트 아키텍처", adrs)
        assert len(relevant) >= 1
        titles = [a["title"] for a in relevant]
        assert any("에이전트" in t for t in titles)

    def test_filter_relevant_empty_description_returns_all(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        loader = ADRLoader(project / "docs" / "adr")
        adrs = loader.load_all()
        relevant = loader.filter_relevant("", adrs)
        assert relevant == adrs

    def test_filter_relevant_no_match_returns_first_three(self, tmp_path: Path) -> None:
        # ADR이 2개이므로 둘 다 반환된다
        project = setup_project(tmp_path)
        loader = ADRLoader(project / "docs" / "adr")
        adrs = loader.load_all()
        relevant = loader.filter_relevant("완전히무관한내용xyz", adrs)
        assert len(relevant) <= 3

    def test_extract_keywords_filters_stopwords(self) -> None:
        loader = ADRLoader(Path("."))
        keywords = loader._extract_keywords("the agent and the system")
        assert "the" not in keywords
        assert "and" not in keywords
        assert "agent" in keywords
        assert "system" in keywords


class TestADRLoaderExternalSources:
    def test_load_from_external_sources_valid_dir(self, tmp_path: Path) -> None:
        ext_dir = tmp_path / "external" / "adr"
        ext_dir.mkdir(parents=True)
        (ext_dir / "0001-ext.md").write_text(
            "# External ADR\nstatus: accepted\n", encoding="utf-8",
        )
        adrs = ADRLoader.load_from_external_sources([str(ext_dir)])
        assert len(adrs) == 1
        assert adrs[0]["title"] == "External ADR"
        assert adrs[0]["source"] == str(ext_dir.resolve())

    def test_load_from_external_sources_missing_dir(self, tmp_path: Path) -> None:
        adrs = ADRLoader.load_from_external_sources([str(tmp_path / "nonexistent")])
        assert adrs == []

    def test_load_from_external_sources_file_not_dir(self, tmp_path: Path) -> None:
        f = tmp_path / "not-a-dir.md"
        f.write_text("text", encoding="utf-8")
        adrs = ADRLoader.load_from_external_sources([str(f)])
        assert adrs == []

    def test_load_from_external_sources_empty_list(self) -> None:
        adrs = ADRLoader.load_from_external_sources([])
        assert adrs == []

    def test_load_from_external_sources_mixed_valid_invalid(self, tmp_path: Path) -> None:
        valid_dir = tmp_path / "valid"
        valid_dir.mkdir()
        (valid_dir / "0001.md").write_text("# Valid\nstatus: accepted\n", encoding="utf-8")

        adrs = ADRLoader.load_from_external_sources([
            str(tmp_path / "nonexistent"),
            str(valid_dir),
        ])
        assert len(adrs) == 1
        assert adrs[0]["title"] == "Valid"

    def test_load_from_external_sources_tilde_expansion(self, tmp_path: Path) -> None:
        adrs = ADRLoader.load_from_external_sources(["~/nonexistent_adr_dir_xyz"])
        assert adrs == []

    def test_load_from_dir_skips_unreadable_files(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "adr"
        adr_dir.mkdir()
        good = adr_dir / "0001.md"
        good.write_text("# Good\nstatus: accepted\n", encoding="utf-8")
        adrs = ADRLoader._load_from_dir(adr_dir, source="test")
        assert len(adrs) == 1
        assert adrs[0]["source"] == "test"


class TestCriteriaGenerator:
    def test_generate_returns_criteria_list(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        gen = CriteriaGenerator(project)
        criteria = gen.generate()
        assert isinstance(criteria, list)

    def test_generate_includes_adr_criteria(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        gen = CriteriaGenerator(project)
        criteria = gen.generate()
        sources = [c.source for c in criteria]
        assert "adr" in sources

    def test_generate_excludes_draft_adrs(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        gen = CriteriaGenerator(project)
        criteria = gen.generate()
        # draft ADR(0099)은 포함되지 않아야 함
        ids = [c.id for c in criteria]
        assert not any("0099" in cid for cid in ids)

    def test_generate_includes_convention_criteria(self, tmp_path: Path) -> None:
        project = setup_project(tmp_path)
        gen = CriteriaGenerator(project)
        criteria = gen.generate()
        sources = [c.source for c in criteria]
        assert "convention" in sources

    def test_generate_no_adrs_returns_convention_only(self, tmp_path: Path) -> None:
        # ADR 없이 컨벤션만 있는 경우
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "code-convention.yaml").write_text(CONVENTION_YAML, encoding="utf-8")
        gen = CriteriaGenerator(tmp_path)
        criteria = gen.generate()
        assert all(c.source == "convention" for c in criteria)

    def test_to_markdown_empty_returns_no_criteria(self, tmp_path: Path) -> None:
        gen = CriteriaGenerator(tmp_path)
        md = gen.to_markdown([])
        assert "기준 없음" in md

    def test_to_markdown_groups_by_category(self, tmp_path: Path) -> None:
        gen = CriteriaGenerator(tmp_path)
        criteria = [
            EvalCriterion(id="a", description="A desc", source="manual", category="architecture"),
            EvalCriterion(id="b", description="B desc", source="manual", category="security"),
        ]
        md = gen.to_markdown(criteria)
        assert "architecture" in md
        assert "security" in md
        assert "a" in md
        assert "b" in md

    def test_eval_criterion_dataclass(self) -> None:
        c = EvalCriterion(id="test", description="d", source="adr")
        assert c.severity == "warning"
        assert c.category == "general"
