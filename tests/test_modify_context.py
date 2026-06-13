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

    def test_to_markdown_includes_relevant_adr_bodies(self) -> None:
        ctx = ModifyContext(relevant_adrs=[{
            "filename": "0010.md",
            "title": "구조 강제",
            "status": "accepted",
            "content": "# ADR-0010\n\n## 결정\n\n고정 구조를 강제한다.\n",
        }])
        md = ctx.to_markdown()
        assert "관련된 ADR 핵심 본문" in md
        assert "고정 구조를 강제한다" in md

    def test_to_markdown_includes_policy(self) -> None:
        ctx = ModifyContext(project_policy="project:\n  name: test")
        md = ctx.to_markdown()
        assert "프로젝트 정책" in md

    def test_to_markdown_includes_python_project_summary(self) -> None:
        ctx = ModifyContext(python_project_summary="- package_manager: uv")
        md = ctx.to_markdown()
        assert "Python 프로젝트 감지 요약" in md
        assert "package_manager: uv" in md


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

    def test_collect_with_external_adr_sources(self, tmp_path: Path) -> None:
        """외부 ADR 소스가 정책에 있으면 내부 ADR과 함께 로드된다."""
        from harness.context.project_policy import ProjectPolicy

        (tmp_path / "docs" / "adr").mkdir(parents=True)
        (tmp_path / "docs" / "adr" / "0001.md").write_text(
            "# Internal ADR\nstatus: accepted\n", encoding="utf-8",
        )

        ext_dir = tmp_path / "external" / "adr"
        ext_dir.mkdir(parents=True)
        (ext_dir / "0001-ext.md").write_text(
            "# External ADR\nstatus: accepted\n", encoding="utf-8",
        )

        policy = ProjectPolicy(external_adr_sources=[str(ext_dir)])
        collector = ModifyContextCollector(tmp_path)
        with (
            patch.object(collector, "_run_git", return_value="main"),
            patch.object(collector, "_run_cmd", return_value=None),
        ):
            ctx = collector.collect(policy=policy)

        assert len(ctx.adrs) == 2
        titles = [a["title"] for a in ctx.adrs]
        assert "Internal ADR" in titles
        assert "External ADR" in titles

    def test_collect_selects_relevant_adr_bodies(self, tmp_path: Path) -> None:
        """task_description가 주어지면 관련 ADR 본문이 선별된다."""
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "0010-structure.md").write_text(
            "# ADR-0010: 구조 강제\n\n- **상태**: Accepted\n\n"
            "## 결정\n\n고정 구조를 강제한다.\n",
            encoding="utf-8",
        )
        (adr_dir / "0007-guide.md").write_text(
            "# ADR-0007: 가이드\n\n- **상태**: Accepted\n\n"
            "## 결정\n\n무관한 결정.\n",
            encoding="utf-8",
        )
        collector = ModifyContextCollector(tmp_path)
        with (
            patch.object(collector, "_run_git", return_value="main"),
            patch.object(collector, "_run_cmd", return_value=None),
        ):
            ctx = collector.collect(task_description="구조 강제 수정")

        assert any("0010" in a["filename"] for a in ctx.relevant_adrs)
        md = ctx.to_markdown()
        assert "관련된 ADR 핵심 본문" in md

    def test_collect_without_task_description_no_relevant_adrs(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "0010.md").write_text(
            "# ADR-0010\n\n- **상태**: Accepted\n", encoding="utf-8",
        )
        collector = ModifyContextCollector(tmp_path)
        with (
            patch.object(collector, "_run_git", return_value="main"),
            patch.object(collector, "_run_cmd", return_value=None),
        ):
            ctx = collector.collect()
        assert ctx.relevant_adrs == []

    def test_collect_with_missing_external_adr_source(self, tmp_path: Path) -> None:
        """외부 ADR 경로가 없으면 무시하고 내부 ADR만 로드한다."""
        from harness.context.project_policy import ProjectPolicy

        (tmp_path / "docs" / "adr").mkdir(parents=True)
        (tmp_path / "docs" / "adr" / "0001.md").write_text(
            "# Internal ADR\nstatus: accepted\n", encoding="utf-8",
        )

        policy = ProjectPolicy(external_adr_sources=[str(tmp_path / "nonexistent")])
        collector = ModifyContextCollector(tmp_path)
        with (
            patch.object(collector, "_run_git", return_value="main"),
            patch.object(collector, "_run_cmd", return_value=None),
        ):
            ctx = collector.collect(policy=policy)

        assert len(ctx.adrs) == 1
        assert ctx.adrs[0]["title"] == "Internal ADR"

    def test_to_markdown_shows_external_source_tag(self) -> None:
        ctx = ModifyContext(adrs=[
            {"filename": "0001.md", "title": "Local", "status": "accepted"},
            {"filename": "0001.md", "title": "External", "status": "accepted", "source": "/ext/adr"},
        ])
        md = ctx.to_markdown()
        assert "(외부: /ext/adr)" in md
        assert md.count("(외부:") == 1

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

    def test_recent_test_summary_uses_policy_commands(self, tmp_path: Path) -> None:
        """검증 요약은 정책의 lint/type 명령을 실행한다."""
        from harness.context.project_policy import ProjectPolicy, ValidationCommands

        policy = ProjectPolicy(
            commands=ValidationCommands(lint="ruff check .", type="mypy src/app")
        )
        collector = ModifyContextCollector(tmp_path)
        with patch.object(collector, "_run_cmd", return_value="") as run_cmd:
            collector._get_recent_test_summary(policy)

        called = {args for args, _ in run_cmd.call_args_list}
        assert ("ruff", "check", ".") in called
        assert ("mypy", "src/app") in called

    def test_recent_test_summary_defaults_without_policy(self, tmp_path: Path) -> None:
        """정책이 없으면 기본 ruff/mypy 명령으로 폴백한다."""
        collector = ModifyContextCollector(tmp_path)
        with patch.object(collector, "_run_cmd", return_value="") as run_cmd:
            collector._get_recent_test_summary(None)

        called = {args for args, _ in run_cmd.call_args_list}
        assert ("ruff", "check", ".") in called
        assert ("mypy", "harness") in called

    def test_recent_test_summary_skips_disallowed_command(self, tmp_path: Path) -> None:
        """allowlist 밖 명령은 실행되지 않고 안전하게 생략된다(None)."""
        from harness.context.project_policy import ProjectPolicy, ValidationCommands

        policy = ProjectPolicy(
            commands=ValidationCommands(lint="rm -rf .", type="")
        )
        collector = ModifyContextCollector(tmp_path)
        summary = collector._get_recent_test_summary(policy)

        assert "Lint" not in summary
        assert summary == ""

    def test_collect_python_project_summary(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "\n".join([
                "[project]",
                'dependencies = ["pydantic>=2", "httpx"]',
                "[project.optional-dependencies]",
                'dev = ["pytest"]',
            ]),
            encoding="utf-8",
        )
        (tmp_path / "uv.lock").write_text("", encoding="utf-8")
        (tmp_path / "src" / "demo").mkdir(parents=True)
        (tmp_path / "src" / "demo" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "src" / "demo" / "cli.py").write_text(
            "import argparse\nimport typer\n", encoding="utf-8"
        )

        collector = ModifyContextCollector(tmp_path)
        with (
            patch.object(
                collector,
                "_run_git",
                side_effect=lambda *args: "main" if args == ("branch", "--show-current") else "init\nadd cli",
            ),
            patch.object(collector, "_run_cmd", return_value=None),
        ):
            ctx = collector.collect()

        assert "pyproject.toml" in ctx.python_project_summary
        assert "uv.lock" in ctx.python_project_summary
        assert "package_manager: uv" in ctx.python_project_summary
        assert "layout: src" in ctx.python_project_summary
        assert "pydantic v2" in ctx.python_project_summary
        assert "httpx" in ctx.python_project_summary
        assert "typer" in ctx.python_project_summary
        assert "최근 커밋 메시지" in ctx.python_project_summary
