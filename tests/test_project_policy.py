"""project_policy.py 단위 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness.context.project_policy import ProjectPolicy, ProjectPolicyManager

if TYPE_CHECKING:
    from pathlib import Path


class TestProjectPolicy:
    def test_default_values(self) -> None:
        policy = ProjectPolicy()
        assert policy.review_language == "ko"
        assert "ruff" in policy.required_checks
        assert "mypy" in policy.required_checks
        assert "pytest" in policy.required_checks
        assert "structure" in policy.required_checks

    def test_to_yaml_and_back(self) -> None:
        policy = ProjectPolicy(
            project_name="test-project",
            language="python",
            python_version="3.11+",
        )
        yaml_str = policy.to_yaml()
        assert "test-project" in yaml_str
        assert "python" in yaml_str

    def test_from_dict(self) -> None:
        data = {
            "project": {"name": "my-proj", "language": "python", "python_version": "3.12"},
            "policies": {
                "review_language": "en",
                "required_checks": ["ruff"],
                "conventions": {"source": "custom.yaml"},
                "adr": {"directory": "adrs/"},
                "structure": {"source": "rules.yaml"},
                "artifacts": {"design_intent": False},
                "custom_rules": {"max_complexity": 10},
            },
        }
        policy = ProjectPolicy.from_dict(data)
        assert policy.project_name == "my-proj"
        assert policy.review_language == "en"
        assert policy.required_checks == ["ruff"]
        assert policy.conventions_source == "custom.yaml"
        assert policy.adr_directory == "adrs/"
        assert policy.custom_rules == {"max_complexity": 10}

    def test_from_dict_with_defaults(self) -> None:
        policy = ProjectPolicy.from_dict({})
        assert policy.project_name == ""
        assert policy.review_language == "ko"
        assert len(policy.required_checks) == 4
        assert policy.external_adr_sources == []

    def test_from_dict_with_external_adr_sources(self) -> None:
        data = {
            "policies": {
                "adr": {
                    "directory": "docs/adr/",
                    "external_sources": ["/path/to/other/docs/adr", "~/projects/shared/adr"],
                },
            },
        }
        policy = ProjectPolicy.from_dict(data)
        assert policy.external_adr_sources == ["/path/to/other/docs/adr", "~/projects/shared/adr"]

    def test_to_yaml_includes_external_adr_sources(self) -> None:
        policy = ProjectPolicy(external_adr_sources=["/ext/adr"])
        yaml_str = policy.to_yaml()
        assert "/ext/adr" in yaml_str
        assert "external_sources" in yaml_str


class TestProjectPolicyManager:
    def test_load_returns_default_when_no_file(self, tmp_path: Path) -> None:
        mgr = ProjectPolicyManager(tmp_path)
        policy = mgr.load()
        assert policy.review_language == "ko"
        assert not mgr.exists()

    def test_save_and_load(self, tmp_path: Path) -> None:
        mgr = ProjectPolicyManager(tmp_path)
        policy = ProjectPolicy(project_name="saved", language="python")
        mgr.save(policy)

        assert mgr.exists()

        mgr.invalidate_cache()
        loaded = mgr.load()
        assert loaded.project_name == "saved"
        assert loaded.language == "python"
        assert list(mgr.policy_path.parent.glob(".policy-*.tmp")) == []

    def test_load_non_mapping_uses_default(self, tmp_path: Path) -> None:
        mgr = ProjectPolicyManager(tmp_path)
        mgr.policy_path.parent.mkdir(parents=True)
        mgr.policy_path.write_text("- not\n- mapping\n", encoding="utf-8")

        policy = mgr.load()

        assert policy.review_language == "ko"

    def test_init_default_creates_file(self, tmp_path: Path) -> None:
        mgr = ProjectPolicyManager(tmp_path)
        policy = mgr.init_default(project_name="init-test", language="python")

        assert mgr.exists()
        assert policy.project_name == "init-test"

    def test_init_default_returns_existing(self, tmp_path: Path) -> None:
        mgr = ProjectPolicyManager(tmp_path)
        mgr.save(ProjectPolicy(project_name="existing"))

        policy = mgr.init_default(project_name="new-name")
        assert policy.project_name == "existing"

    def test_caching(self, tmp_path: Path) -> None:
        mgr = ProjectPolicyManager(tmp_path)
        p1 = mgr.load()
        p2 = mgr.load()
        assert p1 is p2

    def test_invalidate_cache(self, tmp_path: Path) -> None:
        mgr = ProjectPolicyManager(tmp_path)
        p1 = mgr.load()
        mgr.invalidate_cache()
        p2 = mgr.load()
        assert p1 is not p2

    def test_policy_path(self, tmp_path: Path) -> None:
        mgr = ProjectPolicyManager(tmp_path)
        assert mgr.policy_path == tmp_path / ".harness" / "project-policy.yaml"
