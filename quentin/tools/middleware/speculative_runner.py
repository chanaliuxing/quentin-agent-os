from __future__ import annotations
import logging
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)

class SpeculativeRunner:
    """
    P5: Ported from OpenClaw's dry-run safety logic.
    Attempts to verify tool success without side effects before committing.
    """
    
    @staticmethod
    def supports_dry_run(tool_name: str) -> bool:
        # P5: Hardcoded knowledge of tool capabilities (OpenClaw Parity)
        return tool_name in ("fs.patch", "patch", "git.apply")

    @staticmethod
    def execute_dry_run(tool_name: str, params: Dict[str, Any], handler: Callable) -> Dict[str, Any]:
        """
        Injects dry-run flags and interprets the result.
        Returns {"safe": bool, "error": str, "output": str}
        """
        dry_params = dict(params)
        
        # 1. Inject Tool-specific Flags
        if tool_name in ("fs.patch", "patch"):
            dry_params["dry_run"] = True
        elif tool_name == "git.apply":
            dry_params["check_only"] = True
            
        try:
            # 2. Speculative Execution
            logger.info(f"Speculator: Running Dry Run for {tool_name}...")
            result = handler(dry_params)
            
            # 3. Interpret Result
            # Tools should return success=True even in dry run if the dry run was successful
            if isinstance(result, dict) and result.get("status") == "ok":
                return {"safe": True}
            
            error_msg = str(result.get("error") if isinstance(result, dict) else result)
            return {"safe": False, "error": f"Dry run failed: {error_msg}"}
            
        except Exception as e:
            return {"safe": False, "error": f"Dry run exception: {str(e)}"}
