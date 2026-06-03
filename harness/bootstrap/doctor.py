"""GitHub/Python 환경 사전 점검 로직.

라이브러리 계층은 점검 결과 데이터 모델만 반환하고, 사용자 출력(한국어)은
``scripts/doctor.py``가 담당한다. (``harness/`` 내부 print 금지 규칙 준수)
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from harness.tools.api_client import ENDPOINT_ENV_VAR
from harness.tools.shell import run_argv_safe

REQUIRED_TOOLS = ("git", "gh", "ruff", "mypy", "pytest", "claude")


@dataclass(frozen=True)
class DoctorCheck:
    """단일 사전 점검 결과."""

    name: str
    ok: bool
    detail: str = ""
    fix: str = ""


def _git_ok(project_dir: Path, argv: list[str]) -> tuple[bool, str]:
    """git 명령을 실행해 (성공 여부, stdout 첫 줄)을 반환한다."""
    result = run_argv_safe(argv, project_dir, timeout=15)
    if not result.ok:
        return False, (result.stderr or result.error_message).strip()
    return True, result.stdout.strip()


def _check_git_repo(project_dir: Path) -> DoctorCheck:
    ok, detail = _git_ok(project_dir, ["git", "rev-parse", "--is-inside-work-tree"])
    return DoctorCheck(
        name="git 저장소",
        ok=ok and detail == "true",
        detail="git 작업 트리 안에 있습니다." if ok else detail,
        fix="`git init` 후 다시 시도하세요." if not ok else "",
    )


def _check_origin_remote(project_dir: Path) -> DoctorCheck:
    ok, detail = _git_ok(project_dir, ["git", "remote"])
    remotes = detail.split() if ok else []
    has_origin = "origin" in remotes
    return DoctorCheck(
        name="origin 원격",
        ok=has_origin,
        detail=f"원격: {', '.join(remotes)}" if remotes else "등록된 원격이 없습니다.",
        fix=(
            "`git remote add origin <GitHub URL>`로 원격을 등록하세요."
            if not has_origin
            else ""
        ),
    )


def _check_current_branch(project_dir: Path) -> DoctorCheck:
    ok, detail = _git_ok(project_dir, ["git", "rev-parse", "--abbrev-ref", "HEAD"])
    detached = ok and detail == "HEAD"
    branch_ok = ok and bool(detail) and not detached
    if detached:
        return DoctorCheck(
            name="현재 브랜치",
            ok=False,
            detail="detached HEAD 상태입니다(브랜치가 아님).",
            fix="`git checkout -b <브랜치>`로 작업 브랜치를 만들거나 체크아웃하세요.",
        )
    return DoctorCheck(
        name="현재 브랜치",
        ok=branch_ok,
        detail=f"현재 브랜치: {detail}" if ok else detail,
        fix="커밋이 1개 이상 있어야 브랜치가 결정됩니다." if not branch_ok else "",
    )


def _check_default_branch(project_dir: Path) -> DoctorCheck:
    ok, detail = _git_ok(
        project_dir, ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"]
    )
    return DoctorCheck(
        name="기본(base) 브랜치",
        ok=ok and bool(detail),
        detail=f"기본 브랜치: {detail}" if ok else "origin/HEAD를 확인할 수 없습니다.",
        fix=(
            "`git remote set-head origin -a`로 기본 브랜치를 감지시키세요."
            if not ok
            else ""
        ),
    )


def _check_tool(name: str) -> DoctorCheck:
    path = shutil.which(name)
    return DoctorCheck(
        name=f"{name} 설치",
        ok=path is not None,
        detail=f"경로: {path}" if path else f"{name} 실행 파일을 찾을 수 없습니다.",
        fix=f"{name}를 설치하고 PATH에 추가하세요." if path is None else "",
    )


def _check_gh_auth(project_dir: Path) -> DoctorCheck:
    if shutil.which("gh") is None:
        return DoctorCheck(
            name="gh 인증",
            ok=False,
            detail="gh CLI가 설치되어 있지 않습니다.",
            fix="gh CLI 설치 후 `gh auth login`을 실행하세요.",
        )
    result = run_argv_safe(["gh", "auth", "status"], project_dir, timeout=20)
    return DoctorCheck(
        name="gh 인증",
        ok=result.ok,
        detail="gh 인증 상태 정상." if result.ok else "gh 인증이 필요합니다.",
        fix="`gh auth login`으로 GitHub 인증을 완료하세요." if not result.ok else "",
    )


def _check_api_endpoint(api_endpoint: str | None) -> DoctorCheck:
    endpoint = (api_endpoint or os.environ.get(ENDPOINT_ENV_VAR, "")).strip()
    return DoctorCheck(
        name="API 엔드포인트",
        ok=bool(endpoint),
        detail=(
            f"엔드포인트 설정됨: {endpoint}"
            if endpoint
            else f"{ENDPOINT_ENV_VAR}가 비어 있습니다(offline 모드만 가능)."
        ),
        fix=(
            f"`export {ENDPOINT_ENV_VAR}=<URL>` 또는 --api-endpoint를 지정하세요."
            if not endpoint
            else ""
        ),
    )


def _check_file(project_dir: Path, relative: str, label: str) -> DoctorCheck:
    exists = (project_dir / relative).exists()
    return DoctorCheck(
        name=label,
        ok=exists,
        detail=f"{relative} 존재." if exists else f"{relative}가 없습니다.",
        fix=f"`harness-init`로 {relative}를 생성하세요." if not exists else "",
    )


def _check_adr(project_dir: Path) -> DoctorCheck:
    adr_dir = project_dir / "docs" / "adr"
    docs = sorted(adr_dir.glob("*.md")) if adr_dir.is_dir() else []
    return DoctorCheck(
        name="ADR 문서",
        ok=bool(docs),
        detail=f"ADR {len(docs)}개 존재." if docs else "docs/adr/*.md가 없습니다.",
        fix="`harness-init`로 초기 ADR을 생성하세요." if not docs else "",
    )


def run_doctor(
    project_dir: Path | str, api_endpoint: str | None = None
) -> list[DoctorCheck]:
    """GitHub/Python 준비 상태를 점검해 결과 목록을 반환한다."""
    root = Path(project_dir).resolve()
    checks: list[DoctorCheck] = [
        _check_git_repo(root),
        _check_origin_remote(root),
        _check_current_branch(root),
        _check_default_branch(root),
    ]
    checks.extend(_check_tool(tool) for tool in REQUIRED_TOOLS)
    checks.append(_check_gh_auth(root))
    checks.append(_check_api_endpoint(api_endpoint))
    checks.append(
        _check_file(root, ".harness/project-policy.yaml", "프로젝트 정책 파일")
    )
    checks.append(_check_file(root, "harness_structure.yaml", "구조 규칙 파일"))
    checks.append(_check_file(root, "docs/code-convention.yaml", "코드 컨벤션 파일"))
    checks.append(_check_adr(root))
    return checks
