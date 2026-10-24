import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import difflib

logger = logging.getLogger(__name__)

class PathCorrectionHook:
    """
    Middleware hook to auto-correct file paths before tool execution.
    Targeted at fixing path hallucinations like 'qentin/' -> 'quentin/'.
    """
    
    def __init__(self, repo_root: str | Path = "."):
        self.repo_root = Path(repo_root).resolve()
        # Pre-cache common directories to speed up matching
        self.common_dirs = ["quentin", "data", "config", "tests", "docs", "tools"]
        
    def __call__(self, tool_name: str, params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        """
        The hook implementation matching ToolManager signature.
        """
        if "path" not in params or not isinstance(params["path"], str):
            return {"blocked": False, "params": params}
            
        original_path = params["path"]
        
        # 1. If path already exists, do nothing
        if (self.repo_root / original_path).exists():
            return {"blocked": False, "params": params}
            
        # 2. Try to find a correction
        corrected_path = self._find_best_match(original_path)
        
        if corrected_path and corrected_path != original_path:
            logger.info(f"PathCorrectionHook: Auto-corrected hallucinated path '{original_path}' -> '{corrected_path}'")
            new_params = dict(params)
            new_params["path"] = corrected_path
            return {"blocked": False, "params": new_params}
            
        return {"blocked": False, "params": params}

    def _find_best_match(self, path_str: str) -> Optional[str]:
        # Handle common typos in root-level directories
        parts = list(Path(path_str).parts)
        if not parts:
            return None
            
        root_part = parts[0]
        # Match against known top-level dirs
        matches = difflib.get_close_matches(root_part, self.common_dirs, n=1, cutoff=0.7)
        
        if matches:
            parts[0] = matches[0]
            return str(Path(*parts))
            
        return None

def get_path_correction_hook(repo_root: str | Path = ".") -> Any:
    return PathCorrectionHook(repo_root=repo_root)


class PathFixerMiddleware:
    """
    Middleware wrapper for PathCorrectionHook (P1-C).
    """

    id: str = "path_fixer"
    priority: int = 100

    def __init__(self, *, repo_root: str | Path = ".") -> None:
        self._hook = PathCorrectionHook(repo_root=repo_root)

    def before(self, *, tool_name: str, params: Dict[str, Any], ctx: Any):
        from quentin.tools.middleware.base import BeforeOutcome

        original = params.get("path") if isinstance(params, dict) else None
        out = self._hook(tool_name, dict(params or {}), ctx)
        new_params = dict(out.get("params") or params or {})
        new_path = new_params.get("path")
        delta: Dict[str, Any] = {}
        if isinstance(original, str) and isinstance(new_path, str) and original != new_path:
            delta = {"path_corrected": {"from": original, "to": new_path}}
        return BeforeOutcome(
            params=new_params,
            blocked=bool(out.get("blocked")),
            reason=str(out.get("reason") or ""),
            ctx_metadata_delta=delta,
        )

    def after(self, *, tool_name: str, params: Dict[str, Any], result: Any, ctx: Any):
        from quentin.tools.middleware.base import AfterOutcome

        return AfterOutcome(result=result, ctx_metadata_delta={})
