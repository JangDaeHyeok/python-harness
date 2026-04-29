"""스프린트 계약 데이터 모델.

기존 문자열 계약(raw_text)을 보존하면서 구조화 필드를 점진적으로 사용할 수 있도록 설계한다.
JSON 직렬화/역직렬화를 지원한다.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class AcceptanceCriterion:
    """계약 내 개별 검증 기준."""

    id: str
    description: str
    feature: str = ""
    verification_method: str = ""
    priority: str = "must"  # "must" | "should" | "nice-to-have"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> AcceptanceCriterion:
        return cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            feature=data.get("feature", ""),
            verification_method=data.get("verification_method", ""),
            priority=data.get("priority", "must"),
        )


@dataclass
class ContractMetadata:
    """계약 메타데이터."""

    created_at: str = ""
    model: str = ""
    negotiation_rounds: int = 1

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(tz=UTC).isoformat()

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str | int]) -> ContractMetadata:
        return cls(
            created_at=str(data.get("created_at", "")),
            model=str(data.get("model", "")),
            negotiation_rounds=int(data.get("negotiation_rounds", 1)),
        )


@dataclass
class SprintContract:
    """스프린트 계약.

    raw_text로 기존 문자열 계약을 보존하면서,
    features/criteria 등 구조화 필드를 점진적으로 채울 수 있다.
    """

    sprint_number: int
    raw_text: str
    features: list[str] = field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = field(default_factory=list)
    success_threshold: str = ""
    metadata: ContractMetadata = field(default_factory=ContractMetadata)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_dict(self) -> dict[str, object]:
        return {
            "sprint_number": self.sprint_number,
            "raw_text": self.raw_text,
            "features": self.features,
            "acceptance_criteria": [c.to_dict() for c in self.acceptance_criteria],
            "success_threshold": self.success_threshold,
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_json(cls, text: str) -> SprintContract:
        data = json.loads(text)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SprintContract:
        criteria_raw = data.get("acceptance_criteria", [])
        criteria = [
            AcceptanceCriterion.from_dict(c)
            for c in (criteria_raw if isinstance(criteria_raw, list) else [])
            if isinstance(c, dict)
        ]
        meta_raw = data.get("metadata", {})
        metadata = ContractMetadata.from_dict(
            meta_raw if isinstance(meta_raw, dict) else {}
        )
        features_raw = data.get("features", [])
        features = list(features_raw) if isinstance(features_raw, list) else []

        return cls(
            sprint_number=int(str(data.get("sprint_number", 0))),
            raw_text=str(data.get("raw_text", "")),
            features=[str(f) for f in features],
            acceptance_criteria=criteria,
            success_threshold=str(data.get("success_threshold", "")),
            metadata=metadata,
        )

    @classmethod
    def from_raw_text(cls, sprint_number: int, raw_text: str) -> SprintContract:
        """기존 문자열 계약에서 구조화 필드를 최선 노력으로 추출한다."""
        features = _extract_features(raw_text)
        criteria = _extract_criteria(raw_text)
        if raw_text.strip() and not features and not criteria:
            logger.warning(
                "Sprint %d: 계약 텍스트에서 기능/기준을 추출하지 못했습니다 "
                "(raw_text %d자). 마크다운 형식을 확인하세요.",
                sprint_number, len(raw_text),
            )
        return cls(
            sprint_number=sprint_number,
            raw_text=raw_text,
            features=features,
            acceptance_criteria=criteria,
        )


def _extract_features(text: str) -> list[str]:
    """마크다운 리스트에서 기능 항목을 추출한다 (최선 노력)."""
    features: list[str] = []
    in_feature_section = False
    for line in text.splitlines():
        lower = line.lower().strip()
        if ("기능" in lower or "feature" in lower) and (
            lower.startswith("#") or lower.startswith("**")
        ):
            in_feature_section = True
            continue
        if in_feature_section:
            if line.strip().startswith("#") or (line.strip().startswith("**") and not line.strip().startswith("- **")):
                in_feature_section = False
                continue
            match = re.match(r"^\s*[-*]\s+(.+)", line)
            if match:
                features.append(match.group(1).strip())
    return features


def _extract_criteria(text: str) -> list[AcceptanceCriterion]:
    """마크다운에서 검증 기준 항목을 추출한다 (최선 노력)."""
    criteria: list[AcceptanceCriterion] = []
    in_criteria_section = False
    idx = 0
    for line in text.splitlines():
        lower = line.lower().strip()
        if (
            "검증" in lower or "기준" in lower or "criteria" in lower or "verification" in lower
        ) and (lower.startswith("#") or lower.startswith("**")):
            in_criteria_section = True
            continue
        if in_criteria_section:
            if line.strip().startswith("#") or (line.strip().startswith("**") and not line.strip().startswith("- **")):
                in_criteria_section = False
                continue
            match = re.match(r"^\s*[-*]\s+(.+)", line)
            if match:
                idx += 1
                criteria.append(AcceptanceCriterion(
                    id=f"ac-{idx:03d}",
                    description=match.group(1).strip(),
                ))
    return criteria
