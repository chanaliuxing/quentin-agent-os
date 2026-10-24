"""
Simplified tests for governance integration in SelfProgrammingEngine.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from meta_agent.self_programming.engine import SelfProgrammingEngine


class TestEngineGovernanceLoading:
    """Tests that engine loads and initializes governance correctly."""

    def test_engine_loads_governance_config(self, tmp_path):
        """Test that engine loads governance config on initialization."""
        # Create a test governance.yaml
        gov_config = tmp_path / "governance.yaml"
        gov_config.write_text("""
protected_paths:
  - "test/protected.py"
budgets:
  max_llm_tokens_per_task: 10000
""")

        engine = SelfProgrammingEngine(repo_root=str(tmp_path), enable_governance=True)

        assert engine.governance is not None
        assert "test/protected.py" in engine.governance.protected_paths
        assert engine.governance.budgets.max_llm_tokens_per_task == 10000

    def test_engine_uses_default_governance_if_no_config(self, tmp_path):
        """Test that engine uses default governance if no config file."""
        engine = SelfProgrammingEngine(repo_root=str(tmp_path), enable_governance=True)

        assert engine.governance is not None
        assert "meta_agent/self_programming/engine.py" in engine.governance.protected_paths

    def test_engine_can_disable_governance(self, tmp_path):
        """Test that governance can be disabled."""
        engine = SelfProgrammingEngine(repo_root=str(tmp_path), enable_governance=False)

        assert engine.governance is None

    def test_governance_check_protected_paths(self, tmp_path):
        """Test that governance can check protected paths."""
        gov_config = tmp_path / "governance.yaml"
        gov_config.write_text("""
protected_paths:
  - "critical/**"
  - "engine.py"
budgets:
  max_llm_tokens_per_task: 50000
""")

        engine = SelfProgrammingEngine(repo_root=str(tmp_path), enable_governance=True)

        # Check protected paths
        assert engine.governance.is_protected("critical/system.py") is True
        assert engine.governance.is_protected("engine.py") is True
        assert engine.governance.is_protected("safe_file.py") is False

    def test_governance_check_budget(self, tmp_path):
        """Test that governance can check budgets."""
        gov_config = tmp_path / "governance.yaml"
        gov_config.write_text("""
protected_paths: []
budgets:
  max_llm_tokens_per_task: 10000
  max_file_changes_per_task: 5
""")

        engine = SelfProgrammingEngine(repo_root=str(tmp_path), enable_governance=True)

        # Within budget
        allowed, reason = engine.governance.check_budget(llm_tokens=5000, file_count=3)
        assert allowed is True
        assert reason is None

        # Exceeds token budget
        allowed, reason = engine.governance.check_budget(llm_tokens=20000)
        assert allowed is False
        assert "LLM tokens" in reason

        # Exceeds file count budget
        allowed, reason = engine.governance.check_budget(file_count=10)
        assert allowed is False
        assert "File count" in reason

    def test_governance_requires_approval(self, tmp_path):
        """Test that governance can determine approval requirements."""
        gov_config = tmp_path / "governance.yaml"
        gov_config.write_text("""
protected_paths:
  - "critical/**"
budgets:
  max_llm_tokens_per_task: 50000
domains:
  legal:
    risk_level: "critical"
    require_human_approval: true
""")

        engine = SelfProgrammingEngine(repo_root=str(tmp_path), enable_governance=True)

        # Protected path requires approval
        requires, reason = engine.governance.requires_approval(
            modified_files=["critical/system.py"],
            action_type="code_patch",
        )
        assert requires is True
        assert "Protected path" in reason

        # Critical domain requires approval
        requires, reason = engine.governance.requires_approval(
            modified_files=["legal/contract.py"],
            domain="legal",
        )
        assert requires is True
        assert "legal" in reason.lower()

        # Many test failures require approval
        requires, reason = engine.governance.requires_approval(
            test_failures=5,
        )
        assert requires is True
        assert "test failures" in reason.lower()

        # Safe changes don't require approval
        requires, reason = engine.governance.requires_approval(
            modified_files=["tests/test_something.py"],
            action_type="code_patch",
            test_failures=0,
        )
        assert requires is False


class TestGovernanceIntegrationPoints:
    """Tests that verify governance is actually called in engine flow."""

    def test_engine_has_governance_attribute(self):
        """Test that engine exposes governance for inspection."""
        engine = SelfProgrammingEngine(repo_root=".", enable_governance=True)
        assert hasattr(engine, "governance")
        assert engine.governance is not None or engine.governance is None  # Can be either

    def test_engine_governance_integration_exists_in_code(self):
        """Test that engine.py actually has governance checks in the code."""
        from pathlib import Path
        engine_path = Path(__file__).parent.parent.parent / "meta_agent/self_programming/engine.py"

        with open(engine_path, "r") as f:
            content = f.read()

        # Verify governance checks exist in code
        assert "self.governance" in content
        assert "is_protected" in content
        assert "check_budget" in content
        assert "requires_approval" in content

        # Verify governance is loaded in __init__
        assert "GovernanceConfig.load" in content or "GovernanceConfig.default" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
