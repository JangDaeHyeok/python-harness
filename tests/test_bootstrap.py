"""harness/bootstrap 패키지 단위 테스트."""

from __future__ import annotations

import datetime as _dt
import json as _json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import yaml

from harness.bootstrap import (
    BootstrapInitializer,
    TargetKind,
    derive_package_name,
    derive_project_name,
)
from harness.bootstrap.initializer import (
    ALL_TARGETS,
    _validate_convention_yaml,
    _validate_markdown,
    _validate_policy_yaml,
    _validate_structure_yaml,
    relative_path_for,
)
from harness.bootstrap.templates import (
    TemplateContext,
    render_adr,
    render_coderabbit_config,
    render_convention,
    render_policy,
    render_structure,
)
from harness.sensors.computational.structure_test import StructureAnalyzer

_SAFE_PIP_ALLOW = {
    "Bash(pip install -e .)",
    'Bash(pip install -e ".[dev]")',
    "Bash(pip3 install -e .)",
    'Bash(pip3 install -e ".[dev]")',
    "Bash(pip install --upgrade pip)",
    "Bash(pip3 install --upgrade pip)",
}

_SAFE_GH_ALLOW = {
    "Bash(gh pr view *)",
    "Bash(gh pr list *)",
    "Bash(gh pr diff *)",
    "Bash(gh pr status *)",
    "Bash(gh pr checks *)",
    "Bash(gh pr comment *)",
    "Bash(gh pr create *)",
}

_GITHUB_WRITE_CONFIRM_DENY = {
    "Bash(python scripts/auto_pr_pipeline.py *--confirm-github-writes*)",
    "Bash(python3 scripts/auto_pr_pipeline.py *--confirm-github-writes*)",
    "Bash(python scripts/run_harness.py *--pr-confirm-github-writes*)",
    "Bash(python3 scripts/run_harness.py *--pr-confirm-github-writes*)",
}


def _assert_claude_settings_allow_is_narrow(allow: list[str]) -> None:
    """Claude Code 팀 공유 allow 목록이 넓은 권한을 열지 않는지 검증한다."""
    assert "Bash(pip install *)" not in allow
    assert "Bash(pip3 install *)" not in allow
    assert "Bash(.venv/bin/pip install *)" not in allow
    assert "Bash(gh pr *)" not in allow
    assert "Bash(gh api *)" not in allow
    assert "Bash(gh api repos/*)" not in allow

    missing_pip = _SAFE_PIP_ALLOW - set(allow)
    assert not missing_pip, f"누락된 pip allow 패턴: {missing_pip}"

    missing_gh = _SAFE_GH_ALLOW - set(allow)
    assert not missing_gh, f"누락된 gh allow 패턴: {missing_gh}"

    for forbidden in ("gh pr merge", "gh pr close", "gh pr reopen", "gh pr edit"):
        for entry in allow:
            assert forbidden not in entry, (
                f"destructive gh 서브명령이 allow에 포함됨: {entry}"
            )


def _assert_github_write_confirm_requires_permission(deny: list[str]) -> None:
    missing = _GITHUB_WRITE_CONFIRM_DENY - set(deny)
    assert not missing, f"GitHub 쓰기 확인 플래그 deny 누락: {missing}"


class TestRepoClaudeSettings:
    def test_committed_team_settings_keep_permissions_narrow(self) -> None:
        """실제 커밋되는 .claude/settings.json도 템플릿과 같은 보안 정책을 따라야 한다."""
        repo_root = Path(__file__).resolve().parents[1]
        settings_path = repo_root / ".claude/settings.json"

        loaded = _json.loads(settings_path.read_text(encoding="utf-8"))
        allow: list[str] = loaded["permissions"]["allow"]
        deny: list[str] = loaded["permissions"]["deny"]

        _assert_claude_settings_allow_is_narrow(allow)
        _assert_github_write_confirm_requires_permission(deny)


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
        assert rule["severity"] == "error"

    def test_render_structure_no_print_debug_fails_on_print(self, tmp_path: Path) -> None:
        """생성 템플릿의 print 금지 규칙은 구조 검사를 실패시켜야 한다."""
        ctx = TemplateContext(project_name="x", intent_summary="y")
        (tmp_path / "harness_structure.yaml").write_text(
            render_structure(ctx), encoding="utf-8"
        )
        (tmp_path / "CLAUDE.md").write_text("# x\n", encoding="utf-8")
        adr_path = tmp_path / "docs/adr/0001-initial-architecture.md"
        adr_path.parent.mkdir(parents=True)
        adr_path.write_text("# ADR\n", encoding="utf-8")
        convention_path = tmp_path / "docs/code-convention.yaml"
        convention_path.write_text("conventions: []\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("print('debug')\n", encoding="utf-8")

        result = StructureAnalyzer(str(tmp_path)).analyze()

        assert not result.passed
        assert any(
            v.rule_name == "no_print_debug" and v.severity == "error"
            for v in result.violations
        )

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
        assert loaded["project"]["package"] == "harness"
        assert "required_checks" in loaded["policies"]
        assert "ruff" in loaded["policies"]["required_checks"]

    def test_render_policy_yaml_includes_package(self) -> None:
        ctx = TemplateContext(project_name="my-svc", package="my_svc", intent_summary="y")
        loaded = yaml.safe_load(render_policy(ctx))
        assert loaded["project"]["package"] == "my_svc"

    def test_render_policy_yaml_includes_coderabbit_review_tool_flag(self) -> None:
        ctx = TemplateContext(project_name="my-svc", intent_summary="y")
        loaded = yaml.safe_load(render_policy(ctx))
        assert loaded["policies"]["review_tools"]["coderabbit"] is False

    def test_render_coderabbit_config_is_parseable(self) -> None:
        ctx = TemplateContext(project_name="my-svc", intent_summary="y")
        loaded = yaml.safe_load(render_coderabbit_config(ctx))
        assert loaded["language"] == "ko-KR"
        assert loaded["reviews"]["auto_review"]["enabled"] is True
        assert "CLAUDE.md" in loaded["knowledge_base"]["code_guidelines"]["filePatterns"]


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


class TestDerivePackageName:
    def test_hyphenated_project_name(self) -> None:
        assert derive_package_name("billing-api") == "billing_api"

    def test_digit_prefix(self) -> None:
        assert derive_package_name("2026-api") == "pkg_2026_api"


class TestBootstrapInitializerOffline:
    def test_creates_all_targets_when_missing(self, tmp_path: Path) -> None:
        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="사내 청구 자동화",
            offline=True,
        )
        result = initializer.run()

        # CLAUDE_CONFIG는 settings.json + sidecar hook 2개의 plan을 emit한다.
        assert result.created_count == len(ALL_TARGETS) + 1
        assert result.skipped_count == 0
        for kind in ALL_TARGETS:
            assert (tmp_path / relative_path_for(kind)).exists()
        assert (tmp_path / ".claude/hooks/post_session_checks.sh").exists()

        loaded = yaml.safe_load(
            (tmp_path / relative_path_for(TargetKind.POLICY)).read_text(encoding="utf-8")
        )
        assert loaded["project"]["package"] == tmp_path.name.replace("-", "_")

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

    def test_coderabbit_is_optional_target(self, tmp_path: Path) -> None:
        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="GitHub 리뷰 자동화",
            offline=True,
            targets=[TargetKind.CODERABBIT],
        )
        result = initializer.run()

        assert result.created_count == 1
        target = tmp_path / relative_path_for(TargetKind.CODERABBIT)
        assert target.exists()
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded["reviews"]["auto_review"]["enabled"] is True

    def test_existing_policy_is_patched_when_coderabbit_added(
        self, tmp_path: Path
    ) -> None:
        """기존 정책 파일이 있어도 --with-coderabbit 시 플래그가 true로 동기화된다."""
        # 1) 정책 파일을 먼저 만든다 (coderabbit: false 상태)
        BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=True,
            targets=[TargetKind.POLICY],
        ).run()

        policy_path = tmp_path / relative_path_for(TargetKind.POLICY)
        original = policy_path.read_text(encoding="utf-8")
        assert "coderabbit: false" in original
        assert "# 이 프로젝트의 메인 패키지 디렉토리명. 필수." in original

        # 2) --with-coderabbit (force 없이) 재실행
        result = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=True,
            targets=[TargetKind.CODERABBIT, TargetKind.POLICY],
        ).run()

        patched = policy_path.read_text(encoding="utf-8")
        assert "coderabbit: true" in patched
        # 주석은 보존되어야 한다
        assert "# 이 프로젝트의 메인 패키지 디렉토리명. 필수." in patched

        patch_plans = [p for p in result.plans if p.source == "patch"]
        assert len(patch_plans) == 1
        assert patch_plans[0].kind is TargetKind.POLICY
        assert patch_plans[0].existed_before is True

    def test_existing_policy_patch_is_idempotent(self, tmp_path: Path) -> None:
        """이미 true인 정책에 대해선 patch plan이 추가되지 않는다."""
        BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=True,
            targets=[TargetKind.POLICY, TargetKind.CODERABBIT],
        ).run()
        policy_path = tmp_path / relative_path_for(TargetKind.POLICY)
        before = policy_path.read_text(encoding="utf-8")
        assert "coderabbit: true" in before

        result = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=True,
            targets=[TargetKind.CODERABBIT],
        ).run()
        after = policy_path.read_text(encoding="utf-8")
        assert after == before
        assert not any(p.source == "patch" for p in result.plans)

    def test_dry_run_does_not_patch_existing_policy(self, tmp_path: Path) -> None:
        """dry-run에서는 정책 파일이 실제로 바뀌지 않고 plan만 보고된다."""
        BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=True,
            targets=[TargetKind.POLICY],
        ).run()
        policy_path = tmp_path / relative_path_for(TargetKind.POLICY)
        before = policy_path.read_text(encoding="utf-8")
        assert "coderabbit: false" in before

        result = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=True,
            dry_run=True,
            targets=[TargetKind.CODERABBIT],
        ).run()
        after = policy_path.read_text(encoding="utf-8")
        assert after == before  # disk 변경 없음
        patch_plans = [p for p in result.plans if p.source == "patch"]
        assert len(patch_plans) == 1
        assert patch_plans[0].kind is TargetKind.POLICY

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

    def test_claude_config_target_emits_valid_settings_json(
        self, tmp_path: Path
    ) -> None:
        """`.claude/settings.json`이 유효한 JSON으로 기록되고 핵심 키를 포함해야 한다."""
        import json as _json

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="플러그인 패키징 테스트",
            offline=True,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        result = initializer.run()

        plan = result.plans[0]
        assert plan.kind == TargetKind.CLAUDE_CONFIG
        assert plan.source == "template"

        settings_path = tmp_path / relative_path_for(TargetKind.CLAUDE_CONFIG)
        assert settings_path.exists()
        loaded = _json.loads(settings_path.read_text(encoding="utf-8"))
        assert "permissions" in loaded
        assert "hooks" in loaded
        assert isinstance(loaded["permissions"].get("allow"), list)
        assert isinstance(loaded["permissions"].get("deny"), list)
        deny = loaded["permissions"]["deny"]
        assert "Read(./.harness/tasks/**)" not in deny
        assert "Read(./.harness/review-artifacts/**)" not in deny
        _assert_github_write_confirm_requires_permission(deny)
        stop_hooks = loaded["hooks"]["Stop"][0]["hooks"]
        assert (
            stop_hooks[0]["command"]
            == '"${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/post_session_checks.sh"'
        )

        hook_path = tmp_path / ".claude/hooks/post_session_checks.sh"
        assert hook_path.exists()
        hook_text = hook_path.read_text(encoding="utf-8")
        assert "scripts/check_structure.py not found; skipping structure" in hook_text
        assert "pytest -q" in hook_text
        assert hook_path.stat().st_mode & 0o111

    def test_claude_config_fresh_path_emits_separate_sidecar_plan(
        self, tmp_path: Path
    ) -> None:
        """fresh CLAUDE_CONFIG 경로도 settings.json + sidecar hook을 각각 별도 plan으로
        보고해서, 요약 출력이 repair 경로와 비대칭이 되지 않아야 한다.
        """
        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="plan 비대칭 회귀 보호",
            offline=True,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        result = initializer.run()

        settings_path = tmp_path / relative_path_for(TargetKind.CLAUDE_CONFIG)
        hook_path = tmp_path / ".claude/hooks/post_session_checks.sh"

        # CLAUDE_CONFIG 한 대상에서 plan 2개(main + sidecar)가 나와야 한다.
        config_plans = [p for p in result.plans if p.kind == TargetKind.CLAUDE_CONFIG]
        assert len(config_plans) == 2

        settings_plan = next(p for p in config_plans if p.target_path == settings_path)
        hook_plan = next(p for p in config_plans if p.target_path == hook_path)
        assert settings_plan.status == "created"
        assert hook_plan.status == "created"
        assert settings_plan.existed_before is False
        assert hook_plan.existed_before is False

        # 요약 출력에도 hook 파일이 등장해야 한다.
        joined_summary = "\n".join(result.summary_lines())
        assert ".claude/hooks/post_session_checks.sh" in joined_summary
        assert ".claude/settings.json" in joined_summary

    def test_claude_config_repairs_missing_sidecar_hook(
        self, tmp_path: Path
    ) -> None:
        """settings.json이 있어도 누락된 Stop hook은 다시 생성해야 한다."""
        settings_path = tmp_path / relative_path_for(TargetKind.CLAUDE_CONFIG)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text('{"hooks": {}}\n', encoding="utf-8")

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="팀 셋업",
            offline=True,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        result = initializer.run()

        hook_path = tmp_path / ".claude/hooks/post_session_checks.sh"
        assert hook_path.exists()
        assert hook_path.stat().st_mode & 0o111
        assert settings_path.read_text(encoding="utf-8") == '{"hooks": {}}\n'

        hook_plan = next(p for p in result.plans if p.target_path == hook_path)
        settings_plan = next(p for p in result.plans if p.target_path == settings_path)
        assert hook_plan.status == "created"
        assert settings_plan.status == "skipped"

    def test_claude_config_skips_llm_customization(self, tmp_path: Path) -> None:
        """LLM 클라이언트가 있어도 CLAUDE_CONFIG는 호출 자체가 일어나면 안 된다."""
        client = MagicMock()

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=False,
            client=client,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        result = initializer.run()

        client.create_message.assert_not_called()
        assert result.plans[0].source == "template"

    def test_claude_config_force_overwrites_existing_settings(
        self, tmp_path: Path
    ) -> None:
        """--force 시 기존 settings.json은 템플릿으로 교체되고 sidecar 훅도 함께 생긴다."""
        import json as _json

        settings_path = tmp_path / relative_path_for(TargetKind.CLAUDE_CONFIG)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_body = '{"_legacy": true}\n'
        settings_path.write_text(legacy_body, encoding="utf-8")

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="force 재배포",
            offline=True,
            force=True,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        result = initializer.run()

        # 기존 본문이 사라지고 유효한 JSON 템플릿으로 교체되어야 한다.
        new_text = settings_path.read_text(encoding="utf-8")
        assert new_text != legacy_body
        loaded = _json.loads(new_text)
        assert "permissions" in loaded and "hooks" in loaded

        hook_path = tmp_path / ".claude/hooks/post_session_checks.sh"
        assert hook_path.exists()
        assert hook_path.stat().st_mode & 0o111

        settings_plan = next(
            p for p in result.plans if p.target_path == settings_path
        )
        assert settings_plan.status == "updated"
        assert settings_plan.source == "template"

    def test_claude_config_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        """dry_run=True 일 때 settings.json·sidecar 모두 디스크에 만들지 않는다."""
        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="dry-run 검증",
            offline=True,
            dry_run=True,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        result = initializer.run()

        settings_path = tmp_path / relative_path_for(TargetKind.CLAUDE_CONFIG)
        hook_path = tmp_path / ".claude/hooks/post_session_checks.sh"
        assert not settings_path.exists()
        assert not hook_path.exists()

        # plan 상에는 created로 잡혀야 한다 (실제 쓰기만 보류된 상태).
        plan = result.plans[0]
        assert plan.kind == TargetKind.CLAUDE_CONFIG
        assert plan.status == "created"
        assert "[DRY-RUN]" in result.summary_lines()[0]

    def test_claude_config_repair_dry_run_does_not_write_sidecar(
        self, tmp_path: Path
    ) -> None:
        """기존 settings.json 보유 + dry_run 일 때 sidecar 복구도 디스크 변경 없음."""
        settings_path = tmp_path / relative_path_for(TargetKind.CLAUDE_CONFIG)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        existing = '{"hooks": {}}\n'
        settings_path.write_text(existing, encoding="utf-8")

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="복구 시나리오 dry-run",
            offline=True,
            dry_run=True,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        result = initializer.run()

        hook_path = tmp_path / ".claude/hooks/post_session_checks.sh"
        assert not hook_path.exists()
        # 기존 settings.json 도 그대로 유지.
        assert settings_path.read_text(encoding="utf-8") == existing

        # 그래도 복구 plan 항목은 잡혀 있어야 한다.
        hook_plan = next(p for p in result.plans if p.target_path == hook_path)
        assert hook_plan.status == "created"
        assert hook_plan.will_write is True

    def test_post_session_checks_template_safety(self, tmp_path: Path) -> None:
        """렌더된 Stop 훅 본문에 안전 옵션·exclude·skip 메시지가 들어 있어야 하고,
        bash 구문 자체에도 에러가 없어야 한다.
        """
        import shutil
        import subprocess

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="훅 안전성 검증",
            offline=True,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        initializer.run()

        hook_path = tmp_path / ".claude/hooks/post_session_checks.sh"
        hook_text = hook_path.read_text(encoding="utf-8")

        # (a) pipefail 활성화
        assert "set -uo pipefail" in hook_text
        # (b) mypy 가 venv·빌드 산출물·하네스 디렉터리를 제외
        assert "MYPY_EXCLUDE_REGEX=" in hook_text
        assert r"\.venv" in hook_text
        assert r"\.harness" in hook_text
        assert "build" in hook_text and "dist" in hook_text
        assert 'mypy --exclude "$MYPY_EXCLUDE_REGEX" .' in hook_text
        # (c) 사용자에게 보이는 skip 메시지가 도구별로 존재
        assert "ruff not installed; skipping" in hook_text
        assert "mypy not installed; skipping" in hook_text
        assert "pytest not installed; skipping" in hook_text
        assert "no Python files found; skipping mypy" in hook_text
        # CLAUDE_HOOK_SKIP 우회 경로도 보존
        assert "CLAUDE_HOOK_SKIP" in hook_text

        # 실행 가능한 bash 가 있으면 -n 으로 문법 검증.
        bash = shutil.which("bash")
        if bash is not None:
            proc = subprocess.run(
                [bash, "-n", str(hook_path)],
                capture_output=True,
                text=True,
            )
            assert proc.returncode == 0, (
                f"hook 스크립트 bash 구문 오류:\n{proc.stderr}"
            )

    def test_claude_settings_template_omits_broad_pip_install(
        self, tmp_path: Path
    ) -> None:
        """settings.json allow 목록은 좁힌 pip 패턴만 허용하고 와일드카드는 금지한다."""
        import json as _json

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="권한 좁히기 회귀 보호",
            offline=True,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        initializer.run()

        settings_path = tmp_path / relative_path_for(TargetKind.CLAUDE_CONFIG)
        loaded = _json.loads(settings_path.read_text(encoding="utf-8"))
        allow: list[str] = loaded["permissions"]["allow"]

        # 광범위 pip install 와일드카드는 절대 들어가면 안 된다.
        assert "Bash(pip install *)" not in allow
        assert "Bash(pip3 install *)" not in allow

        # 좁힌 패턴은 모두 존재해야 한다.
        expected_subset = {
            "Bash(pip install -e .)",
            'Bash(pip install -e ".[dev]")',
            "Bash(pip3 install -e .)",
            'Bash(pip3 install -e ".[dev]")',
            "Bash(pip install --upgrade pip)",
            "Bash(pip3 install --upgrade pip)",
        }
        missing = expected_subset - set(allow)
        assert not missing, f"누락된 allow 패턴: {missing}"

    def test_claude_settings_template_narrows_gh_subcommands(
        self, tmp_path: Path
    ) -> None:
        """settings.json allow 목록의 gh 패턴이 destructive 서브명령(merge/close/edit) 와
        임의 `gh api` 호출을 포함하지 않아야 한다.
        """
        import json as _json

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="gh 권한 좁히기 회귀 보호",
            offline=True,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        initializer.run()

        settings_path = tmp_path / relative_path_for(TargetKind.CLAUDE_CONFIG)
        loaded = _json.loads(settings_path.read_text(encoding="utf-8"))
        allow: list[str] = loaded["permissions"]["allow"]

        # 광범위 와일드카드는 절대 들어가면 안 된다.
        assert "Bash(gh pr *)" not in allow, (
            "gh pr 와일드카드는 destructive 머지·close·edit까지 허용하므로 금지."
        )
        assert "Bash(gh api *)" not in allow, (
            "gh api 와일드카드는 임의 GitHub REST/GraphQL 호출을 허용하므로 금지."
        )
        assert "Bash(gh api repos/*)" not in allow, (
            "gh api repos/*도 -X DELETE/PATCH 등으로 쓰기 요청이 가능하므로 "
            "팀 공유 allow에서는 금지."
        )

        # 안전한 read·write 패턴만 명시적으로 허용.
        expected_subset = {
            "Bash(gh pr view *)",
            "Bash(gh pr list *)",
            "Bash(gh pr diff *)",
            "Bash(gh pr status *)",
            "Bash(gh pr checks *)",
            "Bash(gh pr comment *)",
            "Bash(gh pr create *)",
        }
        missing = expected_subset - set(allow)
        assert not missing, f"누락된 gh allow 패턴: {missing}"

        # destructive 서브명령은 어떤 형태로도 명시 허용되면 안 된다.
        for forbidden in ("gh pr merge", "gh pr close", "gh pr reopen", "gh pr edit"):
            for entry in allow:
                assert forbidden not in entry, (
                    f"destructive gh 서브명령이 allow에 포함됨: {entry}"
                )

    def test_post_session_checks_pytest_exit_5_is_success(
        self, tmp_path: Path
    ) -> None:
        """Stop 훅이 pytest exit 5 (no tests collected)를 성공으로 간주해야 한다.

        fresh 프로젝트에서 `tests/` 디렉터리만 만들어진 직후 흔히 발생하는 상황을 대비한
        회귀 보호 테스트.
        """
        import shutil
        import subprocess

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="pytest exit 5 가드 회귀 보호",
            offline=True,
            targets=[TargetKind.CLAUDE_CONFIG],
        )
        initializer.run()

        hook_path = tmp_path / ".claude/hooks/post_session_checks.sh"
        hook_text = hook_path.read_text(encoding="utf-8")

        # 가드 의도가 본문에 드러나야 한다.
        assert "pytest collected no tests" in hook_text
        assert 'pytest_status' in hook_text

        # 실제 bash 가 있으면 fake pytest(exit 5) 와 함께 실행해 봄.
        bash = shutil.which("bash")
        if bash is None:
            return

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        fake_pytest = fake_bin / "pytest"
        fake_pytest.write_text("#!/usr/bin/env bash\nexit 5\n", encoding="utf-8")
        fake_pytest.chmod(0o755)

        # check_structure.py·ruff·mypy 는 모두 미설치·미존재 경로로 건너뛰게 한다.
        (tmp_path / "tests").mkdir()

        env = {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "HOME": str(tmp_path),
        }
        proc = subprocess.run(
            [bash, str(hook_path)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert proc.returncode == 0, (
            f"pytest exit 5는 성공 처리되어야 함. stdout=\n{proc.stdout}\n"
            f"stderr=\n{proc.stderr}"
        )
        assert "pytest collected no tests" in proc.stdout


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


class TestValidateConventionYaml:
    def test_accepts_valid_conventions(self) -> None:
        text = "conventions:\n  - id: x\n    description: y\n"
        assert _validate_convention_yaml(text) is True

    def test_rejects_missing_conventions_key(self) -> None:
        assert _validate_convention_yaml("foo: bar\n") is False

    def test_rejects_empty_conventions_list(self) -> None:
        assert _validate_convention_yaml("conventions: []\n") is False

    def test_rejects_non_list_conventions(self) -> None:
        assert _validate_convention_yaml("conventions: not-a-list\n") is False

    def test_rejects_invalid_yaml(self) -> None:
        assert _validate_convention_yaml("not: valid: yaml: [") is False


class TestValidateStructureYaml:
    def test_accepts_valid_rules(self) -> None:
        text = "rules:\n  - name: x\n    type: required_files\n"
        assert _validate_structure_yaml(text) is True

    def test_rejects_missing_rules_key(self) -> None:
        assert _validate_structure_yaml("foo: bar\n") is False

    def test_rejects_empty_rules_list(self) -> None:
        assert _validate_structure_yaml("rules: []\n") is False

    def test_rejects_non_dict(self) -> None:
        assert _validate_structure_yaml("- item\n") is False


class TestValidatePolicyYaml:
    def test_accepts_valid_policy(self) -> None:
        text = "project:\n  name: x\n  package: x\npolicies:\n  required_checks: [ruff]\n"
        assert _validate_policy_yaml(text) is True

    def test_rejects_missing_project(self) -> None:
        assert _validate_policy_yaml("policies:\n  required_checks: []\n") is False

    def test_rejects_missing_package(self) -> None:
        text = "project:\n  name: x\npolicies:\n  required_checks: [ruff]\n"
        assert _validate_policy_yaml(text) is False

    def test_rejects_missing_policies(self) -> None:
        assert _validate_policy_yaml("project:\n  name: x\n  package: x\n") is False

    def test_rejects_non_dict_project(self) -> None:
        text = "project: not-a-dict\npolicies:\n  x: y\n"
        assert _validate_policy_yaml(text) is False

    def test_rejects_non_dict_policies(self) -> None:
        text = "project:\n  name: x\n  package: x\npolicies: not-a-dict\n"
        assert _validate_policy_yaml(text) is False


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
            "```yaml\nproject:\n  name: fenced\n  package: fenced\npolicies:\n  required_checks: [ruff]\n```"
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

    def test_llm_structure_falls_back_on_missing_rules(self, tmp_path: Path) -> None:
        """rules 키 없는 YAML이 오면 템플릿으로 폴백해야 한다."""
        client = MagicMock()
        client.create_message.return_value = self._make_response("foo: bar\n")

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
        loaded = yaml.safe_load(
            (tmp_path / relative_path_for(TargetKind.STRUCTURE)).read_text()
        )
        assert isinstance(loaded["rules"], list)
        assert len(loaded["rules"]) > 0

    def test_llm_convention_falls_back_on_missing_conventions(
        self, tmp_path: Path
    ) -> None:
        """conventions 키 없는 YAML이 오면 템플릿으로 폴백해야 한다."""
        client = MagicMock()
        client.create_message.return_value = self._make_response("style: pep8\n")

        initializer = BootstrapInitializer(
            project_dir=tmp_path,
            prompt="x",
            offline=False,
            client=client,
            targets=[TargetKind.CONVENTION],
        )
        result = initializer.run()

        plan = result.plans[0]
        assert plan.source == "template"
        loaded = yaml.safe_load(
            (tmp_path / relative_path_for(TargetKind.CONVENTION)).read_text()
        )
        assert isinstance(loaded["conventions"], list)
        assert len(loaded["conventions"]) > 0

    def test_llm_policy_falls_back_on_missing_policies(self, tmp_path: Path) -> None:
        """policies 키 없는 YAML이 오면 템플릿으로 폴백해야 한다."""
        client = MagicMock()
        client.create_message.return_value = self._make_response(
            "project:\n  name: x\n"
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
        assert plan.source == "template"
        loaded = yaml.safe_load(
            (tmp_path / relative_path_for(TargetKind.POLICY)).read_text()
        )
        assert isinstance(loaded["project"], dict)
        assert isinstance(loaded["policies"], dict)
