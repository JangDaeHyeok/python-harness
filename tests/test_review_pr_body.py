"""PRBodyGenerator 단위 테스트."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from harness.review.artifacts import ReviewArtifactManager
from harness.review.pr_body import DiffError, PRBodyGenerator, get_changed_files, get_git_diff_stat


class TestGitHelpers:
    def test_get_diff_stat_on_success(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body._resolve_base_ref", return_value="main"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=" 2 files changed\n", stderr=""
            )
            result = get_git_diff_stat(tmp_path)
        assert "files changed" in result

    def test_get_diff_stat_on_exception_raises(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body._resolve_base_ref", return_value="main"), \
             patch("subprocess.run", side_effect=Exception("git error")), \
             pytest.raises(DiffError, match="실행 실패"):
            get_git_diff_stat(tmp_path)

    def test_get_diff_stat_on_nonzero_returncode_raises(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body._resolve_base_ref", return_value="main"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr="bad base ref"
            )
            with pytest.raises(DiffError, match="bad base ref"):
                get_git_diff_stat(tmp_path)

    def test_get_changed_files_returns_list(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body._resolve_base_ref", return_value="main"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="foo.py\nbar.py\n", stderr=""
            )
            files = get_changed_files(tmp_path)
        assert files == ["foo.py", "bar.py"]

    def test_get_changed_files_filters_empty_lines(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body._resolve_base_ref", return_value="main"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="foo.py\n\n  \nbar.py\n", stderr=""
            )
            files = get_changed_files(tmp_path)
        assert "" not in files
        assert "  " not in files

    def test_get_changed_files_on_exception_raises(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body._resolve_base_ref", return_value="main"), \
             patch("subprocess.run", side_effect=Exception("error")), \
             pytest.raises(DiffError, match="실행 실패"):
            get_changed_files(tmp_path)

    def test_get_changed_files_on_nonzero_returncode_raises(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body._resolve_base_ref", return_value="main"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr="invalid base"
            )
            with pytest.raises(DiffError, match="invalid base"):
                get_changed_files(tmp_path)


class TestPRBodyGenerator:
    def _make_manager(self, tmp_path: Path) -> ReviewArtifactManager:
        return ReviewArtifactManager(tmp_path, branch="test")

    def test_generate_returns_string(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch("harness.review.pr_body.get_changed_files", return_value=[]):
            manager = self._make_manager(tmp_path)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_includes_summary_section(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch("harness.review.pr_body.get_changed_files", return_value=[]):
            manager = self._make_manager(tmp_path)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager)
        assert "## Summary" in result

    def test_generate_uses_explicit_summary(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch("harness.review.pr_body.get_changed_files", return_value=[]):
            manager = self._make_manager(tmp_path)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager, summary="특별한 요약입니다")
        assert "특별한 요약입니다" in result

    def test_generate_includes_changes_section(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch("harness.review.pr_body.get_changed_files", return_value=["a.py", "b.py"]):
            manager = self._make_manager(tmp_path)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager)
        assert "## Changes" in result
        assert "a.py" in result
        assert "b.py" in result

    def test_generate_includes_test_plan(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch("harness.review.pr_body.get_changed_files", return_value=[]):
            manager = self._make_manager(tmp_path)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager)
        assert "## Test Plan" in result
        assert "pytest" in result

    def test_generate_rationale_fallback_without_adrs(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch("harness.review.pr_body.get_changed_files", return_value=[]):
            manager = self._make_manager(tmp_path)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager)
        assert "## ADR Rationale" in result
        assert "관련 ADR을 찾지 못했습니다" in result

    def test_generate_includes_dynamic_adr_rationale(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "0010-structure.md").write_text(
            "# ADR-0010: 구조 강제\n\n- **상태**: Accepted\n"
            "- **영향 경로**: harness/context/\n\n"
            "## 결정\n\n외부 프로젝트의 고정 구조를 강제한다.\n",
            encoding="utf-8",
        )
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch(
                 "harness.review.pr_body.get_changed_files",
                 return_value=["harness/context/structure_gate.py"],
             ):
            manager = self._make_manager(tmp_path)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager, summary="구조 게이트 강제")
        assert "## ADR Rationale" in result
        assert "ADR-0010" in result
        assert "고정 구조" in result

    def test_generate_excludes_unrelated_adr_rationale(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "0010-structure.md").write_text(
            "# ADR-0010: 구조 강제\n\n- **상태**: Accepted\n\n"
            "## 결정\n\n외부 프로젝트의 고정 구조를 강제한다.\n",
            encoding="utf-8",
        )
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch("harness.review.pr_body.get_changed_files", return_value=[]):
            manager = self._make_manager(tmp_path)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager, summary="완전히무관한주제zzz")
        assert "## ADR Rationale" in result
        assert "ADR-0010" not in result
        assert "변경과 직접 관련된 ADR이 없습니다" in result

    def test_generate_includes_related_artifacts(self, tmp_path: Path) -> None:
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch("harness.review.pr_body.get_changed_files", return_value=[]):
            manager = self._make_manager(tmp_path)
            manager.save("design-intent.md", "# Design\nsome content")
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager)
        assert "## Related Artifacts" in result
        assert "design-intent.md" in result

    def test_generate_uses_design_intent_as_summary(self, tmp_path: Path) -> None:
        design_md = "# Design Intent\n**스프린트**: 1\n## 작업 개요\n\n인증 모듈 구현\n\n## 핵심 설계 결정\n"
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch("harness.review.pr_body.get_changed_files", return_value=[]):
            manager = self._make_manager(tmp_path)
            manager.save("design-intent.md", design_md)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager)
        assert "인증 모듈 구현" in result

    def test_generate_includes_diff_stat_when_present(self, tmp_path: Path) -> None:
        diff_stat = " harness/foo.py | 10 +++++"
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=diff_stat), \
             patch("harness.review.pr_body.get_changed_files", return_value=[]):
            manager = self._make_manager(tmp_path)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager)
        assert "Diff Summary" in result
        assert "harness/foo.py" in result

    def test_generate_includes_quality_guide(self, tmp_path: Path) -> None:
        guide = "## 평가 기준\n\n### architecture\n\n- [ERROR] adr-001: ADR 기준"
        with patch("harness.review.pr_body.get_git_diff_stat", return_value=""), \
             patch("harness.review.pr_body.get_changed_files", return_value=[]):
            manager = self._make_manager(tmp_path)
            manager.save("code-quality-guide.md", guide)
            gen = PRBodyGenerator(tmp_path)
            result = gen.generate(manager)
        assert "Code Quality Guide" in result

    def test_extract_overview_returns_content(self) -> None:
        md = "# Design\n## 작업 개요\n\n인증 개선\n모듈 분리\n\n## 다음 섹션"
        result = PRBodyGenerator._extract_overview(md)
        assert "인증 개선" in result
        assert "모듈 분리" in result

    def test_merge_path_matches_keeps_same_filename_other_source(self) -> None:
        # 같은 파일명이라도 소스가 다르면 외부 ADR이 누락되지 않아야 한다.
        local = {
            "filename": "0010-structure.md", "source": "",
            "affected_paths": "harness/context/",
        }
        external = {
            "filename": "0010-structure.md", "source": "/ext/adr",
            "affected_paths": "harness/context/",
        }
        merged = PRBodyGenerator._merge_path_matches(
            [local], [local, external], ["harness/context/foo.py"]
        )
        assert external in merged
        assert len(merged) == 2
