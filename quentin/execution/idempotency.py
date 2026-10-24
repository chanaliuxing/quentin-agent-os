from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List
from quentin.utils.hash import get_file_hash, get_goal_fingerprint, EnvironmentHasher
from quentin.utils.time import now_iso
import hashlib

logger = logging.getLogger(__name__)

class IdempotencyGate:
    """
    P4-A: Goal Fingerprint + File State Hash Idempotency Gate.
    P5: Surgery Four - Cognitive Fingerprinting (Joint State Hash).
    """
    def __init__(self, repo_root: str = "."):
        self.repo_root = Path(repo_root).resolve()
        self.state_dir = self.repo_root / "data" / "execution" / "idempotency"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def get_cognitive_fingerprint(self, task_input: str, env_summary: str, tools: List[str]) -> str:
        """
        P5: Surgery Four - Cognitive Fingerprint.
        Joint hash of Task + Environment + Capabilities + Physical System State.
        """
        # P5: OpenClaw Parity - Deep Physical State Sampling
        physical_env = EnvironmentHasher.get_fast_directory_fingerprint(self.repo_root)
        system_state = EnvironmentHasher.get_system_state_fingerprint()
        
        data = {
            "task": task_input,
            "physical_env_hash": physical_env,
            "system_state": system_state,
            "tools": sorted(tools)
        }
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

    def check_detail(self, fingerprint: str, target_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if this goal/state has already been achieved.
        Returns a dict with 'hit': bool and 'plan_fragment': Optional[Dict].
        """
        if not fingerprint:
            return {"hit": False}
            
        record_path = self.state_dir / f"{fingerprint}.json"
        if not record_path.exists():
            return {"hit": False}
            
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            
            # 1. Physical file state check (if applicable)
            if target_file:
                current_hash = get_file_hash(self.repo_root / target_file)
                if record.get("target_file_hash") != current_hash:
                    return {"hit": False}
            
            if record.get("status") == "success":
                return {
                    "hit": True,
                    "plan_fragment": record.get("plan_fragment"),
                    "final_output": record.get("final_output")
                }
            
            return {"hit": False}
        except Exception:
            logger.warning("Failed to read idempotency record %s", fingerprint, exc_info=True)
            return {"hit": False}

    def check(self, fingerprint: str, target_file: Optional[str] = None) -> bool:
        """
        Backward-compatible boolean check.

        NOTE: A dict return here is dangerous because non-empty dicts are truthy and can
        accidentally skip execution steps. Call `check_detail()` when you need artifacts.
        """
        return bool(self.check_detail(fingerprint, target_file).get("hit"))

    def mark_success(self, fingerprint: str, target_file: Optional[str] = None, plan_fragment: Any = None, final_output: str = "") -> None:
        """
        Record a successful completion with its cognitive artifacts.
        """
        if not fingerprint:
            return
            
        record_path = self.state_dir / f"{fingerprint}.json"
        record = {
            "status": "success",
            "fingerprint": fingerprint,
            "target_file": target_file,
            "target_file_hash": get_file_hash(self.repo_root / target_file) if target_file else None,
            "plan_fragment": plan_fragment,
            "final_output": final_output,
            "ts": now_iso()
        }
        
        try:
            record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("Failed to write idempotency record %s", fingerprint, exc_info=True)
