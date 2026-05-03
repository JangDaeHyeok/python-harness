"""harness/review/docs_diff.py 테스트."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from harness.review.docs_diff import DocsDiff, DocsDiffGenerator, FileDiff


class TestFileDiff:
    def test_empty_file_diff_has_no_changes(self) -> None:
        fd = FileDiff(path="docs/spec.md")
        assert not fd.has_changes

    def test_file_diff_with_added_lines(self) -> None:
        fd = FileDiff(
            path="docs/spec.md",
            added_lines=[(10, "새로운 내용")],
        )
        assert fd.has_changes

    def test_file_diff_with_removed_lines(self) -> None:
        fd = FileDiff(
            path="docs/spec.md",
            removed_lines=[(5, "삭제된 내용")],
        )
        assert fd.has_changes


class TestDocsDiff:
    def test_empty_docs_diff(self) -> None:
        dd = DocsDiff(base_ref="HEAD")
        assert not dd.has_changes
        assert dd.changed_files == []

    def test_to_markdown_no_changes(self) -> None:
        dd = DocsDiff(base_ref="HEAD")
        md = dd.to_markdown()
        assert "변경된 문서 없음" in md

    def test_to_markdown_with_changes(self) -> None:
        dd = DocsDiff(
            base_ref="HEAD",
            file_diffs=[
                FileDiff(
                    path="docs/api.md",
                    added_lines=[(15, "JWT 인증 추가")],
                    removed_lines=[(14, "세션 기반 인증")],
                ),
            ],
        )
        md = dd.to_markdown()
        assert "docs/api.md" in md
        assert "JWT 인증 추가" in md
        assert "세션 기반 인증" in md
        assert dd.has_changes
        assert dd.changed_files == ["docs/api.md"]

    def test_changed_files_excludes_unchanged(self) -> None:
        dd = DocsDiff(
            base_ref="HEAD",
            file_diffs=[
                FileDiff(path="docs/unchanged.md"),
                FileDiff(path="docs/changed.md", added_lines=[(1, "new")]),
            ],
        )
        assert dd.changed_files == ["docs/changed.md"]


class TestDocsDiffGeneratorParsing:
    def test_parse_unified_diff_add(self) -> None:
        raw = (
            "diff --git a/docs/spec.md b/docs/spec.md\n"
            "--- a/docs/spec.md\n"
            "+++ b/docs/spec.md\n"
            "@@ -0,0 +10,1 @@\n"
            "+새로운 스펙 항목\n"
        )
        diffs = DocsDiffGenerator._parse_unified_diff(raw)
        assert len(diffs) == 1
        assert diffs[0].path == "docs/spec.md"
        assert len(diffs[0].added_lines) == 1
        assert diffs[0].added_lines[0] == (10, "새로운 스펙 항목")

    def test_parse_unified_diff_remove(self) -> None:
        raw = (
            "diff --git a/docs/old.md b/docs/old.md\n"
            "--- a/docs/old.md\n"
            "+++ b/docs/old.md\n"
            "@@ -5,1 +5,0 @@\n"
            "-제거된 줄\n"
        )
        diffs = DocsDiffGenerator._parse_unified_diff(raw)
        assert len(diffs) == 1
        assert len(diffs[0].removed_lines) == 1
        assert diffs[0].removed_lines[0] == (5, "제거된 줄")

    def test_parse_deleted_file(self) -> None:
        raw = (
            "diff --git a/docs/deleted.md b/docs/deleted.md\n"
            "deleted file mode 100644\n"
            "--- a/docs/deleted.md\n"
            "+++ /dev/null\n"
            "@@ -1,2 +0,0 @@\n"
            "-첫 줄\n"
            "-둘째 줄\n"
        )
        diffs = DocsDiffGenerator._parse_unified_diff(raw)
        assert len(diffs) == 1
        assert diffs[0].path == "docs/deleted.md"
        assert diffs[0].removed_lines == [(1, "첫 줄"), (2, "둘째 줄")]

    def test_parse_unified_diff_multiple_files(self) -> None:
        raw = (
            "diff --git a/docs/a.md b/docs/a.md\n"
            "--- a/docs/a.md\n"
            "+++ b/docs/a.md\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n"
            "diff --git a/docs/b.md b/docs/b.md\n"
            "--- a/docs/b.md\n"
            "+++ b/docs/b.md\n"
            "@@ -0,0 +1,1 @@\n"
            "+added\n"
        )
        diffs = DocsDiffGenerator._parse_unified_diff(raw)
        assert len(diffs) == 2
        assert diffs[0].path == "docs/a.md"
        assert diffs[1].path == "docs/b.md"

    def test_parse_empty_diff(self) -> None:
        diffs = DocsDiffGenerator._parse_unified_diff("")
        assert diffs == []

    def test_generate_includes_untracked_docs(self, tmp_path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "new.md").write_text("# 새 문서\n내용\n", encoding="utf-8")

        diff_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="")
        untracked_result = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="docs/new.md\n",
        )

        with patch("subprocess.run", side_effect=[diff_result, untracked_result]):
            docs_diff = DocsDiffGenerator(tmp_path).generate()

        assert docs_diff.changed_files == ["docs/new.md"]
        assert docs_diff.file_diffs[0].added_lines == [(1, "# 새 문서"), (2, "내용")]
