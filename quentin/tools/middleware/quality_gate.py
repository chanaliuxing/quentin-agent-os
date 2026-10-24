from __future__ import annotations
import os
import subprocess
import logging
from pathlib import Path
from typing import Any, Dict
from quentin.tools.middleware.base import ToolMiddleware, AfterOutcome, BeforeOutcome
from quentin.tools.schemas import ToolCallResult

logger = logging.getLogger(__name__)

class QualityGateMiddleware(ToolMiddleware):
    """
    P4-B: Post-write Quality Gate.
    Runs static checks (e.g. ruff) after file writes.
    """
    id = "quality_gate"
    priority = 50

    def __init__(self, repo_root: str = "."):
        self.repo_root = Path(repo_root).resolve()

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: Any) -> BeforeOutcome:
        return BeforeOutcome(params=params)

    def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: Any) -> AfterOutcome:
        if tool_name not in ("fs.write_file", "fs.search_replace") or not result.success:
            return AfterOutcome(result=result)

        path_str = params.get("path") or params.get("file")
        if not path_str or not path_str.endswith(".py"):
            return AfterOutcome(result=result)

        # Run ruff check
        full_path = self.repo_root / path_str
        if not full_path.exists():
            return AfterOutcome(result=result)

        try:
            # Default to critical errors only (E, F, B). 
            # Allow environment override for testing or stricter environments.
            rules = os.getenv("QUENTIN_QUALITY_GATE_RULES", "E,F,B")
            
            # -q for quiet
            res = subprocess.run(
                ["ruff", "check", str(full_path), "--select", rules, "-q"],
                capture_output=True,
                text=True,
                cwd=str(self.repo_root)
            )
            
            # Ruff returns non-zero if it finds linting errors
            if res.returncode != 0:
                logger.warning("Quality Gate FAILED for %s: %s", path_str, res.stdout)
                # We modify the result to be a failure if quality gate fails
                new_result = ToolCallResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Quality gate failed: static checks (ruff) found errors.\n{res.stdout}",
                    output=result.output
                )
                return AfterOutcome(result=new_result)
                
        except Exception as e:
            logger.error("Failed to run quality gate: %s", e)
            
        return AfterOutcome(result=result)
