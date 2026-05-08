"""scripts/init_harness.py CLI 옵션 연결 테스트."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from harness.bootstrap.initializer import ALL_TARGETS, TargetKind, relative_path_for
from scripts import init_harness

if TYPE_CHECKING:
    from pathlib import Path


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
