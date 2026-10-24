from __future__ import annotations
from typing import Any, Dict
import logging
from quentin.tools.schemas import ToolCallRequest
from quentin.tools.manager import ToolCallContext

logger = logging.getLogger(__name__)

class SelfProgrammingSafetyWrapper:
    """
    P0: Forces Self-Programming Engine to use ToolManager.
    Ensures all writes pass through PathGuard and SyntaxGuard.
    """
    def __init__(self, tool_manager: Any):
        self.tm = tool_manager

    async def safe_write_file(self, path: str, content: str, reason: str = "self-prog"):
        """
        Execute fs.write_file via ToolManager (Middleware enabled).
        """
        req = ToolCallRequest(
            tool_name="fs.write_file",
            payload={"path": path, "content": content},
            meta={"reason": reason}
        )
        ctx = ToolCallContext(metadata={"session_id": "self-programming-system"})
        
        # This triggers SmartFS, PathGuard, SyntaxGuard
        result = await self.tm.call_tool(req, ctx)
        
        if not result.success:
            raise PermissionError(f"Self-Programming Write Blocked: {result.error}")
        return result

# We will inject this into the Engine or PatchApplier
