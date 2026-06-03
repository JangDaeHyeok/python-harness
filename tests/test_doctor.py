"""harness-doctor 사전 점검 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness.bootstrap import doctor
from harness.tools.shell import CommandResult

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    import pytest


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(argv=["git"], returncode=0, stdout=stdout)


def _fail(stderr: str = "error") -> CommandResult:
    return CommandResult(argv=["git"], returncode=1, stderr=stderr)


def _check(checks: list[doctor.DoctorCheck], name: str) -> doctor.DoctorCheck:
    return next(c for c in checks if c.name == name)


def test_run_doctor_all_passing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """모든 환경이 준비되면 전부 통과한다."""
    git_responses = {
        ("git", "rev-parse", "--is-inside-work-tree"): _ok("true"),
        ("git", "remote"): _ok("origin"),
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): _ok("feature/x"),
        ("git", "rev-parse", "--abbrev-ref", "origin/HEAD"): _ok("origin/main"),
        ("gh", "auth", "status"): _ok("ok"),
    }

    def fake_run(argv: Sequence[str], cwd: object, timeout: int = 120) -> CommandResult:
        return git_responses[tuple(argv)]

    monkeypatch.setattr(doctor, "run_argv_safe", fake_run)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("HARNESS_API_ENDPOINT", "https://example.invalid/v1")

    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "project-policy.yaml").write_text("x", encoding="utf-8")
    (tmp_path / "harness_structure.yaml").write_text("x", encoding="utf-8")
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "docs" / "adr" / "0001.md").write_text("x", encoding="utf-8")
    (tmp_path / "docs" / "code-convention.yaml").write_text("x", encoding="utf-8")

    checks = doctor.run_doctor(tmp_path)

    assert all(c.ok for c in checks), [c.name for c in checks if not c.ok]


def test_run_doctor_reports_korean_fixes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """실패 항목은 한국어 조치 문구를 포함한다."""

    def fake_run(argv: Sequence[str], cwd: object, timeout: int = 120) -> CommandResult:
        return _fail("not a git repository")

    monkeypatch.setattr(doctor, "run_argv_safe", fake_run)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    monkeypatch.delenv("HARNESS_API_ENDPOINT", raising=False)

    checks = doctor.run_doctor(tmp_path)

    git_repo = _check(checks, "git 저장소")
    assert not git_repo.ok
    assert "git init" in git_repo.fix

    gh_auth = _check(checks, "gh 인증")
    assert not gh_auth.ok
    assert "gh auth login" in gh_auth.fix

    endpoint = _check(checks, "API 엔드포인트")
    assert not endpoint.ok
    assert "HARNESS_API_ENDPOINT" in endpoint.fix


def test_run_doctor_flags_detached_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """detached HEAD 상태는 현재 브랜치 점검을 실패로 처리한다."""

    def fake_run(argv: Sequence[str], cwd: object, timeout: int = 120) -> CommandResult:
        if tuple(argv) == ("git", "rev-parse", "--abbrev-ref", "HEAD"):
            return _ok("HEAD")
        return _ok("true")

    monkeypatch.setattr(doctor, "run_argv_safe", fake_run)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")

    checks = doctor.run_doctor(tmp_path)

    branch = _check(checks, "현재 브랜치")
    assert not branch.ok
    assert "git checkout -b" in branch.fix


def test_run_doctor_missing_origin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """origin 원격이 없으면 등록 안내를 표시한다."""

    def fake_run(argv: Sequence[str], cwd: object, timeout: int = 120) -> CommandResult:
        if tuple(argv) == ("git", "remote"):
            return _ok("upstream")
        return _ok("true")

    monkeypatch.setattr(doctor, "run_argv_safe", fake_run)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")

    checks = doctor.run_doctor(tmp_path)

    origin = _check(checks, "origin 원격")
    assert not origin.ok
    assert "git remote add origin" in origin.fix
