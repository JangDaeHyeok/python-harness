"""PR 본문 생성.

현재 브랜치 diff와 리뷰 산출물을 기반으로 pr-body.md를 생성한다.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from harness.context.knowledge import KnowledgeStore
from harness.tools.adr import ADRLoader, extract_key_sections

if TYPE_CHECKING:
    from harness.review.artifacts import ReviewArtifactManager

logger = logging.getLogger(__name__)

_MAX_RATIONALE_ADRS = 4


class DiffError(RuntimeError):
    """git diff 명령 실행 실패."""


def _resolve_base_ref(project_dir: Path, base_branch: str) -> str:
    """로컬 브랜치가 없을 때 origin/ 리모트 ref로 폴백한다.

    CI 환경(detached HEAD)에서는 로컬 main 브랜치가 없을 수 있으므로
    origin/main 등 리모트 ref를 시도한다.
    """
    check = subprocess.run(
        ["git", "rev-parse", "--verify", base_branch],
        cwd=str(project_dir),
        capture_output=True, text=True, timeout=10,
    )
    if check.returncode == 0:
        return base_branch

    remote_ref = f"origin/{base_branch}"
    check_remote = subprocess.run(
        ["git", "rev-parse", "--verify", remote_ref],
        cwd=str(project_dir),
        capture_output=True, text=True, timeout=10,
    )
    if check_remote.returncode == 0:
        return remote_ref

    return base_branch


def get_git_diff_stat(project_dir: Path, base_branch: str = "main") -> str:
    """base_branch에서 HEAD까지의 diff stat을 반환한다.

    Raises:
        DiffError: git diff 명령이 실패하면 발생한다.
    """
    ref = _resolve_base_ref(project_dir, base_branch)
    try:
        result = subprocess.run(
            ["git", "diff", f"{ref}...HEAD", "--stat"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        raise DiffError(f"git diff --stat 실행 실패: {e}") from e
    if result.returncode != 0:
        raise DiffError(
            f"git diff --stat 실패 (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def get_changed_files(project_dir: Path, base_branch: str = "main") -> list[str]:
    """base_branch에서 HEAD까지 변경된 파일 목록을 반환한다.

    Raises:
        DiffError: git diff 명령이 실패하면 발생한다.
    """
    ref = _resolve_base_ref(project_dir, base_branch)
    try:
        result = subprocess.run(
            ["git", "diff", f"{ref}...HEAD", "--name-only"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        raise DiffError(f"git diff --name-only 실행 실패: {e}") from e
    if result.returncode != 0:
        raise DiffError(
            f"git diff --name-only 실패 (exit {result.returncode}): {result.stderr.strip()}"
        )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


class PRBodyGenerator:
    """diff와 리뷰 산출물을 조합하여 PR 본문을 생성한다."""

    def __init__(
        self,
        project_dir: Path,
        external_adr_sources: list[str] | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)  # normalize
        self._adr_loader = ADRLoader(self.project_dir / "docs" / "adr")
        self._external_adr_sources = external_adr_sources or []
        self._knowledge_store = KnowledgeStore(self.project_dir)

    def generate(
        self,
        artifact_manager: ReviewArtifactManager,
        base_branch: str = "main",
        summary: str = "",
    ) -> str:
        """diff와 산출물 기반으로 PR 본문 마크다운을 생성한다."""
        diff_stat = get_git_diff_stat(self.project_dir, base_branch)
        changed_files = get_changed_files(self.project_dir, base_branch)

        design_intent = artifact_manager.load("design-intent.md") or ""
        quality_guide = artifact_manager.load("code-quality-guide.md")

        lines: list[str] = ["# PR 본문\n"]

        # Summary
        lines.append("## Summary\n")
        if summary:
            lines.append(summary)
        elif design_intent:
            lines.extend(self._extract_overview(design_intent))
        else:
            lines.append("_작업 요약을 여기에 작성하세요._")
        lines.append("")

        # Changes
        lines.append("## Changes\n")
        if changed_files:
            for f in changed_files:
                lines.append(f"- `{f}`")
        else:
            lines.append("_변경 파일 없음_")
        lines.append("")

        if diff_stat:
            lines.append("### Diff Summary\n")
            lines.append("```")
            lines.append(diff_stat[:3000])
            lines.append("```")
            lines.append("")

        # Breaking Changes
        lines.append("## Breaking Changes\n")
        lines.append("_없음 (있으면 여기에 기술)_\n")

        # Test Plan
        lines.append("## Test Plan\n")
        lines.append("- [ ] 단위 테스트 통과 (`pytest`)")
        lines.append("- [ ] 타입 체크 통과 (`mypy harness`)")
        lines.append("- [ ] 린트 통과 (`ruff check .`)")
        lines.append("- [ ] 구조 분석 통과 (`python3 scripts/check_structure.py`)")
        lines.append("")

        # ADR Rationale — 변경 파일/요약과 관련 있는 ADR을 동적으로 선별한다.
        lines.append("## ADR Rationale\n")
        query = " ".join([summary, design_intent, *changed_files])
        lines.extend(self._adr_rationale(query, changed_files))
        lines.append("")

        # 관련 과거 실행 지식 (있을 때만)
        knowledge_entries = self._knowledge_store.relevant(
            query, limit=3, fallback_to_recent=False
        )
        if knowledge_entries:
            lines.append(KnowledgeStore.to_markdown(knowledge_entries, title="관련 과거 실행 이력"))
            lines.append("")

        # Related Artifacts
        lines.append("## Related Artifacts\n")
        artifact_list = artifact_manager.list_artifacts()
        if artifact_list:
            for a in artifact_list:
                branch = artifact_manager.branch
                lines.append(f"- `.harness/review-artifacts/{branch}/{a}`")
        else:
            lines.append("_생성된 산출물 없음_")

        if quality_guide:
            lines.append("\n### Code Quality Guide\n")
            lines.append(quality_guide[:2000])
        lines.append("")

        return "\n".join(lines)

    def _adr_rationale(self, query: str, changed_files: list[str]) -> list[str]:
        """변경 내용과 관련 있는 accepted ADR의 근거를 한 줄씩 정리한다."""
        all_adrs = self._adr_loader.load_all()
        if self._external_adr_sources:
            all_adrs.extend(
                ADRLoader.load_from_external_sources(self._external_adr_sources)
            )
        accepted = [a for a in all_adrs if a.get("status") == "accepted"]
        if not accepted:
            return ["_관련 ADR을 찾지 못했습니다._"]

        relevant = self._adr_loader.filter_relevant(
            query, accepted, fallback_to_first=False
        )
        # filter_relevant는 affected_paths를 검색하지 않으므로, 변경 경로로만
        # 관련 있는 ADR이 여기서 탈락한다. 경로 매칭 ADR을 합집합으로 보강한다.
        relevant = self._merge_path_matches(relevant, accepted, changed_files)
        relevant = self._prioritize_by_paths(relevant, changed_files)[:_MAX_RATIONALE_ADRS]
        if not relevant:
            return ["_변경과 직접 관련된 ADR이 없습니다._"]

        lines: list[str] = []
        for adr in relevant:
            number = adr.get("number", "") or adr.get("filename", "")
            label = f"ADR-{number}" if number and number.isdigit() else number
            rationale = self._one_line_rationale(adr.get("content", ""))
            lines.append(f"- **{label}** {adr.get('title', '')}: {rationale}")
        return lines

    @staticmethod
    def _merge_path_matches(
        relevant: list[dict[str, str]],
        candidates: list[dict[str, str]],
        changed_files: list[str],
    ) -> list[dict[str, str]]:
        """변경 경로로만 관련 있는 ADR을 기존 결과에 합집합으로 추가한다."""
        if not changed_files:
            return relevant
        files = [f.lower() for f in changed_files]
        # 파일명은 소스마다 로컬이므로 (소스, 파일명)으로 식별해야
        # 로컬 ADR과 외부 ADR이 같은 번호/파일명을 가져도 충돌하지 않는다.
        seen = {(a.get("source", ""), a.get("filename", "")) for a in relevant}
        merged = list(relevant)
        for adr in candidates:
            key = (adr.get("source", ""), adr.get("filename", ""))
            if key not in seen and PRBodyGenerator._path_score(adr, files) > 0:
                merged.append(adr)
                seen.add(key)
        return merged

    @staticmethod
    def _prioritize_by_paths(
        adrs: list[dict[str, str]], changed_files: list[str],
    ) -> list[dict[str, str]]:
        """변경 파일 경로와 ADR 영향 경로가 겹치는 항목을 앞으로 정렬한다."""
        if not changed_files:
            return adrs
        files = [f.lower() for f in changed_files]
        return sorted(
            adrs, key=lambda adr: PRBodyGenerator._path_score(adr, files), reverse=True
        )

    @staticmethod
    def _path_score(adr: dict[str, str], files: list[str]) -> int:
        """ADR 영향 경로와 (소문자) 변경 파일 경로가 겹치는 개수를 센다."""
        prefixes = [
            p.strip().rstrip("/*").lower()
            for p in adr.get("affected_paths", "").split(",")
            if p.strip()
        ]
        return sum(
            1 for p in prefixes if p and any(p in f or f.startswith(p) for f in files)
        )

    @staticmethod
    def _one_line_rationale(content: str) -> str:
        """ADR 본문에서 결정 핵심을 한 줄로 요약한다."""
        sections = extract_key_sections(content)
        for line in sections.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped[:200]
        return "아키텍처 결정 근거 참조."

    @staticmethod
    def _extract_overview(design_intent_md: str) -> list[str]:
        """design-intent.md에서 작업 개요 섹션을 추출한다."""
        in_section = False
        extracted: list[str] = []
        for line in design_intent_md.splitlines():
            if line.startswith("## 작업 개요"):
                in_section = True
                continue
            if in_section:
                if line.startswith("##"):
                    break
                if line.strip():
                    extracted.append(line)
        return extracted if extracted else ["_설계 의도에서 개요를 찾을 수 없음_"]
