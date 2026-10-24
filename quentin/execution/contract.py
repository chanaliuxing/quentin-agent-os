from __future__ import annotations
import logging
from typing import Any, Dict, List, Set
from quentin.planning import PlanStep

logger = logging.getLogger(__name__)

class StepContractGuard:
    """
    P4-A: Step Contract Guard.
    Ensures that mutation steps are preceded by observation steps for the same target.
    """
    def __init__(self):
        self.observed_targets: Set[str] = set()

    def verify_step(self, step: PlanStep) -> bool:
        """
        Verify if the step complies with the contract.
        - If it's a mutation (write, replace, etc.), it must have been observed.
        - If it's an observation (read, ls, etc.), record it.
        """
        target = step.args.get("path") or step.args.get("file") or step.args.get("target_path")
        
        # 1. Identify step nature
        name = step.name.lower()
        is_mutation = any(kw in name for kw in ["write", "replace", "delete", "mkdir", "rm", "update", "patch"])
        is_observation = any(kw in name for kw in ["read", "list", "ls", "grep", "find", "cat", "stat", "check", "search"])
        
        if is_observation and target:
            self.observed_targets.add(target)
            return True
            
        if is_mutation and target:
            if target not in self.observed_targets:
                logger.warning("Step Contract Violation: Attempting to mutate '%s' without prior observation.", target)
                # In strict mode, we would return False. For v1, we just log and return True but could be used to block.
                # Let's be strict if enabled via env.
                import os
                if os.getenv("QUENTIN_STRICT_STEP_CONTRACT", "0") == "1":
                    return False
        
        return True

    def reset(self):
        self.observed_targets.clear()
