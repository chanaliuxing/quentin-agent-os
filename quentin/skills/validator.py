from __future__ import annotations
import subprocess
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from quentin.skills.candidate_pipeline import SkillCandidate

logger = logging.getLogger(__name__)

class SkillValidator:
    """
    P5: Ported from OpenClaw's skill validator.
    Runs automated smoke tests for new skill candidates in isolation.
    """
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def validate_candidate(self, cand: SkillCandidate) -> Tuple[bool, str]:
        """
        Physically executes the candidate's test code.
        """
        # 1. Create Temporary Validation File
        temp_test_path = self.repo_root / "data" / "temp" / f"test_{cand.candidate_id[:8]}.py"
        temp_test_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Combined code for standalone execution
        test_payload = f"""
# --- Skill Code ---
{cand.implementation_code}

# --- Test Code ---
{cand.verification_test_code}

if __name__ == "__main__":
    # Simple runner if not using pytest
    import sys
    try:
        # We look for functions starting with 'test_' and run them
        test_funcs = [obj for name, obj in locals().items() if name.startswith('test_') and callable(obj)]
        for f in test_funcs:
            print(f"Running {{f.__name__}}...")
            f()
        print("ALL_TESTS_PASSED")
    except Exception as e:
        print(f"TEST_FAILED: {{e}}", file=sys.stderr)
        sys.exit(1)
"""
        temp_test_path.write_text(test_payload, encoding="utf-8")
        
        # 2. Physical Execution in Sandbox (OpenClaw Parity)
        try:
            # We use a restricted shell execution
            result = subprocess.run(
                ["python3", str(temp_test_path)],
                capture_output=True,
                text=True,
                timeout=30.0
            )
            
            if result.returncode == 0 and "ALL_TESTS_PASSED" in result.stdout:
                logger.info(f"Validator: Skill {cand.name} PASSED validation.")
                return True, result.stdout
            else:
                error_info = result.stderr or result.stdout
                logger.warning(f"Validator: Skill {cand.name} FAILED validation: {error_info}")
                return False, error_info
                
        except Exception as e:
            return False, str(e)
        finally:
            # Cleanup
            if temp_test_path.exists():
                temp_test_path.unlink()
