"""harness/contracts 모듈 단위 테스트."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from harness.contracts.models import (
    AcceptanceCriterion,
    ContractMetadata,
    SprintContract,
)
from harness.contracts.store import ContractStore

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.logging import LogCaptureFixture


# ---------------------------------------------------------------------------
# AcceptanceCriterion
# ---------------------------------------------------------------------------

class TestAcceptanceCriterion:
    def test_creation_defaults(self) -> None:
        ac = AcceptanceCriterion(id="ac-001", description="API 응답 200")
        assert ac.feature == ""
        assert ac.priority == "must"

    def test_to_dict_roundtrip(self) -> None:
        ac = AcceptanceCriterion(
            id="ac-001", description="API 응답", feature="auth", priority="should"
        )
        restored = AcceptanceCriterion.from_dict(ac.to_dict())
        assert restored.id == "ac-001"
        assert restored.feature == "auth"
        assert restored.priority == "should"


# ---------------------------------------------------------------------------
# ContractMetadata
# ---------------------------------------------------------------------------

class TestContractMetadata:
    def test_created_at_auto_populated(self) -> None:
        meta = ContractMetadata()
        assert meta.created_at != ""
        assert "T" in meta.created_at

    def test_explicit_created_at_preserved(self) -> None:
        meta = ContractMetadata(created_at="2026-01-01T00:00:00+00:00")
        assert meta.created_at == "2026-01-01T00:00:00+00:00"

    def test_to_dict_roundtrip(self) -> None:
        meta = ContractMetadata(model="claude-sonnet-4-6", negotiation_rounds=2)
        restored = ContractMetadata.from_dict(meta.to_dict())
        assert restored.model == "claude-sonnet-4-6"
        assert restored.negotiation_rounds == 2


# ---------------------------------------------------------------------------
# SprintContract
# ---------------------------------------------------------------------------

class TestSprintContract:
    def test_creation_minimal(self) -> None:
        sc = SprintContract(sprint_number=1, raw_text="계약 내용")
        assert sc.sprint_number == 1
        assert sc.raw_text == "계약 내용"
        assert sc.features == []
        assert sc.acceptance_criteria == []

    def test_json_roundtrip(self) -> None:
        sc = SprintContract(
            sprint_number=3,
            raw_text="# Sprint 3 Contract\n내용",
            features=["인증", "대시보드"],
            acceptance_criteria=[
                AcceptanceCriterion(id="ac-001", description="로그인 성공"),
                AcceptanceCriterion(id="ac-002", description="대시보드 렌더링"),
            ],
            success_threshold="모든 검증 기준 통과",
        )
        json_str = sc.to_json()
        data = json.loads(json_str)
        assert data["sprint_number"] == 3
        assert len(data["acceptance_criteria"]) == 2

        restored = SprintContract.from_json(json_str)
        assert restored.sprint_number == 3
        assert restored.raw_text == sc.raw_text
        assert len(restored.features) == 2
        assert restored.features[0] == "인증"
        assert restored.acceptance_criteria[0].id == "ac-001"
        assert restored.success_threshold == "모든 검증 기준 통과"

    def test_from_dict_handles_missing_fields(self) -> None:
        sc = SprintContract.from_dict({"sprint_number": 1, "raw_text": "hello"})
        assert sc.sprint_number == 1
        assert sc.features == []
        assert sc.acceptance_criteria == []

    def test_from_dict_handles_bad_types(self) -> None:
        sc = SprintContract.from_dict({
            "sprint_number": 1,
            "raw_text": "x",
            "features": "not a list",
            "acceptance_criteria": "not a list",
            "metadata": "not a dict",
        })
        assert sc.features == []
        assert sc.acceptance_criteria == []


class TestSprintContractFromRawText:
    def test_extracts_features(self) -> None:
        raw = (
            "# 스프린트 1 계약\n\n"
            "## 구현할 기능 목록\n\n"
            "- 사용자 로그인\n"
            "- 대시보드 렌더링\n"
            "- 프로필 관리\n\n"
            "## 검증 기준\n\n"
            "- 로그인 성공 시 토큰 반환\n"
        )
        sc = SprintContract.from_raw_text(1, raw)
        assert sc.raw_text == raw
        assert "사용자 로그인" in sc.features
        assert "대시보드 렌더링" in sc.features

    def test_extracts_criteria(self) -> None:
        raw = (
            "## 검증 기준\n\n"
            "- 로그인 성공 시 200 반환\n"
            "- 잘못된 비밀번호 시 401 반환\n"
        )
        sc = SprintContract.from_raw_text(1, raw)
        assert len(sc.acceptance_criteria) == 2
        assert sc.acceptance_criteria[0].id == "ac-001"
        assert "200" in sc.acceptance_criteria[0].description

    def test_empty_text_returns_empty_fields(self) -> None:
        sc = SprintContract.from_raw_text(1, "")
        assert sc.features == []
        assert sc.acceptance_criteria == []

    def test_preserves_raw_text(self) -> None:
        raw = "Some arbitrary contract text with no structure"
        sc = SprintContract.from_raw_text(5, raw)
        assert sc.raw_text == raw
        assert sc.sprint_number == 5

    def test_warns_when_parsing_yields_nothing(self, caplog: LogCaptureFixture) -> None:
        raw = "Some text without markdown structure but not empty"
        with caplog.at_level(logging.WARNING, logger="harness.contracts.models"):
            sc = SprintContract.from_raw_text(1, raw)
        assert sc.features == []
        assert sc.acceptance_criteria == []
        assert "추출하지 못했습니다" in caplog.text

    def test_no_warning_on_empty_text(self, caplog: LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="harness.contracts.models"):
            SprintContract.from_raw_text(1, "")
        assert "추출하지 못했습니다" not in caplog.text


# ---------------------------------------------------------------------------
# ContractStore
# ---------------------------------------------------------------------------

class TestContractStore:
    def test_save_and_load(self, tmp_path: Path) -> None:
        store = ContractStore(tmp_path)
        contract = SprintContract(sprint_number=1, raw_text="계약 텍스트")
        store.save(contract)

        loaded = store.load(1)
        assert loaded is not None
        assert loaded.sprint_number == 1
        assert loaded.raw_text == "계약 텍스트"

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        store = ContractStore(tmp_path)
        assert store.load(99) is None

    def test_exists(self, tmp_path: Path) -> None:
        store = ContractStore(tmp_path)
        assert store.exists(1) is False
        store.save(SprintContract(sprint_number=1, raw_text="x"))
        assert store.exists(1) is True

    def test_list_sprints_sorted(self, tmp_path: Path) -> None:
        store = ContractStore(tmp_path)
        for n in [3, 1, 2]:
            store.save(SprintContract(sprint_number=n, raw_text=f"sprint {n}"))
        assert store.list_sprints() == [1, 2, 3]

    def test_list_sprints_empty(self, tmp_path: Path) -> None:
        store = ContractStore(tmp_path)
        assert store.list_sprints() == []

    def test_overwrite_existing(self, tmp_path: Path) -> None:
        store = ContractStore(tmp_path)
        store.save(SprintContract(sprint_number=1, raw_text="v1"))
        store.save(SprintContract(sprint_number=1, raw_text="v2"))
        loaded = store.load(1)
        assert loaded is not None
        assert loaded.raw_text == "v2"

    def test_load_corrupted_json_returns_none(self, tmp_path: Path) -> None:
        store = ContractStore(tmp_path)
        store.base_dir.mkdir(parents=True, exist_ok=True)
        path = store.base_dir / "sprint_1.json"
        path.write_text("{invalid json", encoding="utf-8")
        assert store.load(1) is None

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        store = ContractStore(tmp_path / "nested" / "deep")
        store.save(SprintContract(sprint_number=1, raw_text="x"))
        assert store.exists(1)

    def test_atomic_write_no_temp_files_left(self, tmp_path: Path) -> None:
        store = ContractStore(tmp_path)
        store.save(SprintContract(sprint_number=1, raw_text="atomic test"))
        temp_files = list(store.base_dir.glob(".contract-*.tmp"))
        assert temp_files == []

    def test_full_roundtrip_with_criteria(self, tmp_path: Path) -> None:
        store = ContractStore(tmp_path)
        contract = SprintContract(
            sprint_number=2,
            raw_text="## Sprint 2",
            features=["feature A", "feature B"],
            acceptance_criteria=[
                AcceptanceCriterion(id="ac-001", description="테스트 통과"),
            ],
            success_threshold="all pass",
            metadata=ContractMetadata(model="claude-sonnet-4-6", negotiation_rounds=2),
        )
        store.save(contract)

        loaded = store.load(2)
        assert loaded is not None
        assert loaded.features == ["feature A", "feature B"]
        assert len(loaded.acceptance_criteria) == 1
        assert loaded.acceptance_criteria[0].description == "테스트 통과"
        assert loaded.metadata.model == "claude-sonnet-4-6"
        assert loaded.metadata.negotiation_rounds == 2
