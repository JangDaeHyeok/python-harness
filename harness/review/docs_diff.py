"""docs-diff 시스템.

docs/ 디렉터리의 스펙 문서 변경을 줄 단위로 추적하여 구조화된 diff를 생성한다.
Phase별 구현 시 에이전트가 정확한 스펙 변경점만 참조할 수 있게 한다.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_DIFF_TIMEOUT = 30


@dataclass
class FileDiff:
    """단일 문서 파일의 줄 단위 변경."""

    path: str
    added_lines: list[tuple[int, str]] = field(default_factory=list)
    removed_lines: list[tuple[int, str]] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added_lines or self.removed_lines)


@dataclass
class DocsDiff:
    """docs 디렉터리 전체의 변경 요약."""

    base_ref: str
    file_diffs: list[FileDiff] = field(default_factory=list)

    @property
    def changed_files(self) -> list[str]:
        return [fd.path for fd in self.file_diffs if fd.has_changes]

    @property
    def has_changes(self) -> bool:
        return any(fd.has_changes for fd in self.file_diffs)

    def to_markdown(self) -> str:
        """구조화된 docs-diff 마크다운을 생성한다."""
        if not self.has_changes:
            return "# Docs Diff\n\n변경된 문서 없음.\n"

        lines: list[str] = [
            "# Docs Diff\n",
            f"**기준**: `{self.base_ref}`\n",
        ]

        for fd in self.file_diffs:
            if not fd.has_changes:
                continue
            lines.append(f"\n## `{fd.path}`\n")

            if fd.removed_lines:
                lines.append("### 삭제된 내용\n")
                for line_num, content in fd.removed_lines:
                    lines.append(f"- L{line_num}: `{content}`")

            if fd.added_lines:
                lines.append("\n### 추가된 내용\n")
                for line_num, content in fd.added_lines:
                    lines.append(f"- L{line_num}: `{content}`")

        lines.append("")
        return "\n".join(lines)


class DocsDiffGenerator:
    """git diff를 파싱하여 docs 디렉터리의 줄 단위 변경을 추적한다."""

    def __init__(self, project_dir: Path, docs_dirs: list[str] | None = None) -> None:
        self.project_dir = Path(project_dir)
        self.docs_dirs = docs_dirs or ["docs/"]

    def generate(self, base_ref: str = "HEAD") -> DocsDiff:
        """base_ref 기준으로 docs 디렉터리의 변경을 수집한다."""
        result = DocsDiff(base_ref=base_ref)

        for docs_dir in self.docs_dirs:
            raw_diff = self._get_raw_diff(base_ref, docs_dir)
            if not raw_diff:
                file_diffs = []
            else:
                file_diffs = self._parse_unified_diff(raw_diff)
                result.file_diffs.extend(file_diffs)

            tracked_paths = {fd.path for fd in file_diffs}
            result.file_diffs.extend(
                self._get_untracked_file_diffs(docs_dir, tracked_paths)
            )

        return result

    def generate_from_branch(self, base_branch: str = "main") -> DocsDiff:
        """base_branch 기준으로 현재 브랜치의 docs 변경을 수집한다."""
        ref = self._resolve_ref(base_branch)
        return self.generate(base_ref=f"{ref}...HEAD")

    def _get_raw_diff(self, base_ref: str, docs_dir: str) -> str:
        try:
            result = subprocess.run(
                ["git", "diff", base_ref, "--unified=0", "--", docs_dir],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=_DIFF_TIMEOUT,
            )
            if result.returncode != 0:
                logger.warning("git diff 실패 (docs_dir=%s): %s", docs_dir, result.stderr.strip())
                return ""
            return result.stdout
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning("git diff 실행 실패: %s", e)
            return ""

    def _get_untracked_file_diffs(
        self,
        docs_dir: str,
        tracked_paths: set[str],
    ) -> list[FileDiff]:
        """git diff가 보여주지 않는 untracked 문서 파일을 추가 줄로 수집한다."""
        try:
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard", "--", docs_dir],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=_DIFF_TIMEOUT,
            )
            if result.returncode != 0:
                logger.warning(
                    "untracked docs 조회 실패 (docs_dir=%s): %s",
                    docs_dir,
                    result.stderr.strip(),
                )
                return []
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning("untracked docs 조회 실행 실패: %s", e)
            return []

        diffs: list[FileDiff] = []
        project_root = self.project_dir.resolve()
        for raw_path in result.stdout.splitlines():
            rel_path = raw_path.strip()
            if not rel_path or rel_path in tracked_paths:
                continue

            path = (self.project_dir / rel_path).resolve()
            if not path.is_relative_to(project_root) or not path.is_file():
                continue

            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as e:
                logger.warning("untracked 문서 읽기 실패 (%s): %s", rel_path, e)
                continue

            diffs.append(
                FileDiff(
                    path=rel_path,
                    added_lines=[(i, line) for i, line in enumerate(lines, start=1)],
                )
            )

        return diffs

    def _resolve_ref(self, branch: str) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", branch],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return branch
        except (subprocess.SubprocessError, OSError):
            pass

        remote_ref = f"origin/{branch}"
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", remote_ref],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return remote_ref
        except (subprocess.SubprocessError, OSError):
            pass

        return branch

    @staticmethod
    def _parse_unified_diff(raw_diff: str) -> list[FileDiff]:
        """git diff --unified=0 출력을 파싱하여 FileDiff 목록을 반환한다."""
        file_diffs: list[FileDiff] = []
        current: FileDiff | None = None
        current_add_line = 0
        current_del_line = 0
        old_path = ""

        for line in raw_diff.splitlines():
            if line.startswith("diff --git"):
                if current is not None and current.has_changes:
                    file_diffs.append(current)
                current = None
                continue

            if line.startswith("+++ b/"):
                path = line[6:]
                current = FileDiff(path=path)
                continue

            if line.startswith("--- a/"):
                old_path = line[6:]
                continue

            if line == "+++ /dev/null" and old_path:
                current = FileDiff(path=old_path)
                continue

            if line.startswith("@@ ") and current is not None:
                hunk_info = line.split("@@")[1].strip()
                parts = hunk_info.split()
                if len(parts) >= 1:
                    old_part = parts[0]  # -start,count or -start
                    old_nums = old_part.lstrip("-").split(",")
                    current_del_line = int(old_nums[0]) if old_nums[0] else 0
                if len(parts) >= 2:
                    new_part = parts[1]  # +start,count or +start
                    new_nums = new_part.lstrip("+").split(",")
                    current_add_line = int(new_nums[0]) if new_nums[0] else 0
                continue

            if current is None:
                continue

            if line.startswith("-") and not line.startswith("---"):
                content = line[1:]
                current.removed_lines.append((current_del_line, content))
                current_del_line += 1
            elif line.startswith("+") and not line.startswith("+++"):
                content = line[1:]
                current.added_lines.append((current_add_line, content))
                current_add_line += 1

        if current is not None and current.has_changes:
            file_diffs.append(current)

        return file_diffs
