"""세션 포크 기반 설계 의도 문서화.

메인 세션의 대화 컨텍스트를 요약하여 별도 세션(또는 서브에이전트)에서
설계 의도 문서와 ADR을 작성하게 한다.
문서만 남기고 세션은 폐기하여 메인 세션의 컨텍스트를 보존한다.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from harness.review.artifacts import ReviewArtifactManager

logger = logging.getLogger(__name__)

_FORK_TIMEOUT = 300


@dataclass
class ForkResult:
    """세션 포크 실행 결과."""

    success: bool = False
    design_intent_path: str = ""
    adr_path: str = ""
    output: str = ""
    error: str = ""


@dataclass
class SessionContext:
    """메인 세션에서 포크 세션에 전달할 컨텍스트."""

    user_prompt: str = ""
    sprint_info: str = ""
    key_decisions: list[str] = field(default_factory=list)
    existing_adrs: list[str] = field(default_factory=list)
    conversation_summary: str = ""

    def to_prompt(self) -> str:
        """포크 세션에 전달할 자기 완결적 프롬프트를 생성한다."""
        lines: list[str] = [
            "# 설계 의도 문서 작성 요청\n",
            "다음 프로젝트 컨텍스트를 바탕으로 설계 의도 문서를 작성해주세요.\n",
        ]

        lines.append("## 사용자 요청\n")
        lines.append(self.user_prompt or "_요청 없음_")
        lines.append("")

        if self.sprint_info:
            lines.append("## 스프린트 정보\n")
            lines.append(self.sprint_info)
            lines.append("")

        if self.key_decisions:
            lines.append("## 핵심 설계 결정\n")
            for decision in self.key_decisions:
                lines.append(f"- {decision}")
            lines.append("")

        if self.conversation_summary:
            lines.append("## 대화 요약\n")
            lines.append(self.conversation_summary)
            lines.append("")

        if self.existing_adrs:
            lines.append("## 기존 ADR 목록\n")
            for adr in self.existing_adrs:
                lines.append(f"- {adr}")
            lines.append("")

        lines.append("## 요청 사항\n")
        lines.append("1. design-intent.md 파일을 생성해주세요.")
        lines.append("2. 새로운 아키텍처 결정이 있다면 ADR 파일도 생성해주세요.")
        lines.append("3. 파일은 .harness/review-artifacts/ 아래에 저장해주세요.")
        lines.append("")

        return "\n".join(lines)


class SessionForkManager:
    """세션 포크를 통해 설계 의도 문서를 생성하고 관리한다."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self._artifacts = ReviewArtifactManager(self.project_dir)

    def create_context(
        self,
        user_prompt: str,
        sprint_info: str = "",
        key_decisions: list[str] | None = None,
        conversation_summary: str = "",
    ) -> SessionContext:
        """포크 세션에 전달할 컨텍스트를 조립한다."""
        existing_adrs: list[str] = []
        adr_dir = self.project_dir / "docs" / "adr"
        if adr_dir.exists():
            existing_adrs = [p.name for p in sorted(adr_dir.glob("*.md"))]

        return SessionContext(
            user_prompt=user_prompt,
            sprint_info=sprint_info,
            key_decisions=key_decisions or [],
            existing_adrs=existing_adrs,
            conversation_summary=conversation_summary,
        )

    def execute_fork(
        self,
        context: SessionContext,
        timeout: int = _FORK_TIMEOUT,
    ) -> ForkResult:
        """포크 세션을 실행하여 설계 의도 문서를 생성한다.

        claude --print 모드로 독립 세션을 실행하고,
        생성된 문서만 보존한 뒤 세션을 폐기한다.
        """
        prompt = context.to_prompt()

        try:
            result = subprocess.run(
                ["claude", "--print", "-p", prompt],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            return ForkResult(
                success=False,
                error="claude CLI를 찾을 수 없습니다.",
            )
        except subprocess.TimeoutExpired:
            return ForkResult(
                success=False,
                error=f"세션 포크 타임아웃 ({timeout}초)",
            )
        except (subprocess.SubprocessError, OSError) as e:
            return ForkResult(
                success=False,
                error=str(e),
            )

        if result.returncode != 0:
            return ForkResult(
                success=False,
                error=result.stderr.strip(),
                output=result.stdout,
            )

        fork_result = ForkResult(success=True, output=result.stdout)

        intent = self._artifacts.load("design-intent.md")
        if intent:
            fork_result.design_intent_path = str(
                self._artifacts.artifact_dir / "design-intent.md"
            )

        logger.info("세션 포크 실행 완료 (출력 %d자)", len(result.stdout))
        return fork_result

    def generate_intent_from_context(
        self,
        context: SessionContext,
    ) -> str:
        """LLM 없이 컨텍스트 기반으로 설계 의도 문서를 생성한다.

        claude CLI가 없는 환경에서의 폴백용.
        """
        lines: list[str] = [
            "# 설계 의도 (Design Intent)\n",
            "## 작업 개요\n",
            context.user_prompt or "_작업 설명 없음_",
            "",
        ]

        if context.sprint_info:
            lines.append("## 스프린트 정보\n")
            lines.append(context.sprint_info)
            lines.append("")

        if context.key_decisions:
            lines.append("## 핵심 설계 결정\n")
            for decision in context.key_decisions:
                lines.append(f"- {decision}")
            lines.append("")

        if context.conversation_summary:
            lines.append("## 대화 맥락 요약\n")
            lines.append(context.conversation_summary)
            lines.append("")

        lines.append("## 구현/리뷰 시 주의사항\n")
        lines.append("- 이 문서는 메인 세션의 대화 컨텍스트를 기반으로 생성되었습니다.")
        lines.append("- 구현 중 변경이 발생하면 이 문서를 업데이트하세요.")
        lines.append("")

        content = "\n".join(lines)
        self._artifacts.save("design-intent.md", content)
        logger.info("설계 의도 문서 생성 (폴백 모드)")
        return content
