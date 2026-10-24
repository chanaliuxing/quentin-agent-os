# tests/unit/test_self_programming_offline_safety.py

import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from meta_agent.self_programming.engine_v2 import SelfProgrammingEngineV2, SelfProgrammingConfig, GapLike, CouncilDecision
from meta_agent.tools.coder.base import CodeGenerationResult

@pytest.mark.asyncio
async def test_deterministic_target_file_safety():
    # Force deterministic backend
    config = SelfProgrammingConfig(allow_auto_apply=False)
    engine = SelfProgrammingEngineV2(config=config)
    
    gap = GapLike(
        id="test_gap",
        title="Test Gap",
        description="A test gap",
        category="core",
        priority=1,
        target_file="quentin/cognitive/loop_impl.py" # UNSAFE TARGET
    )
    
    # Mock components to avoid real calls
    with (
        patch("meta_agent.tools.coder.router.coder_router.generate") as mock_gen,
        patch("meta_agent.self_programming.engine_v2.build_status_snapshot"),
        patch("meta_agent.self_programming.engine_v2.build_context_chunks"),
        patch("meta_agent.self_programming.test_runner.SandboxTestRunner.run_in_sandbox") as mock_sandbox,
        patch("meta_agent.self_programming.engine_v2.PatchGovernanceCouncil.decide_on_patch") as mock_council,
        patch("meta_agent.patches.store.PatchStore.save_patch"),
        patch("quentin.self_programming.skill_evaluator.PatchEvaluator.evaluate"),
        patch("meta_agent.self_programming.engine_v2.SelfProgrammingEngineV2._run_static_checks") as mock_static
    ):
        
        mock_gen.return_value = CodeGenerationResult(success=True, code='{"implementation_code": "pass", "verification_test_code": "pass"}')
        mock_sandbox.return_value = {"success": True, "stdout": "", "stderr": ""}
        mock_council.return_value = CouncilDecision(should_apply=True, risk_level="low", reason="ok")
        mock_static.return_value = (True, "")
        
        # Let's test the logic by calling _run_for_single_gap directly
        snapshot = MagicMock()
        await engine._run_for_single_gap(gap, backend="deterministic", snapshot=snapshot)
        
        # Check SandboxTestRunner.run_in_sandbox call
        assert mock_sandbox.called
        args, kwargs = mock_sandbox.call_args
        # args[2] is target_file_path
        target_file_used = str(args[2])
        assert target_file_used.startswith("quentin/mutable/")
        assert "deterministic_test_gap.py" in target_file_used

@pytest.mark.asyncio
async def test_proposal_only_mode_no_merge():
    config = SelfProgrammingConfig(allow_auto_apply=False, proposal_only=True)
    engine = SelfProgrammingEngineV2(config=config)
    engine.git = MagicMock(enabled=True)
    
    gap = GapLike(id="test_gap", title="T", description="D", category="C", priority=1)
    
    with (
        patch("meta_agent.tools.coder.router.coder_router.generate") as mock_gen,
        patch("meta_agent.self_programming.engine_v2.build_status_snapshot"),
        patch("meta_agent.self_programming.engine_v2.build_context_chunks"),
        patch("meta_agent.self_programming.test_runner.SandboxTestRunner.run_in_sandbox") as mock_sandbox,
        patch("meta_agent.self_programming.engine_v2.PatchGovernanceCouncil.decide_on_patch") as mock_council,
        patch("meta_agent.patches.store.PatchStore.save_patch"),
        patch("quentin.self_programming.skill_evaluator.PatchEvaluator.evaluate"),
        patch("meta_agent.patches.safe_applier.SafePatchApplier.apply_patch") as mock_apply,
        patch("meta_agent.self_programming.engine_v2.SelfProgrammingEngineV2._run_static_checks") as mock_static
    ):
        
        mock_gen.return_value = CodeGenerationResult(success=True, code='{"implementation_code": "pass", "verification_test_code": "pass"}')
        mock_sandbox.return_value = {"success": True, "stdout": "", "stderr": ""}
        mock_council.return_value = CouncilDecision(should_apply=True, risk_level="low", reason="ok")
        mock_static.return_value = (True, "")
        
        await engine._run_for_single_gap(gap, backend="deterministic", snapshot=MagicMock())
        
        # apply_patch should NOT be called
        mock_apply.assert_not_called()
        # finalize_success should NOT be called
        engine.git.finalize_success.assert_not_called()
        # cleanup_sandbox SHOULD be called
        engine.git.cleanup_sandbox.assert_called()