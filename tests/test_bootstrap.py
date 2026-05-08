"""harness/bootstrap 패키지 단위 테스트."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import yaml

from harness.bootstrap import (
    BootstrapInitializer,
    TargetKind,
    derive_project_name,
)
from harness.bootstrap.initializer import (
    ALL_TARGETS,
    _validate_markdown,
    relative_path_for,
)
from harness.bootstrap.templates import (
    TemplateContext,
    render_adr,
    render_convention,
    render_policy,
    render_structure,
)


class TestTemplates:
    def test_render_adr_substitutes_project_name(self) -> None:
        ctx = TemplateContext(project_name="my-app", intent_summary="API 게이트웨이")
        out = render_adr(ctx)
        assert "my-app" in out
        assert "API 게이트웨이" in out
        assert out.startswith("---")

    def test_render_convention_yaml_is_parseable(self) -> None:
        ctx = TemplateContext(project_name="x", intent_summary="y")
        loaded = yaml.safe_load(render_convention(ctx))
        assert isinstance(loaded, dict)
        assert "conventions" in loaded
        assert isinstance(loaded["conventions"], list)

    def test_render_structure_yaml_has_rules(self) -> None:
        ctx = TemplateContext(project_name="x", intent_summary="y")
        loaded = yaml.safe_load(render_structure(ctx))
        assert "rules" in loaded
        assert any(r.get("type") == "required_files" for r in loaded["rules"])

    def test_render_structure_no_print_debug_uses_default_directories(self) -> None:
        """no_print_debug 규칙이 directories를 비우지 않는지 확인.

        구조 분석기는 ``directories`` 키가 없을 때만 기본값 ``["."]``을 적용한다.
        ``directories: []`` 같은 빈 리스트가 들어가면 어떤 디렉터리도 검사하지 않는
        no-op 규칙이 되므로, 템플릿에서는 키 자체를 생략해야 한다.
        """
        ctx = TemplateContext(project_name="x", intent_summary="y")
        loaded = yaml.safe_load(render_structure(ctx))
        rule = next(r for r in loaded["rules"] if r["name"] == "no_print_debug")
        assert "directories" not in rule

    def test_render_adr_uses_today_date(self) -> None:
        """ADR 템플릿의 date 필드가 오늘 날짜로 채워지는지 확인."""
        ctx = TemplateContext(project_name="x", intent_summary="y")
        out = render_adr(ctx)
        today = _dt.date.today().isoformat()
        assert f"date: {today}" in out

    def test_render_adr_explicit_today_override(self) -> None:
        ctx = TemplateContext(project_name="x", intent_summary="y", today="2099-01-02")
        assert "date: 2099-01-02" in render_adr(ctx)

    def test_render_policy_yaml_has_required_keys(self) -> None:
        ctx = TemplateContext(project_name="my-svc", intent_summary="y", language="python")
        loaded = yaml.safe_load(render_policy(ctx))
        assert loaded["project"]["name"] == "my-svc"
        assert "required_checks" in loaded["policies"]
        assert "ruff" in loaded["policies"]["required_checks"]


class TestDeriveProjectName:
    def test_quoted_name_in_prompt(self, tmp_path: Path) -> None:
        assert derive_project_name("프로젝트 'billing-api'를 만들자", tmp_path) == "billing-api"

    def test_falls_back_to_directory_name(self, tmp_path: Path) -> None:
        target = tmp_path / "data-pipeline"
        target.mkdir()
        assert derive_project_name("어떤 자연어", target) == "data-pipeline"

    def test_sanitizes_directory_name(self, tmp_path: Path) -> None:
        target = tmp_path / "weird name!@#"
        target.mkdir()
        assert derive_project_name("", target) == "weird-name"

    def test_default_when_empty(self) -> None:
        assert derive_project_name("", Path(".")) != ""


class TestBootstrapInitializerOffline:
    def test_creates_all_targets_when_missing(self, tmp_path: Path) -> None:
        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="사내 청구 자동화",
            offline=True,
        )
        result = initializer.run()

        assert result.created_count == len(ALL_TARGETS)
        assert result.skipped_count == 0
        for kind in ALL_TARGETS:
            assert (tmp_path / relative_path_for(kind)).exists()

    def test_skips_existing_files_without_force(self, tmp_path: Path) -> None:
        target = tmp_path / relative_path_for(TargetKind.POLICY)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("existing: true\n", encoding="utf-8")

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=True,
        )
        result = initializer.run()

        policy_plan = next(p for p in result.plans if p.kind == TargetKind.POLICY)
        assert policy_plan.status == "skipped"
        assert target.read_text(encoding="utf-8") == "existing: true\n"

    def test_force_overwrites_existing(self, tmp_path: Path) -> None:
        target = tmp_path / relative_path_for(TargetKind.POLICY)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old\n", encoding="utf-8")

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="신규 정책",
            offline=True,
            force=True,
        )
        result = initializer.run()

        policy_plan = next(p for p in result.plans if p.kind == TargetKind.POLICY)
        assert policy_plan.status == "updated"
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded["project"]["name"]

    def test_only_filter(self, tmp_path: Path) -> None:
        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=True,
            targets=[TargetKind.ADR, TargetKind.POLICY],
        )
        result = initializer.run()

        assert {p.kind for p in result.plans} == {TargetKind.ADR, TargetKind.POLICY}
        assert (tmp_path / relative_path_for(TargetKind.ADR)).exists()
        assert not (tmp_path / relative_path_for(TargetKind.STRUCTURE)).exists()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=True,
            dry_run=True,
        )
        result = initializer.run()

        assert result.dry_run is True
        for kind in ALL_TARGETS:
            assert not (tmp_path / relative_path_for(kind)).exists()
        assert all(p.will_write for p in result.plans)

    def test_summary_lines_includes_status_tags(self, tmp_path: Path) -> None:
        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=True,
        )
        result = initializer.run()
        joined = "\n".join(result.summary_lines())
        assert "CREATED" in joined


class TestValidateMarkdown:
    def test_accepts_yaml_frontmatter_then_heading(self) -> None:
        text = "---\nstatus: accepted\n---\n\n# 제목\n\n본문\n"
        assert _validate_markdown(text) is True

    def test_accepts_simple_heading(self) -> None:
        assert _validate_markdown("# 제목\n본문") is True

    def test_rejects_empty(self) -> None:
        assert _validate_markdown("   \n") is False

    def test_rejects_text_without_heading(self) -> None:
        assert _validate_markdown("그냥 본문만 있고 헤딩이 없음") is False


class TestBootstrapInitializerLLM:
    def _make_response(self, text: str) -> Any:
        block = MagicMock()
        block.text = text
        response = MagicMock()
        response.content = [block]
        return response

    def test_llm_customization_used_when_valid(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.create_message.return_value = self._make_response(
            "rules:\n  - name: x\n    type: required_files\n    files: []\n"
        )

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="구조 강화",
            offline=False,
            client=client,
            targets=[TargetKind.STRUCTURE],
        )
        result = initializer.run()

        plan = result.plans[0]
        assert plan.source == "llm"
        assert "name: x" in (tmp_path / relative_path_for(TargetKind.STRUCTURE)).read_text()

    def test_llm_falls_back_on_invalid_yaml(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.create_message.return_value = self._make_response("not: valid: yaml: [")

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=False,
            client=client,
            targets=[TargetKind.STRUCTURE],
        )
        result = initializer.run()

        plan = result.plans[0]
        assert plan.source == "template"
        loaded = yaml.safe_load((tmp_path / relative_path_for(TargetKind.STRUCTURE)).read_text())
        assert "rules" in loaded

    def test_llm_falls_back_on_exception(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.create_message.side_effect = RuntimeError("network error")

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=False,
            client=client,
            targets=[TargetKind.ADR],
        )
        result = initializer.run()

        plan = result.plans[0]
        assert plan.source == "template"

    def test_llm_adr_with_frontmatter_passes_validation(self, tmp_path: Path) -> None:
        """ADR LLM 응답이 ``---`` frontmatter로 시작해도 검증을 통과해야 한다."""
        client = MagicMock()
        client.create_message.return_value = self._make_response(
            "---\nstatus: accepted\ndate: 2099-01-02\n---\n\n"
            "# ADR-0001: 제목\n\n## Context\n내용\n"
        )

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=False,
            client=client,
            targets=[TargetKind.ADR],
        )
        result = initializer.run()

        plan = result.plans[0]
        assert plan.source == "llm"
        body = (tmp_path / relative_path_for(TargetKind.ADR)).read_text()
        assert body.startswith("---")
        assert "ADR-0001" in body

    def test_llm_strips_code_fence(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.create_message.return_value = self._make_response(
            "```yaml\nproject:\n  name: fenced\nlanguage: python\n```"
        )

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=False,
            client=client,
            targets=[TargetKind.POLICY],
        )
        result = initializer.run()

        plan = result.plans[0]
        assert plan.source == "llm"
        loaded = yaml.safe_load((tmp_path / relative_path_for(TargetKind.POLICY)).read_text())
        assert loaded["project"]["name"] == "fenced"
