"""IntentGenerator 단위 테스트."""

from __future__ import annotations

from harness.review.intent import DesignIntent, IntentGenerator


class TestDesignIntent:
    def test_default_fields(self) -> None:
        intent = DesignIntent(task_overview="overview")
        assert intent.key_decisions == []
        assert intent.alternatives_considered == []
        assert intent.intentionally_excluded == []
        assert intent.review_notes == []
        assert intent.sprint_number == 0
        assert intent.task_description == ""

    def test_all_fields(self) -> None:
        intent = DesignIntent(
            task_overview="Test overview",
            key_decisions=["decision 1"],
            sprint_number=3,
            task_description="task desc",
        )
        assert intent.sprint_number == 3
        assert len(intent.key_decisions) == 1


class TestIntentGenerator:
    def test_generate_from_spec_basic(self) -> None:
        gen = IntentGenerator()
        sprint_info = {"number": 1, "name": "초기 설정", "goal": "기반 구축", "features": ["f1"]}
        intent = gen.generate_from_spec("테스트 작업", sprint_info=sprint_info)

        assert intent.sprint_number == 1
        assert "초기 설정" in intent.task_overview
        assert "기반 구축" in intent.task_overview
        assert intent.task_description == "테스트 작업"

    def test_generate_from_spec_no_sprint_info(self) -> None:
        gen = IntentGenerator()
        intent = gen.generate_from_spec("작업")
        assert intent.sprint_number == 0
        assert intent.task_overview != ""

    def test_generate_from_spec_with_contract(self) -> None:
        gen = IntentGenerator()
        intent = gen.generate_from_spec(
            "작업", sprint_contract="검증 기준: 테스트 통과"
        )
        assert any("계약" in d or "협의" in d for d in intent.key_decisions)

    def test_generate_from_spec_features_in_decisions(self) -> None:
        gen = IntentGenerator()
        sprint_info = {"number": 2, "name": "기능 구현", "features": ["로그인", "회원가입"]}
        intent = gen.generate_from_spec("기능 구현", sprint_info=sprint_info)
        assert any("로그인" in d or "회원가입" in d for d in intent.key_decisions)

    def test_generate_review_notes_not_empty(self) -> None:
        gen = IntentGenerator()
        intent = gen.generate_from_spec("작업")
        assert len(intent.review_notes) > 0

    def test_to_markdown_includes_sections(self) -> None:
        gen = IntentGenerator()
        sprint_info = {"number": 1, "name": "Sprint 1", "features": ["feat-a"]}
        intent = gen.generate_from_spec("task description", sprint_info=sprint_info)
        md = gen.to_markdown(intent)

        assert "# 설계 의도" in md
        assert "## 작업 개요" in md
        assert "## 핵심 설계 결정" in md
        assert "## 구현/리뷰 시 주의사항" in md

    def test_to_markdown_sprint_number(self) -> None:
        gen = IntentGenerator()
        sprint_info = {"number": 5, "name": "스프린트 5"}
        intent = gen.generate_from_spec("t", sprint_info=sprint_info)
        md = gen.to_markdown(intent)
        assert "5" in md

    def test_to_markdown_task_description_shown(self) -> None:
        gen = IntentGenerator()
        intent = gen.generate_from_spec("특별한 작업 설명")
        md = gen.to_markdown(intent)
        assert "특별한 작업 설명" in md

    def test_to_markdown_alternatives_section(self) -> None:
        gen = IntentGenerator()
        intent = gen.generate_from_spec("t")
        intent.alternatives_considered = [
            {"option": "Option A", "reason": "더 빠름"},
        ]
        md = gen.to_markdown(intent)
        assert "## 고려한 선택지" in md
        assert "Option A" in md

    def test_to_markdown_excluded_section(self) -> None:
        gen = IntentGenerator()
        intent = gen.generate_from_spec("t")
        intent.intentionally_excluded = ["레거시 API 지원"]
        md = gen.to_markdown(intent)
        assert "## 의도적으로 제외한 것" in md
        assert "레거시 API 지원" in md

    def test_to_markdown_no_alternatives_omits_section(self) -> None:
        gen = IntentGenerator()
        intent = gen.generate_from_spec("t")
        # alternatives_considered는 기본 []
        md = gen.to_markdown(intent)
        assert "## 고려한 선택지" not in md

    def test_to_markdown_returns_string(self) -> None:
        gen = IntentGenerator()
        intent = gen.generate_from_spec("test")
        result = gen.to_markdown(intent)
        assert isinstance(result, str)
        assert len(result) > 0
