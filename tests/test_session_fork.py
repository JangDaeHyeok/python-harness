"""harness/review/session_fork.py 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from harness.review.session_fork import (
    SessionContext,
    SessionForkManager,
)


class TestSessionContext:
    def test_to_prompt_basic(self) -> None:
        ctx = SessionContext(
            user_prompt="할일 앱을 만들어줘",
            sprint_info="Sprint 1: 기본 CRUD",
            key_decisions=["React 사용", "REST API"],
        )
        prompt = ctx.to_prompt()
        assert "할일 앱" in prompt
        assert "Sprint 1" in prompt
        assert "React 사용" in prompt
        assert "REST API" in prompt
        assert "design-intent.md" in prompt

    def test_to_prompt_minimal(self) -> None:
        ctx = SessionContext()
        prompt = ctx.to_prompt()
        assert "설계 의도 문서 작성 요청" in prompt
        assert "_요청 없음_" in prompt

    def test_to_prompt_with_conversation_summary(self) -> None:
        ctx = SessionContext(
            user_prompt="수정 요청",
            conversation_summary="인증 방식을 JWT로 변경하기로 합의",
        )
        prompt = ctx.to_prompt()
        assert "JWT" in prompt
        assert "대화 요약" in prompt

    def test_to_prompt_with_existing_adrs(self) -> None:
        ctx = SessionContext(
            user_prompt="테스트",
            existing_adrs=["0001-test.md", "0002-other.md"],
        )
        prompt = ctx.to_prompt()
        assert "0001-test.md" in prompt
        assert "기존 ADR 목록" in prompt


class TestSessionForkManager:
    def test_create_context(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "0001-test.md").write_text("# Test", encoding="utf-8")

        mgr = SessionForkManager(tmp_path)
        ctx = mgr.create_context(
            user_prompt="테스트 요청",
            sprint_info="Sprint 1",
            key_decisions=["결정1"],
        )
        assert ctx.user_prompt == "테스트 요청"
        assert "0001-test.md" in ctx.existing_adrs
        assert ctx.key_decisions == ["결정1"]

    def test_generate_intent_from_context(self, tmp_path: Path) -> None:
        (tmp_path / ".harness" / "review-artifacts" / "main").mkdir(parents=True, exist_ok=True)
        mgr = SessionForkManager(tmp_path)
        ctx = SessionContext(
            user_prompt="인증 시스템 구현",
            sprint_info="Sprint 2: OAuth 통합",
            key_decisions=["OAuth2.0 채택", "세션 → JWT 전환"],
            conversation_summary="보안 요구사항에 따라 JWT 방식으로 결정",
        )
        content = mgr.generate_intent_from_context(ctx)
        assert "인증 시스템 구현" in content
        assert "OAuth2.0 채택" in content
        assert "JWT" in content

        artifacts_dir = tmp_path / ".harness" / "review-artifacts"
        intent_files = list(artifacts_dir.rglob("design-intent.md"))
        assert len(intent_files) >= 1

    def test_create_context_no_adr_dir(self, tmp_path: Path) -> None:
        mgr = SessionForkManager(tmp_path)
        ctx = mgr.create_context("테스트")
        assert ctx.existing_adrs == []
