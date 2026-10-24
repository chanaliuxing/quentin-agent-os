import asyncio
import logging
import sys
from pathlib import Path
import json # Added for MockCoderRouter
import re # Added for MockCoderRouter
from unittest.mock import patch # Added for mocking coder_router

# Add repo root to sys.path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from meta_agent.self_programming.engine_v2 import SelfProgrammingEngineV2, GapLike, SelfProgrammingConfig
from meta_agent.patches.models import PatchProposal
from meta_agent.patches.safe_applier import SafePatchApplier
from quentin.self_programming.skill_evaluator import PatchEvaluator
from meta_agent.self_programming.engine_v2 import PatchGovernanceCouncil
from meta_agent.skills.registry import SkillRegistry
from meta_agent.skills.router import SkillRouter
from meta_agent.research.tool import ResearchTool
from meta_agent.tools.coder.base import CodeGenerationResult, CodeGenerationRequest # Added for MockCoderRouter
from meta_agent.tools.coder.router import coder_router # The actual router to patch

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/end_to_end_demo.log")
    ]
)
logger = logging.getLogger("EndToEndDemo")

# --- Mock CoderRouter (copied from conftest.py) ---
class MockCoderRouter:
    def __init__(self):
        self._responses = {}

    def add_response(self, gap_id: str, implementation_code: str, verification_test_code: str, success: bool = True, reasoning: str = "Mocked success"):
        json_output = {
            "implementation_code": implementation_code,
            "verification_test_code": verification_test_code
        }
        self._responses[gap_id] = CodeGenerationResult(
            success=success,
            code=json.dumps(json_output), # The engine expects a JSON string
            reasoning=reasoning
        )

    def generate(self, request: CodeGenerationRequest, backend_name: str) -> CodeGenerationResult:
        # Assuming the gap_id is part of the request.goal
        gap_id_match = re.search(r"gap: (gap_demo_001)", request.goal)
        gap_id = gap_id_match.group(1) if gap_id_match else None
        
        if gap_id in self._responses:
            return self._responses[gap_id]
        
        # Default failure for unmocked gaps
        return CodeGenerationResult(
            success=False,
            code="{}",
            reasoning=f"No mock response for gap_id: {gap_id}"
        )

# --- End Mock CoderRouter ---


async def main():
    logger.info("Starting End-to-End Demo...")

    # 1. Initialize components
    config = SelfProgrammingConfig(
        default_coder_backend="codex_cli", 
        enable_research=False, 
        max_gaps_per_cycle=1,
        allow_auto_apply=True, 
        max_retries=1 
    )
    
    # Initialize MockCoderRouter and patch the global coder_router
    mock_cr = MockCoderRouter()
    mock_cr.add_response(
        gap_id="gap_demo_001",
        implementation_code="""
# quentin/mutable/math_utils.py
def calculate_fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    else:
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b
""",
        verification_test_code="""
# tests/temp_test.py
import pytest
from quentin.mutable.math_utils import calculate_fibonacci

def test_calculate_fibonacci_zero():
    assert calculate_fibonacci(0) == 0

def test_calculate_fibonacci_one():
    assert calculate_fibonacci(1) == 1

def test_calculate_fibonacci_positive():
    assert calculate_fibonacci(2) == 1
    assert calculate_fibonacci(3) == 2
    assert calculate_fibonacci(4) == 3
    assert calculate_fibonacci(5) == 5
    assert calculate_fibonacci(10) == 55
"""
    )
    # Patch the actual coder_router.generate method
    with patch('meta_agent.tools.coder.router.coder_router.generate', side_effect=mock_cr.generate):
        # We rely on the default components which we've been patching
        engine = SelfProgrammingEngineV2(config=config)
        
        # 2. Inject Artificial Gap
        gap = GapLike(
            id="gap_demo_001",
            title="Missing Math Utility",
            description="We need a new utility function `calculate_fibonacci(n: int) -> int` in `quentin/mutable/math_utils.py`. It should compute the nth Fibonacci number efficiently.",
            category="missing_feature",
            priority=1
        )
        logger.info(f"Injected Gap: {gap}")

        # 3. Trigger Self-Programming
        logger.info("Triggering Self-Programming Engine...")
        
        try:
            await engine._run_for_gaps_async([gap])
            logger.info("Self-Programming Cycle Completed.")
        except Exception as e:
            logger.error(f"Self-Programming Cycle Failed: {e}", exc_info=True)

    # 4. Verify Results
    logger.info("Demo finished. Please check 'logs/self_programming_engine_v2.jsonl' and 'logs/end_to_end_demo.log' for details.")

if __name__ == "__main__":
    asyncio.run(main())

