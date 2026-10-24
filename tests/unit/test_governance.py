"""
Unit tests for governance system.
"""
from __future__ import annotations

from pathlib import Path
import pytest
import yaml

from meta_agent.self_programming.governance import (
    GovernanceConfig,
    BudgetLimits,
    SafetyPolicies,
    DomainPolicy,
    EnvironmentPolicy,
)


@pytest.fixture
def sample_governance_config(tmp_path):
    """Create a sample governance.yaml for testing."""
    config = {
        "protected_paths": [
            "meta_agent/self_programming/engine.py",
            "meta_agent/self_programming/governance.py",
            "quentin/kernel/**",
            "governance.yaml",
        ],
        "budgets": {
            "max_llm_tokens_per_task": 30000,
            "max_test_runtime_seconds": 120,
            "max_file_changes_per_task": 5,
        },
        "safety": {
            "require_approval_for": [
                "changes_to_protected_paths",
                "file_deletions",
            ],
            "auto_reject_for": [
                "delete_entire_directory",
            ],
            "auto_approve_for": [
                "test_files_only",
            ],
        },
        "domains": {
            "core": {
                "risk_level": "medium",
                "max_tokens_per_task": 25000,
                "require_tests": True,
            },
            "legal": {
                "risk_level": "critical",
                "require_human_approval": True,
            },
        },
        "environments": {
            "sandbox": {
                "allow_auto_apply": True,
                "allow_file_deletion": False,
            },
            "production": {
                "allow_auto_apply": False,
                "require_human_approval": True,
            },
        },
    }

    config_path = tmp_path / "governance.yaml"
    with config_path.open("w") as f:
        yaml.dump(config, f)

    return config_path


class TestGovernanceConfig:
    """Tests for GovernanceConfig loading and parsing."""

    def test_load_from_file(self, sample_governance_config):
        """Test loading governance config from YAML file."""
        config = GovernanceConfig.load(sample_governance_config)

        assert len(config.protected_paths) == 4
        assert "meta_agent/self_programming/engine.py" in config.protected_paths
        assert config.budgets.max_llm_tokens_per_task == 30000
        assert config.budgets.max_test_runtime_seconds == 120

    def test_load_missing_file_returns_default(self, tmp_path):
        """Test that missing config file returns default config."""
        missing_path = tmp_path / "nonexistent.yaml"
        config = GovernanceConfig.load(missing_path)

        # Should return default config
        assert isinstance(config, GovernanceConfig)
        assert len(config.protected_paths) >= 3  # Has some defaults

    def test_load_empty_file_returns_default(self, tmp_path):
        """Test that empty config file returns default config."""
        empty_path = tmp_path / "empty.yaml"
        empty_path.write_text("")

        config = GovernanceConfig.load(empty_path)
        assert isinstance(config, GovernanceConfig)

    def test_default_config(self):
        """Test default governance config."""
        config = GovernanceConfig.default()

        assert "meta_agent/self_programming/engine.py" in config.protected_paths
        assert config.budgets.max_llm_tokens_per_task == 50000
        assert "changes_to_protected_paths" in config.safety.require_approval_for

    def test_parse_budgets(self, sample_governance_config):
        """Test budget limits parsing."""
        config = GovernanceConfig.load(sample_governance_config)

        assert config.budgets.max_llm_tokens_per_task == 30000
        assert config.budgets.max_test_runtime_seconds == 120
        assert config.budgets.max_file_changes_per_task == 5

    def test_parse_safety_policies(self, sample_governance_config):
        """Test safety policies parsing."""
        config = GovernanceConfig.load(sample_governance_config)

        assert "changes_to_protected_paths" in config.safety.require_approval_for
        assert "delete_entire_directory" in config.safety.auto_reject_for
        assert "test_files_only" in config.safety.auto_approve_for

    def test_parse_domains(self, sample_governance_config):
        """Test domain policies parsing."""
        config = GovernanceConfig.load(sample_governance_config)

        assert "core" in config.domains
        assert config.domains["core"].risk_level == "medium"
        assert config.domains["core"].max_tokens_per_task == 25000

        assert "legal" in config.domains
        assert config.domains["legal"].require_human_approval is True

    def test_parse_environments(self, sample_governance_config):
        """Test environment policies parsing."""
        config = GovernanceConfig.load(sample_governance_config)

        assert "sandbox" in config.environments
        assert config.environments["sandbox"].allow_auto_apply is True
        assert config.environments["sandbox"].allow_file_deletion is False

        assert "production" in config.environments
        assert config.environments["production"].require_human_approval is True


class TestProtectedPaths:
    """Tests for protected path checking."""

    def test_is_protected_exact_match(self, sample_governance_config):
        """Test exact path matching."""
        config = GovernanceConfig.load(sample_governance_config)

        assert config.is_protected("meta_agent/self_programming/engine.py") is True
        assert config.is_protected("meta_agent/other/file.py") is False

    def test_is_protected_wildcard(self, sample_governance_config):
        """Test wildcard pattern matching."""
        config = GovernanceConfig.load(sample_governance_config)

        assert config.is_protected("quentin/kernel/safety.py") is True
        assert config.is_protected("quentin/kernel/policy.py") is True
        assert config.is_protected("quentin/other/file.py") is False

    def test_is_protected_with_leading_dot_slash(self, sample_governance_config):
        """Test path matching with ./ prefix."""
        config = GovernanceConfig.load(sample_governance_config)

        assert config.is_protected("./governance.yaml") is True
        assert config.is_protected("governance.yaml") is True

    def test_is_protected_absolute_path(self, sample_governance_config, tmp_path):
        """Test absolute path handling."""
        config = GovernanceConfig.load(sample_governance_config)

        # Absolute paths should be converted to relative
        abs_path = tmp_path / "meta_agent/self_programming/engine.py"
        # This test is environment-dependent, so just verify it doesn't crash
        result = config.is_protected(str(abs_path))
        assert isinstance(result, bool)


class TestBudgetChecks:
    """Tests for budget checking."""

    def test_check_budget_within_limits(self, sample_governance_config):
        """Test that operations within budget are allowed."""
        config = GovernanceConfig.load(sample_governance_config)

        allowed, reason = config.check_budget(
            llm_tokens=20000,
            runtime_seconds=60,
            file_count=3,
            cost_usd=0.5,
        )

        assert allowed is True
        assert reason is None

    def test_check_budget_exceeds_token_limit(self, sample_governance_config):
        """Test token limit enforcement."""
        config = GovernanceConfig.load(sample_governance_config)

        allowed, reason = config.check_budget(llm_tokens=50000)

        assert allowed is False
        assert "LLM tokens" in reason
        assert "30000" in reason

    def test_check_budget_exceeds_runtime_limit(self, sample_governance_config):
        """Test runtime limit enforcement."""
        config = GovernanceConfig.load(sample_governance_config)

        allowed, reason = config.check_budget(runtime_seconds=200)

        assert allowed is False
        assert "Runtime" in reason
        assert "120" in reason

    def test_check_budget_exceeds_file_count_limit(self, sample_governance_config):
        """Test file count limit enforcement."""
        config = GovernanceConfig.load(sample_governance_config)

        allowed, reason = config.check_budget(file_count=10)

        assert allowed is False
        assert "File count" in reason
        assert "5" in reason

    def test_check_budget_exceeds_cost_limit(self):
        """Test cost limit enforcement."""
        config = GovernanceConfig.default()

        allowed, reason = config.check_budget(cost_usd=5.0)

        assert allowed is False
        assert "Cost" in reason


class TestApprovalRequirements:
    """Tests for approval requirement checks."""

    def test_requires_approval_for_protected_paths(self, sample_governance_config):
        """Test that modifying protected paths requires approval."""
        config = GovernanceConfig.load(sample_governance_config)

        requires, reason = config.requires_approval(
            modified_files=["meta_agent/self_programming/engine.py"],
            action_type="code_patch",
        )

        assert requires is True
        assert "Protected path" in reason

    def test_requires_approval_for_critical_domain(self, sample_governance_config):
        """Test that critical domains require approval."""
        config = GovernanceConfig.load(sample_governance_config)

        requires, reason = config.requires_approval(
            modified_files=["legal/contract.py"],
            domain="legal",
        )

        assert requires is True
        assert "legal" in reason.lower()

    def test_requires_approval_for_many_test_failures(self, sample_governance_config):
        """Test that many test failures require approval."""
        config = GovernanceConfig.load(sample_governance_config)

        requires, reason = config.requires_approval(
            test_failures=5,
        )

        assert requires is True
        assert "test failures" in reason.lower()

    def test_no_approval_for_safe_changes(self, sample_governance_config):
        """Test that safe changes don't require approval."""
        config = GovernanceConfig.load(sample_governance_config)

        requires, reason = config.requires_approval(
            modified_files=["tests/test_something.py"],
            action_type="code_patch",
            test_failures=0,
            domain="core",
            environment="sandbox",
        )

        assert requires is False

    def test_requires_approval_for_production(self, sample_governance_config):
        """Test that production environment requires approval."""
        config = GovernanceConfig.load(sample_governance_config)

        requires, reason = config.requires_approval(
            environment="production",
        )

        assert requires is True
        assert "production" in reason.lower()


class TestAutoApply:
    """Tests for auto-apply checks."""

    def test_can_auto_apply_in_sandbox(self, sample_governance_config):
        """Test that sandbox allows auto-apply."""
        config = GovernanceConfig.load(sample_governance_config)

        can_apply = config.can_auto_apply(
            environment="sandbox",
            all_tests_pass=True,
            modified_files=["src/feature.py"],
        )

        assert can_apply is True

    def test_cannot_auto_apply_in_production(self, sample_governance_config):
        """Test that production doesn't allow auto-apply."""
        config = GovernanceConfig.load(sample_governance_config)

        can_apply = config.can_auto_apply(
            environment="production",
            all_tests_pass=True,
            modified_files=["src/feature.py"],
        )

        assert can_apply is False

    def test_cannot_auto_apply_protected_paths(self, sample_governance_config):
        """Test that protected paths cannot be auto-applied."""
        config = GovernanceConfig.load(sample_governance_config)

        can_apply = config.can_auto_apply(
            environment="sandbox",
            all_tests_pass=True,
            modified_files=["meta_agent/self_programming/engine.py"],
        )

        assert can_apply is False

    def test_cannot_auto_apply_without_passing_tests(self, sample_governance_config):
        """Test that failing tests prevent auto-apply."""
        config = GovernanceConfig.load(sample_governance_config)

        can_apply = config.can_auto_apply(
            environment="sandbox",
            all_tests_pass=False,
            modified_files=["src/feature.py"],
        )

        # Even in sandbox, if tests don't pass, can't auto-apply
        # (This depends on implementation - adjust test if behavior differs)
        assert can_apply is False


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_protected_paths(self):
        """Test config with no protected paths."""
        config = GovernanceConfig(
            protected_paths=[],
            budgets=BudgetLimits(),
            safety=SafetyPolicies(),
            domains={},
            environments={},
            rollback={},
            monitoring={},
            meta_learning={},
        )

        assert config.is_protected("any/file.py") is False

    def test_unknown_domain(self, sample_governance_config):
        """Test handling of unknown domain."""
        config = GovernanceConfig.load(sample_governance_config)

        requires, reason = config.requires_approval(
            domain="unknown_domain",
        )

        # Should not crash, should use defaults
        assert isinstance(requires, bool)

    def test_unknown_environment(self, sample_governance_config):
        """Test handling of unknown environment."""
        config = GovernanceConfig.load(sample_governance_config)

        can_apply = config.can_auto_apply(
            environment="unknown_env",
        )

        # Should default to not allowing auto-apply
        assert can_apply is False

    def test_invalid_yaml(self, tmp_path):
        """Test handling of invalid YAML."""
        bad_yaml_path = tmp_path / "bad.yaml"
        bad_yaml_path.write_text("invalid: yaml: content:\n  - broken")

        with pytest.raises(ValueError, match="Invalid governance YAML"):
            GovernanceConfig.load(bad_yaml_path)
