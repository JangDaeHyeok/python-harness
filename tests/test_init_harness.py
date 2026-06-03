"""scripts/init_harness.py CLI 옵션 연결 테스트."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from harness.bootstrap.initializer import ALL_TARGETS, TargetKind, relative_path_for
from scripts import init_harness


def test_main_creates_files_with_offline_mode(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    with patch.object(
        sys,
        "argv",
        [
            "init_harness.py",
            "--project-dir",
            str(project_dir),
            "--offline",
            "사내 인보이스 관리 도구",
        ],
    ):
        init_harness.main()

    for kind in ALL_TARGETS:
        assert (project_dir / relative_path_for(kind)).exists()


def test_main_only_filter_limits_targets(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    with patch.object(
        sys,
        "argv",
        [
            "init_harness.py",
            "--project-dir",
            str(project_dir),
            "--offline",
            "--only",
            "policy,adr",
            "x",
        ],
    ):
        init_harness.main()

    assert (project_dir / relative_path_for(TargetKind.POLICY)).exists()
    assert (project_dir / relative_path_for(TargetKind.ADR)).exists()
    assert not (project_dir / relative_path_for(TargetKind.STRUCTURE)).exists()


def test_main_with_coderabbit_creates_optional_config(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    with patch.object(
        sys,
        "argv",
        [
            "init_harness.py",
            "--project-dir",
            str(project_dir),
            "--offline",
            "--with-coderabbit",
            "x",
        ],
    ):
        init_harness.main()

    assert (project_dir / ".coderabbit.yaml").exists()
    policy = yaml.safe_load(
        (project_dir / relative_path_for(TargetKind.POLICY)).read_text(encoding="utf-8")
    )
    assert policy["policies"]["review_tools"]["coderabbit"] is True


def test_main_only_coderabbit_limits_to_optional_config(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    with patch.object(
        sys,
        "argv",
        [
            "init_harness.py",
            "--project-dir",
            str(project_dir),
            "--offline",
            "--only",
            "coderabbit",
            "x",
        ],
    ):
        init_harness.main()

    assert (project_dir / ".coderabbit.yaml").exists()
    assert not (project_dir / relative_path_for(TargetKind.POLICY)).exists()


def test_main_with_coderabbit_extends_only_filter(tmp_path: Path) -> None:
    """--with-coderabbit는 --only 목록에 coderabbit를 추가하는 sugar로 동작한다."""
    project_dir = tmp_path / "demo"
    with patch.object(
        sys,
        "argv",
        [
            "init_harness.py",
            "--project-dir",
            str(project_dir),
            "--offline",
            "--only",
            "adr",
            "--with-coderabbit",
            "x",
        ],
    ):
        init_harness.main()

    assert (project_dir / relative_path_for(TargetKind.ADR)).exists()
    assert (project_dir / ".coderabbit.yaml").exists()
    # POLICY는 targets에 없었으므로 생성되지 않는다
    assert not (project_dir / relative_path_for(TargetKind.POLICY)).exists()


def test_main_package_init_honors_existing_policy_source_root(tmp_path: Path) -> None:
    """기존 정책의 package/source_root를 따라 src 레이아웃 경로에 __init__.py를 쓴다."""
    project_dir = tmp_path / "billing-svc"
    policy_path = project_dir / relative_path_for(TargetKind.POLICY)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        "project:\n  name: billing\n  package: billing_core\n  source_root: src\n"
        "policies:\n  required_checks: [ruff]\n",
        encoding="utf-8",
    )

    with patch.object(
        sys,
        "argv",
        [
            "init_harness.py",
            "--project-dir",
            str(project_dir),
            "--offline",
            "--only",
            "package-init",
            "x",
        ],
    ):
        init_harness.main()

    assert (project_dir / "src" / "billing_core" / "__init__.py").exists()
    assert not (project_dir / "billing_svc" / "__init__.py").exists()


def test_main_rejects_policy_source_root_escaping_project(tmp_path: Path) -> None:
    """정책 source_root가 프로젝트 밖을 가리키면 거부하고 외부에 파일을 쓰지 않는다."""
    project_dir = tmp_path / "billing-svc"
    policy_path = project_dir / relative_path_for(TargetKind.POLICY)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        "project:\n  name: billing\n  package: billing_core\n  source_root: ../escape\n"
        "policies:\n  required_checks: [ruff]\n",
        encoding="utf-8",
    )

    with (
        patch.object(
            sys,
            "argv",
            [
                "init_harness.py",
                "--project-dir",
                str(project_dir),
                "--offline",
                "--only",
                "package-init",
                "x",
            ],
        ),
        pytest.raises(SystemExit),
    ):
        init_harness.main()

    assert not (tmp_path / "escape").exists()


def test_main_rejects_policy_package_escaping_project(tmp_path: Path) -> None:
    """정책 package가 상위 경로를 포함하면 거부한다."""
    project_dir = tmp_path / "billing-svc"
    policy_path = project_dir / relative_path_for(TargetKind.POLICY)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        "project:\n  name: billing\n  package: ../../evil\n"
        "policies:\n  required_checks: [ruff]\n",
        encoding="utf-8",
    )

    with (
        patch.object(
            sys,
            "argv",
            [
                "init_harness.py",
                "--project-dir",
                str(project_dir),
                "--offline",
                "--only",
                "package-init",
                "x",
            ],
        ),
        pytest.raises(SystemExit),
    ):
        init_harness.main()

    assert not (tmp_path / "evil").exists()
    assert not (tmp_path.parent / "evil").exists()


def test_main_rejects_unknown_only(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    with (
        patch.object(
            sys,
            "argv",
            [
                "init_harness.py",
                "--project-dir",
                str(project_dir),
                "--offline",
                "--only",
                "nonsense",
                "x",
            ],
        ),
        pytest.raises(SystemExit),
    ):
        init_harness.main()


def test_main_dry_run_does_not_write(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    with patch.object(
        sys,
        "argv",
        [
            "init_harness.py",
            "--project-dir",
            str(project_dir),
            "--offline",
            "--dry-run",
            "x",
        ],
    ):
        init_harness.main()

    for kind in ALL_TARGETS:
        assert not (project_dir / relative_path_for(kind)).exists()
    # dry-run에서는 대상 디렉터리 자체도 만들면 안 된다.
    assert not project_dir.exists()


def test_main_uses_template_when_endpoint_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HARNESS_API_ENDPOINT", raising=False)
    project_dir = tmp_path / "demo"
    with (
        patch.object(
            sys,
            "argv",
            ["init_harness.py", "--project-dir", str(project_dir), "x"],
        ),
        patch("scripts.init_harness.HarnessClient") as mock_client_cls,
    ):
        init_harness.main()

    mock_client_cls.assert_not_called()
    assert (project_dir / relative_path_for(TargetKind.POLICY)).exists()


def test_main_force_overwrites(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    target = project_dir / relative_path_for(TargetKind.CLAUDE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old\n", encoding="utf-8")

    with patch.object(
        sys,
        "argv",
        [
            "init_harness.py",
            "--project-dir",
            str(project_dir),
            "--offline",
            "--force",
            "--only",
            "claude",
            "사내 인보이스",
        ],
    ):
        init_harness.main()

    content = target.read_text(encoding="utf-8")
    assert content != "old\n"
    assert "운영 원칙" in content


def test_main_constructs_client_when_endpoint_provided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HARNESS_API_ENDPOINT", raising=False)
    project_dir = tmp_path / "demo"
    fake_client = MagicMock()
    fake_response = MagicMock()
    block = MagicMock()
    block.text = "# 테스트 ADR\n\n## Context\n내용\n"
    fake_response.content = [block]
    fake_client.create_message.return_value = fake_response

    with (
        patch.object(
            sys,
            "argv",
            [
                "init_harness.py",
                "--project-dir",
                str(project_dir),
                "--api-endpoint",
                "https://example.invalid/api",
                "--only",
                "adr",
                "테스트",
            ],
        ),
        patch("scripts.init_harness.HarnessClient", return_value=fake_client) as mock_cls,
    ):
        init_harness.main()

    mock_cls.assert_called_once()
    fake_client.create_message.assert_called_once()
    assert (project_dir / relative_path_for(TargetKind.ADR)).exists()


def test_main_migrate_dry_run_current_repo_reports_no_changes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    with patch.object(
        sys,
        "argv",
        [
            "init_harness.py",
            "--project-dir",
            str(repo_root),
            "--offline",
            "--migrate",
            "--dry-run",
        ],
    ):
        init_harness.main()

    captured = capsys.readouterr()
    assert "변경 사항 없음" in captured.out
    assert "[MIGRATE] 완료. 다음 단계:" in captured.out
