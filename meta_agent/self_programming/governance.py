"""
Governance system for self-programming.

Loads and enforces policies from governance.yaml including:
- Protected paths that cannot be modified
- Budget limits for LLM usage and runtime
- Safety policies for approval/rejection
- Domain and environment-specific rules
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from fnmatch import fnmatch

import yaml
try:
    import tiktoken  # type: ignore
except Exception:  # noqa: BLE001
    tiktoken = None

logger = logging.getLogger(__name__)


@dataclass
class BudgetLimits:
    """Budget limits from governance config."""
    max_llm_tokens_per_task: int = 50000
    max_llm_tokens_per_hour: int = 200000
    max_llm_tokens_per_day: int = 1000000
    max_test_runtime_seconds: int = 300
    max_pytest_cov_time_seconds: int = 60
    max_radon_time_seconds: int = 30
    max_file_changes_per_task: int = 10
    max_file_size_bytes: int = 100000
    max_usd_per_task: float = 1.0
    max_usd_per_day: float = 10.0
    llm_cost_per_1k_tokens: float = 0.0  # optional cost tracking


@dataclass
class SafetyPolicies:
    """Safety policies from governance config."""
    require_approval_for: List[str] = field(default_factory=list)
    auto_reject_for: List[str] = field(default_factory=list)
    auto_approve_for: List[str] = field(default_factory=list)


@dataclass
class DomainPolicy:
    """Policy for a specific domain."""
    risk_level: str = "medium"
    max_tokens_per_task: int = 30000
    require_tests: bool = True
    require_human_approval: bool = False


@dataclass
class EnvironmentPolicy:
    """Policy for a specific environment."""
    allow_auto_apply: bool = False
    allow_file_deletion: bool = False
    require_tests: bool = True
    require_human_approval: bool = False


@dataclass
class GovernanceConfig:
    """
    Complete governance configuration loaded from governance.yaml.

    Provides methods to check:
    - Is path protected?
    - Is action allowed?
    - Does task exceed budgets?
    """

    protected_paths: List[str]
    budgets: BudgetLimits
    safety: SafetyPolicies
    domains: Dict[str, DomainPolicy]
    environments: Dict[str, EnvironmentPolicy]
    rollback: Dict[str, Any]
    monitoring: Dict[str, Any]
    meta_learning: Dict[str, Any]

    @classmethod
    def load(cls, config_path: Path | str) -> "GovernanceConfig":
        """
        Load governance config from YAML file.

        Args:
            config_path: Path to governance.yaml

        Returns:
            GovernanceConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        path = Path(config_path)
        if not path.exists():
            logger.warning("Governance config not found at %s, using defaults", path)
            return cls.default()

        try:
            with path.open("r") as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning("Empty governance config, using defaults")
                return cls.default()

            # Parse budgets
            budget_data = data.get("budgets", {})
            budgets = BudgetLimits(
                max_llm_tokens_per_task=budget_data.get("max_llm_tokens_per_task", 50000),
                max_llm_tokens_per_hour=budget_data.get("max_llm_tokens_per_hour", 200000),
                max_llm_tokens_per_day=budget_data.get("max_llm_tokens_per_day", 1000000),
                max_test_runtime_seconds=budget_data.get("max_test_runtime_seconds", 300),
                max_pytest_cov_time_seconds=budget_data.get("max_pytest_cov_time_seconds", 60),
                max_radon_time_seconds=budget_data.get("max_radon_time_seconds", 30),
                max_file_changes_per_task=budget_data.get("max_file_changes_per_task", 10),
                max_file_size_bytes=budget_data.get("max_file_size_bytes", 100000),
                max_usd_per_task=budget_data.get("max_usd_per_task", 1.0),
                max_usd_per_day=budget_data.get("max_usd_per_day", 10.0),
                llm_cost_per_1k_tokens=budget_data.get("llm_cost_per_1k_tokens", 0.0),
            )

            # Parse safety policies
            safety_data = data.get("safety", {})
            safety = SafetyPolicies(
                require_approval_for=safety_data.get("require_approval_for", []),
                auto_reject_for=safety_data.get("auto_reject_for", []),
                auto_approve_for=safety_data.get("auto_approve_for", []),
            )

            # Parse domain policies
            domains_data = data.get("domains", {})
            domains = {}
            for domain_name, domain_config in domains_data.items():
                domains[domain_name] = DomainPolicy(
                    risk_level=domain_config.get("risk_level", "medium"),
                    max_tokens_per_task=domain_config.get("max_tokens_per_task", 30000),
                    require_tests=domain_config.get("require_tests", True),
                    require_human_approval=domain_config.get("require_human_approval", False),
                )

            # Parse environment policies
            envs_data = data.get("environments", {})
            environments = {}
            for env_name, env_config in envs_data.items():
                environments[env_name] = EnvironmentPolicy(
                    allow_auto_apply=env_config.get("allow_auto_apply", False),
                    allow_file_deletion=env_config.get("allow_file_deletion", False),
                    require_tests=env_config.get("require_tests", True),
                    require_human_approval=env_config.get("require_human_approval", False),
                )

            return cls(
                protected_paths=data.get("protected_paths", []),
                budgets=budgets,
                safety=safety,
                domains=domains,
                environments=environments,
                rollback=data.get("rollback", {}),
                monitoring=data.get("monitoring", {}),
                meta_learning=data.get("meta_learning", {}),
            )

        except yaml.YAMLError as e:
            logger.error("Failed to parse governance config: %s", e)
            raise ValueError(f"Invalid governance YAML: {e}")
        except Exception as e:
            logger.exception("Failed to load governance config")
            raise ValueError(f"Error loading governance: {e}")

    @classmethod
    def default(cls) -> "GovernanceConfig":
        """Return default governance config with minimal restrictions."""
        return cls(
            protected_paths=[
                "meta_agent/self_programming/engine.py",
                "meta_agent/self_programming/governance.py",
                "governance.yaml",
            ],
            budgets=BudgetLimits(
                max_llm_tokens_per_task=50000,
                max_llm_tokens_per_hour=200000,
                max_llm_tokens_per_day=1000000,
                max_test_runtime_seconds=300,
                max_pytest_cov_time_seconds=60,
                max_radon_time_seconds=30,
                max_file_changes_per_task=10,
                max_file_size_bytes=100000,
                max_usd_per_task=1.0,
                max_usd_per_day=10.0,
                llm_cost_per_1k_tokens=0.0,
            ),
            safety=SafetyPolicies(
                require_approval_for=["changes_to_protected_paths"],
                auto_reject_for=["delete_entire_directory"],
                auto_approve_for=["test_files_only"],
            ),
            domains={
                "core": DomainPolicy(risk_level="medium", max_tokens_per_task=30000),
            },
            environments={
                "sandbox": EnvironmentPolicy(allow_auto_apply=True),
            },
            rollback={},
            monitoring={},
            meta_learning={},
        )

    def is_protected(self, file_path: str) -> bool:
        """
        Check if a file path is protected from modification.

        Args:
            file_path: Relative or absolute file path

        Returns:
            True if path matches any protected pattern
        """
        # Normalize path to relative
        try:
            path_obj = Path(file_path)
            if path_obj.is_absolute():
                # Try to make relative to current dir
                try:
                    file_path = str(path_obj.relative_to(Path.cwd()))
                except ValueError:
                    # Can't make relative, use as-is
                    file_path = str(path_obj)
            else:
                file_path = str(path_obj)
        except Exception:
            pass  # Use file_path as-is

        # Check against all protected patterns
        for pattern in self.protected_paths:
            if fnmatch(file_path, pattern):
                return True
            # Also check with ./ prefix
            if fnmatch(f"./{file_path}", pattern):
                return True
            # Check if file_path starts with pattern (for directory protection)
            if file_path.startswith(pattern.rstrip("*/")):
                return True

        return False

    def estimate_tokens(self, text: str, model: str = "gpt-4") -> int:
        """
        Estimate tokens using tiktoken if available; fallback to rough heuristic.
        """
        try:
            if tiktoken is None:
                raise RuntimeError("tiktoken unavailable")
            enc = tiktoken.encoding_for_model(model)
            return len(enc.encode(text))
        except Exception:
            return max(1, len(text) // 4)

    def check_budget(
        self,
        *,
        llm_tokens: int = 0,
        runtime_seconds: float = 0,
        file_count: int = 0,
        cost_usd: float = 0,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if operation is within budget limits.

        Args:
            llm_tokens: Number of LLM tokens to use
            runtime_seconds: Expected runtime
            file_count: Number of files to modify
            cost_usd: Estimated cost in USD

        Returns:
            (allowed, reason) tuple
        """
        if llm_tokens > self.budgets.max_llm_tokens_per_task:
            return False, f"LLM tokens ({llm_tokens}) exceed limit ({self.budgets.max_llm_tokens_per_task})"

        if runtime_seconds > self.budgets.max_test_runtime_seconds:
            return False, f"Runtime ({runtime_seconds}s) exceeds limit ({self.budgets.max_test_runtime_seconds}s)"

        if file_count > self.budgets.max_file_changes_per_task:
            return False, f"File count ({file_count}) exceeds limit ({self.budgets.max_file_changes_per_task})"

        if cost_usd > self.budgets.max_usd_per_task:
            return False, f"Cost (${cost_usd}) exceeds limit (${self.budgets.max_usd_per_task})"

        return True, None

    def check_budget_for_text(self, text: str, model: str = "gpt-4") -> tuple[bool, Optional[str], int, float]:
        tokens = self.estimate_tokens(text, model=model)
        cost = 0.0
        if self.budgets.llm_cost_per_1k_tokens:
            cost = tokens / 1000.0 * self.budgets.llm_cost_per_1k_tokens
        ok, reason = self.check_budget(llm_tokens=tokens, cost_usd=cost)
        return ok, reason, tokens, cost

    def requires_approval(
        self,
        *,
        modified_files: List[str] = None,
        action_type: str = "",
        test_failures: int = 0,
        domain: str = "core",
        environment: str = "sandbox",
    ) -> tuple[bool, str]:
        """
        Check if an action requires human approval.

        Args:
            modified_files: List of files being modified
            action_type: Type of action (e.g., "code_patch", "file_deletion")
            test_failures: Number of test failures
            domain: Domain (core, legal, trading, etc.)
            environment: Environment (sandbox, staging, production)

        Returns:
            (requires_approval, reason) tuple
        """
        modified_files = modified_files or []

        # Check if any modified files are protected
        for file_path in modified_files:
            if self.is_protected(file_path):
                return True, f"Protected path: {file_path}"

        # Check auto-reject conditions
        for condition in self.safety.auto_reject_for:
            if condition in action_type:
                return True, f"Auto-reject condition: {condition}"

        # Check domain policy
        domain_policy = self.domains.get(domain)
        if domain_policy and domain_policy.require_human_approval:
            return True, f"Domain '{domain}' requires approval"

        # Check environment policy
        env_policy = self.environments.get(environment)
        if env_policy and env_policy.require_human_approval:
            return True, f"Environment '{environment}' requires approval"

        # Check test failures
        if test_failures > 3:
            return True, f"Too many test failures: {test_failures}"

        # Check approval requirements
        for condition in self.safety.require_approval_for:
            if condition == "changes_to_protected_paths" and any(
                self.is_protected(f) for f in modified_files
            ):
                return True, "Changes to protected paths"
            if condition == "file_deletions" and "deletion" in action_type.lower():
                return True, "File deletion"

        return False, "Auto-approved"

    def can_auto_apply(
        self,
        *,
        environment: str = "sandbox",
        all_tests_pass: bool = False,
        modified_files: List[str] = None,
    ) -> bool:
        """
        Check if changes can be auto-applied without review.

        Args:
            environment: Environment (sandbox, staging, production)
            all_tests_pass: Whether all tests passed
            modified_files: List of modified files

        Returns:
            True if can auto-apply
        """
        modified_files = modified_files or []

        # Check environment policy
        env_policy = self.environments.get(environment, EnvironmentPolicy())
        if not env_policy.allow_auto_apply:
            return False

        # Check if any files are protected
        if any(self.is_protected(f) for f in modified_files):
            return False

        # If all tests pass and in sandbox, allow auto-apply
        if all_tests_pass and environment == "sandbox":
            return True

        return False
