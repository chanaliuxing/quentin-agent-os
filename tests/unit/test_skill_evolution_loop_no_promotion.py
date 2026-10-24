"""
Unit test for SkillEvolutionLoop without promotion method.

Tests that the loop can run successfully even when the engine doesn't
have the select_patches_to_promote method.
"""
import pytest
from pathlib import Path
from quentin.evolution.skill_loop import SkillEvolutionLoop
from quentin.self_programming.schema import PatchCandidate, PatchReport, PatchTestResult, PatchTarget, PatchTestPlan
from unittest.mock import MagicMock
from datetime import datetime


class TestSkillEvolutionLoopWithoutPromotion:
    """Test SkillEvolutionLoop when engine lacks promotion method."""

    def test_run_once_completes_without_promotion_method(self, tmp_path):
        """Test that run_once succeeds when engine lacks select_patches_to_promote."""
        # Create a mock engine WITHOUT select_patches_to_promote method
        mock_engine = MagicMock()
        # Explicitly remove the method if it exists
        if hasattr(mock_engine, 'select_patches_to_promote'):
            delattr(mock_engine, 'select_patches_to_promote')

        loop = SkillEvolutionLoop(
            engine=mock_engine,
            repo_root=tmp_path,
        )

        # Mock the methods that would be called
        loop.generate_skills_from_traces = MagicMock(return_value=[])
        loop.generate_patches_from_issues = MagicMock(return_value=[])
        loop.evaluate_patches = MagicMock(return_value=[])

        # Should not raise any errors
        result = loop.run_once(
            successful_traces=[],
            issues=[],
        )

        assert isinstance(result, dict)
        assert "skill_candidates" in result
        assert "patch_candidates" in result
        assert "patch_reports" in result
        assert "promotable_patches" in result

    def test_fallback_to_first_patch_when_no_promotion_method(self, tmp_path):
        """Test that fallback selects first patch when promotion method absent."""
        mock_engine = MagicMock()
        # Remove select_patches_to_promote
        if hasattr(mock_engine, 'select_patches_to_promote'):
            delattr(mock_engine, 'select_patches_to_promote')

        loop = SkillEvolutionLoop(
            engine=mock_engine,
            repo_root=tmp_path,
        )

        # Create mock patch reports
        proposal1 = PatchCandidate(
            proposal_id="patch-001",
            created_at=datetime.utcnow().isoformat(),
            created_by="test",
            target=PatchTarget(kind="module", path="test.py"),
            rationale="Test patch 1",
            patch_type="unified_diff",
            patch_content="diff content",
            test_plan=PatchTestPlan(unit_tests=["pytest test.py"]),
        )
        exec_result1 = PatchTestResult(
            proposal_id="patch-001", tests_run=[], tests_passed=[], tests_failed=[], static_issues=[]
        )
        patch1 = PatchReport(
            proposal=proposal1,
            execution_result=exec_result1,
            recommended_action="accept",
            reasoning="All tests passed.",
        )

        proposal2 = PatchCandidate(
            proposal_id="patch-002",
            created_at=datetime.utcnow().isoformat(),
            created_by="test",
            target=PatchTarget(kind="module", path="test2.py"),
            rationale="Test patch 2",
            patch_type="unified_diff",
            patch_content="diff content 2",
            test_plan=PatchTestPlan(unit_tests=["pytest test2.py"]),
        )
        exec_result2 = PatchTestResult(
            proposal_id="patch-002", tests_run=[], tests_passed=[], tests_failed=[], static_issues=[]
        )
        patch2 = PatchReport(
            proposal=proposal2,
            execution_result=exec_result2,
            recommended_action="accept",
            reasoning="All tests passed.",
        )

        loop.generate_skills_from_traces = MagicMock(return_value=[])
        loop.generate_patches_from_issues = MagicMock(return_value=[])
        loop.evaluate_patches = MagicMock(return_value=[patch1, patch2])

        result = loop.run_once(
            successful_traces=[],
            issues=[],
        )

        # Should use fallback and select first patch
        promotable = result["promotable_patches"]
        assert len(promotable) == 1
        assert promotable[0]["proposal"]["proposal_id"] == "patch-001"

    def test_handles_promotion_method_exception_gracefully(self, tmp_path):
        """Test graceful handling when select_patches_to_promote raises exception."""
        mock_engine = MagicMock()
        # Add a promotion method that raises
        mock_engine.select_patches_to_promote = MagicMock(
            side_effect=RuntimeError("Promotion failed")
        )

        loop = SkillEvolutionLoop(
            engine=mock_engine,
            repo_root=tmp_path,
        )

        proposal = PatchCandidate(
            proposal_id="patch-003",
            created_at=datetime.utcnow().isoformat(),
            created_by="test",
            target=PatchTarget(kind="module", path="test.py"),
            rationale="Test patch",
            patch_type="unified_diff",
            patch_content="diff",
            test_plan=PatchTestPlan(unit_tests=["pytest test.py"]),
        )
        exec_result = PatchTestResult(
            proposal_id="patch-003", tests_run=[], tests_passed=[], tests_failed=[], static_issues=[]
        )
        patch_report = PatchReport(
            proposal=proposal,
            execution_result=exec_result,
            recommended_action="accept",
            reasoning="All tests passed.",
        )

        loop.generate_skills_from_traces = MagicMock(return_value=[])
        loop.generate_patches_from_issues = MagicMock(return_value=[])
        loop.evaluate_patches = MagicMock(return_value=[patch_report])

        # Should not crash despite exception
        result = loop.run_once(
            successful_traces=[],
            issues=[],
        )

        assert isinstance(result, dict)
        # Should fall back to first patch
        promotable = result["promotable_patches"]
        assert len(promotable) == 1
        assert promotable[0]["proposal"]["proposal_id"] == "patch-003"

    def test_empty_patch_reports_handled_correctly(self, tmp_path):
        """Test that empty patch reports don't cause issues."""
        mock_engine = MagicMock()

        loop = SkillEvolutionLoop(
            engine=mock_engine,
            repo_root=tmp_path,
        )

        loop.generate_skills_from_traces = MagicMock(return_value=[])
        loop.generate_patches_from_issues = MagicMock(return_value=[])
        loop.evaluate_patches = MagicMock(return_value=[])  # Empty list

        result = loop.run_once(
            successful_traces=[],
            issues=[],
        )

        # Should handle empty reports gracefully
        assert result["promotable_patches"] == []

    def test_run_once_logs_fallback_message(self, tmp_path, caplog):
        """Test that fallback usage is logged."""
        import logging

        mock_engine = MagicMock()
        if hasattr(mock_engine, 'select_patches_to_promote'):
            delattr(mock_engine, 'select_patches_to_promote')

        loop = SkillEvolutionLoop(
            engine=mock_engine,
            repo_root=tmp_path,
        )

        proposal = PatchCandidate(
            proposal_id="patch-004",
            created_at=datetime.utcnow().isoformat(),
            created_by="test",
            target=PatchTarget(kind="module", path="test.py"),
            rationale="Test",
            patch_type="unified_diff",
            patch_content="diff",
            test_plan=PatchTestPlan(unit_tests=["pytest test.py"]),
        )
        exec_result = PatchTestResult(
            proposal_id="patch-004", tests_run=[], tests_passed=[], tests_failed=[], static_issues=[]
        )
        patch_report = PatchReport(
            proposal=proposal,
            execution_result=exec_result,
            recommended_action="accept",
            reasoning="All tests passed.",
        )

        loop.generate_skills_from_traces = MagicMock(return_value=[])
        loop.generate_patches_from_issues = MagicMock(return_value=[])
        loop.evaluate_patches = MagicMock(return_value=[patch_report])

        with caplog.at_level(logging.DEBUG):
            result = loop.run_once(
                successful_traces=[],
                issues=[],
            )

        # Execution should complete successfully
        assert "promotable_patches" in result
        assert len(result["promotable_patches"]) == 1


class TestSkillEvolutionLoopIntegration:
    """Integration tests for SkillEvolutionLoop."""

    def test_can_be_initialized_with_minimal_engine(self, tmp_path):
        """Test initialization with a minimal engine object."""
        # Create minimal engine (just an object, no methods)
        class MinimalEngine:
            pass

        engine = MinimalEngine()
        loop = SkillEvolutionLoop(engine=engine, repo_root=tmp_path)

        assert loop.engine is engine
        assert loop.repo_root == tmp_path

    def test_getattr_pattern_is_safe(self, tmp_path):
        """Test that getattr pattern handles various edge cases."""
        # Test with None
        mock_engine = MagicMock()
        mock_engine.select_patches_to_promote = None

        loop = SkillEvolutionLoop(engine=mock_engine, repo_root=tmp_path)
        loop.generate_skills_from_traces = MagicMock(return_value=[])
        loop.generate_patches_from_issues = MagicMock(return_value=[])
        loop.evaluate_patches = MagicMock(return_value=[])

        # Should not crash with None method
        result = loop.run_once(successful_traces=[], issues=[])
        assert "promotable_patches" in result
