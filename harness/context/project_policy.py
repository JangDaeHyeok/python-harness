"""프로젝트별 정책 파일 관리.

.harness/project-policy.yaml을 통해 프로젝트별 하네스 동작을 커스터마이즈한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from harness.tools.file_io import atomic_write_text

logger = logging.getLogger(__name__)

POLICY_FILENAME = "project-policy.yaml"
DEFAULT_POLICY_PATH = Path(".harness") / POLICY_FILENAME


@dataclass
class ProjectPolicy:
    """프로젝트 정책 데이터."""

    project_name: str = ""
    language: str = ""
    python_version: str = ""
    review_language: str = "ko"
    required_checks: list[str] = field(
        default_factory=lambda: ["ruff", "mypy", "pytest", "structure"]
    )
    conventions_source: str = "docs/code-convention.yaml"
    adr_directory: str = "docs/adr/"
    structure_source: str = "harness_structure.yaml"
    artifacts_enabled: dict[str, bool] = field(default_factory=lambda: {
        "design_intent": True,
        "code_quality_guide": True,
        "review_comments": True,
        "pr_body": True,
    })
    custom_rules: dict[str, Any] = field(default_factory=dict)

    def to_yaml(self) -> str:
        """정책을 YAML 문자열로 변환한다."""
        data: dict[str, Any] = {
            "project": {
                "name": self.project_name,
                "language": self.language,
            },
            "policies": {
                "review_language": self.review_language,
                "required_checks": self.required_checks,
                "conventions": {"source": self.conventions_source},
                "adr": {"directory": self.adr_directory},
                "structure": {"source": self.structure_source},
                "artifacts": self.artifacts_enabled,
            },
        }
        if self.python_version:
            data["project"]["python_version"] = self.python_version
        if self.custom_rules:
            data["policies"]["custom_rules"] = self.custom_rules
        return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectPolicy:
        """딕셔너리에서 정책을 생성한다."""
        project = data.get("project", {})
        policies = data.get("policies", {})
        conventions = policies.get("conventions", {})
        adr = policies.get("adr", {})
        structure = policies.get("structure", {})

        return cls(
            project_name=str(project.get("name", "")),
            language=str(project.get("language", "")),
            python_version=str(project.get("python_version", "")),
            review_language=str(policies.get("review_language", "ko")),
            required_checks=list(policies.get("required_checks", ["ruff", "mypy", "pytest", "structure"])),
            conventions_source=str(conventions.get("source", "docs/code-convention.yaml")),
            adr_directory=str(adr.get("directory", "docs/adr/")),
            structure_source=str(structure.get("source", "harness_structure.yaml")),
            artifacts_enabled=dict(policies.get("artifacts", {
                "design_intent": True,
                "code_quality_guide": True,
                "review_comments": True,
                "pr_body": True,
            })),
            custom_rules=dict(policies.get("custom_rules", {})),
        )


class ProjectPolicyManager:
    """프로젝트 정책 파일을 관리한다."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self._policy_path = self.project_dir / DEFAULT_POLICY_PATH
        self._cached: ProjectPolicy | None = None

    @property
    def policy_path(self) -> Path:
        return self._policy_path

    def exists(self) -> bool:
        return self._policy_path.exists()

    def load(self) -> ProjectPolicy:
        """정책 파일을 로드한다. 없으면 기본 정책을 반환한다."""
        if self._cached is not None:
            return self._cached
        if not self._policy_path.exists():
            self._cached = ProjectPolicy()
            return self._cached
        try:
            content = self._policy_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content) or {}
            if not isinstance(data, dict):
                raise ValueError("프로젝트 정책 YAML 최상위 값은 매핑이어야 합니다.")
            self._cached = ProjectPolicy.from_dict(data)
            logger.info("프로젝트 정책 로드 완료: %s", self._policy_path)
            return self._cached
        except (OSError, ValueError, yaml.YAMLError, TypeError, AttributeError) as e:
            logger.warning("프로젝트 정책 파싱 실패: %s — 기본 정책 사용", e)
            self._cached = ProjectPolicy()
            return self._cached

    def save(self, policy: ProjectPolicy) -> Path:
        """정책 파일을 저장한다."""
        self._policy_path.parent.mkdir(parents=True, exist_ok=True)
        content = policy.to_yaml()
        atomic_write_text(self._policy_path, content, prefix=".policy-")
        self._cached = policy
        logger.info("프로젝트 정책 저장 완료: %s", self._policy_path)
        return self._policy_path

    def init_default(self, project_name: str = "", language: str = "python") -> ProjectPolicy:
        """기본 정책 파일을 생성한다. 이미 존재하면 기존 정책을 반환한다."""
        if self.exists():
            return self.load()
        policy = ProjectPolicy(
            project_name=project_name,
            language=language,
            python_version="3.11+",
        )
        self.save(policy)
        return policy

    def invalidate_cache(self) -> None:
        """캐시를 무효화한다."""
        self._cached = None
