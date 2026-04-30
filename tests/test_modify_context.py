"""modify_context.py 단위 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from harness.context.modify_context import ModifyContext, ModifyContextCollector

if TYPE_CHECKING:
    from pathlib import Path


class TestModifyContext:
    def test_default_empty(self) -> None:
        ctx = ModifyContext()
        assert ctx.git_branch == ""
        assert ctx.changed_files == []
        assert ctx.adrs == []

    def test_to_markdown_minimal(self) -> None:
        ctx = ModifyContext(git_branch="main")
        md = ctx.to_markdown()
        assert "# 프로젝트 수정 컨텍스트" in md
        assert "`main`" in md

    def test_to_markdown_with_changed_files(self) -> None:
        ctx = ModifyContext(
            git_branch="feature/test",
            changed_files=["foo.py", "bar.py"],
        )
        md = ctx.to_markdown()
        assert "`foo.py`" in md
        assert "`bar.py`" in md

    def test_to_markdown_truncates_long_diff(self) -> None:
        ctx = ModifyContext(git_diff="x" * 6000)
        md = ctx.to_markdown()
        assert "[잘림: 원본 6000자, 표시 5000자]" in md

    def test_to_markdown_marks_truncated_code_convention(self) -> None:
        ctx = ModifyContext(code_convention="x" * 4000)
        md = ctx.to_markdown()
        assert "[잘림: 원본 4000자, 표시 3000자]" in md

    def test_to_markdown_includes_adrs(self) -> None:
        ctx = ModifyContext(adrs=[{
            "filename": "0001.md",
            "title": "Test ADR",
            "status": "accepted",
        }])
        md = ctx.to_markdown()
        assert "0001.md" in md
        assert "Test ADR" in md

    def test_to_markdown_includes_policy(self) -> None:
        ctx = ModifyContext(project_policy="project:\n  name: test")
        md = ctx.to_markdown()
        assert "프로젝트 정책" in md


class TestModifyContextCollector:
    def test_collect_with_mocked_git(self, tmp_path: Path) -> None:
        (tmp_path / "docs" / "adr").mkdir(parents=True)
        (tmp_path / "docs" / "adr" / "0001-test.md").write_text(
            "# Test ADR\nstatus: accepted\n", encoding="utf-8",
        )
        (tmp_path / "docs" / "code-convention.yaml").write_text(
            "conventions: []", encoding="utf-8",
        )
        (tmp_path / "harness_structure.yaml").write_text(
            "rules: []", encoding="utf-8",
        )

        collector = ModifyContextCollector(tmp_path)

        with (
            patch.object(collector, "_run_git", return_value="main"),
            patch.object(collector, "_run_cmd", return_value=None),
        ):
            ctx = collector.collect()

        assert ctx.git_branch == "main"
        assert ctx.code_convention == "conventions: []"
        assert ctx.structure_rules == "rules: []"
        assert len(ctx.adrs) == 1
        assert ctx.adrs[0]["title"] == "Test ADR"

    def test_collect_no_adr_dir(self, tmp_path: Path) -> None:
        collector = ModifyContextCollector(tmp_path)

        with (
            patch.object(collector, "_run_git", return_value=""),
            patch.object(collector, "_run_cmd", return_value=None),
        ):
            ctx = collector.collect()

        assert ctx.adrs == []
        assert ctx.git_branch == "unknown"

    def test_get_changed_files_parses_porcelain(self, tmp_path: Path) -> None:
        collector = ModifyContextCollector(tmp_path)

        with patch.object(
            collector, "_run_git", return_value=" M foo.py\n?? bar.py"
        ):
            files = collector._get_changed_files()

        assert "foo.py" in files
        assert "bar.py" in files

    def test_get_changed_files_empty(self, tmp_path: Path) -> None:
        collector = ModifyContextCollector(tmp_path)

        with patch.object(collector, "_run_git", return_value=""):
            files = collector._get_changed_files()

        assert files == []

    def test_collect_uses_policy_paths(self, tmp_path: Path) -> None:
        """ProjectPolicy의 경로 설정이 collect()에 실제로 반영된다."""
        from harness.context.project_policy import ProjectPolicy

        custom_conv = tmp_path / "custom" / "conv.yaml"
        custom_conv.parent.mkdir(parents=True)
        custom_conv.write_text("custom: true", encoding="utf-8")

        custom_adr_dir = tmp_path / "custom" / "adr"
        custom_adr_dir.mkdir(parents=True)
        (custom_adr_dir / "0001-test.md").write_text("# Custom ADR\nstatus: accepted\n", encoding="utf-8")

        custom_struct = tmp_path / "custom" / "rules.yaml"
        custom_struct.write_text("rules: []", encoding="utf-8")

        policy = ProjectPolicy(
            conventions_source="custom/conv.yaml",
            adr_directory="custom/adr",
            structure_source="custom/rules.yaml",
        )

        collector = ModifyContextCollector(tmp_path)
        with (
            patch.object(collector, "_run_git", return_value="main"),
            patch.object(collector, "_run_cmd", return_value=None),
        ):
            ctx = collector.collect(policy=policy)

        assert ctx.code_convention == "custom: true"
        assert len(ctx.adrs) == 1
        assert ctx.adrs[0]["title"] == "Custom ADR"
        assert ctx.structure_rules == "rules: []"

    def test_collect_without_policy_uses_defaults(self, tmp_path: Path) -> None:
        """policy=None이면 기본 경로(docs/code-convention.yaml 등)를 사용한다."""
        (tmp_path / "docs" / "code-convention.yaml").parent.mkdir(parents=True)
        (tmp_path / "docs" / "code-convention.yaml").write_text("default: true", encoding="utf-8")

        collector = ModifyContextCollector(tmp_path)
        with (
            patch.object(collector, "_run_git", return_value="main"),
            patch.object(collector, "_run_cmd", return_value=None),
        ):
            ctx = collector.collect()

        assert ctx.code_convention == "default: true"
