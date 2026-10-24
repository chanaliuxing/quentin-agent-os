
import os
from typing import Any, Dict, List
from pathlib import Path

class PolicyPerceptionProvider:
    """
    P5.1: Provides transparency about system policies (write roots, logs) to the brain.
    """
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def get_policy_summary(self) -> Dict[str, Any]:
        from quentin.kernel.path_guard import PathGuard
        
        guard = PathGuard(repo_root=self.repo_root, allowed_roots=None)
        extra_raw = str(os.getenv("QUENTIN_PATH_GUARD_EXTRA_ALLOWED_ROOTS", "") or "").strip()
        
        return {
            "allowed_write_roots": list(guard.allowed_roots),
            "recommended_directories": {
                "logs": "logs/",
                "mutable_data": "mutable/",
                "generated_artifacts": "generated/",
                "tool_extensions": "extensions/tools/"
            },
            "environment": os.getenv("QUENTIN_ENV", "sandbox"),
            "extra_allowed_roots_env": extra_raw
        }
