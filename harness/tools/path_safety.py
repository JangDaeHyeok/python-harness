"""경로에 들어갈 식별자 정규화/검증 유틸리티."""

from __future__ import annotations

import re

DEFAULT_BRANCH_FALLBACK = "unknown-branch"


def sanitize_branch_name(name: str, fallback: str = DEFAULT_BRANCH_FALLBACK) -> str:
    """브랜치명을 파일 경로에 안전한 형식으로 변환한다."""
    sanitized = name.replace("/", "-")
    sanitized = re.sub(r"[^\w\-.]", "-", sanitized)
    sanitized = sanitized.replace("..", ".")
    sanitized = re.sub(r"-{2,}", "-", sanitized)
    sanitized = sanitized.strip("-.")
    return sanitized or fallback


def validate_run_id(run_id: str) -> None:
    """체크포인트 run_id가 파일명으로 안전한 식별자인지 검증한다."""
    if not run_id or not all(c.isalnum() or c in "-_" for c in run_id):
        raise ValueError(f"안전하지 않은 run_id입니다: {run_id!r}")
