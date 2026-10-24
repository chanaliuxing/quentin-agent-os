from __future__ import annotations

import uuid
import asyncio
import logging
import time
import threading
from typing import Dict, Any, Optional, Literal, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ApprovalStatus = Literal["pending", "approved", "rejected", "expired"]

@dataclass
class ApprovalRequest:
    request_id: str
    tool_name: str
    args: Dict[str, Any]
    reason: str
    status: ApprovalStatus = "pending"
    created_at: float = field(default_factory=time.time)
    # Async waiters (optional): only created when `request_approval()` is used.
    _future: Optional[asyncio.Future] = None
    # Sync waiters: safe to use across threads.
    _event: threading.Event = field(default_factory=threading.Event)
    _sync_result: Optional[bool] = None

class ApprovalGatekeeper:
    """
    Manages Human-in-the-Loop approval requests.
    Ported from OpenClaw's exec-approval-manager.
    """
    def __init__(self, timeout_seconds: int = 300):
        self.timeout_seconds = timeout_seconds
        self._pending_requests: Dict[str, ApprovalRequest] = {}

    async def request_approval(self, tool_name: str, args: Dict[str, Any], reason: str, *, timeout_seconds: Optional[int] = None) -> bool:
        """
        Blocks and waits for human approval via Canvas or Telegram.
        """
        req_id = uuid.uuid4().hex
        req = ApprovalRequest(
            request_id=req_id,
            tool_name=tool_name,
            args=args,
            reason=reason
        )
        req._future = asyncio.get_running_loop().create_future()
        self._pending_requests[req_id] = req
        
        logger.warning(f"GATEKEEPER: Approval required for {tool_name}! Request ID: {req_id}")
        
        # Notify channels (mock logic for now, would hook into Broadcaster)
        from quentin.infra.canvas.broadcaster import broadcaster
        await broadcaster.broadcast({
            "type": "approval_request",
            "payload": {
                "request_id": req_id,
                "tool": tool_name,
                "reason": reason
            }
        })

        timeout = int(timeout_seconds) if timeout_seconds is not None else int(self.timeout_seconds)
        try:
            # Wait for decision
            is_approved = await asyncio.wait_for(req._future, timeout=timeout)
            return is_approved
        except asyncio.TimeoutError:
            req.status = "expired"
            logger.error(f"Approval request {req_id} timed out.")
            return False
        finally:
            if req_id in self._pending_requests:
                del self._pending_requests[req_id]

    def request_approval_sync(
        self,
        tool_name: str,
        args: Dict[str, Any],
        reason: str,
        *,
        timeout_seconds: Optional[int] = None,
    ) -> tuple[bool, str]:
        """
        Synchronous variant for sync guard rails (SafetyKernel / ToolManager).

        This is safe to call from background threads. It can be resolved via:
        - /approvals/{id}/resolve API
        - qctl approve/deny
        - canvas server callbacks
        """
        req_id = uuid.uuid4().hex
        req = ApprovalRequest(
            request_id=req_id,
            tool_name=tool_name,
            args=args,
            reason=reason,
        )
        self._pending_requests[req_id] = req

        logger.warning(f"GATEKEEPER(sync): Approval required for {tool_name}! Request ID: {req_id}")

        # Best-effort notify channels; do not block if broadcaster is unavailable.
        try:
            from quentin.infra.canvas.broadcaster import broadcaster

            async def _notify() -> None:
                await broadcaster.broadcast(
                    {
                        "type": "approval_request",
                        "payload": {
                            "request_id": req_id,
                            "tool": tool_name,
                            "reason": reason,
                        },
                    }
                )

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                loop.create_task(_notify())
            else:
                asyncio.run(_notify())
        except Exception:
            pass

        timeout = float(timeout_seconds) if timeout_seconds is not None else float(self.timeout_seconds)
        approved = False
        try:
            if req._event.wait(timeout=timeout):
                approved = bool(req._sync_result)
            else:
                req.status = "expired"
                approved = False
        finally:
            self._pending_requests.pop(req_id, None)
        return approved, req_id

    def list_pending(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for req_id, req in list(self._pending_requests.items()):
            out.append(
                {
                    "request_id": req_id,
                    "tool_name": req.tool_name,
                    "reason": req.reason,
                    "status": req.status,
                    "created_at": req.created_at,
                    "args": req.args,
                }
            )
        out.sort(key=lambda x: float(x.get("created_at") or 0.0))
        return out

    def resolve_request(self, request_id: str, decision: bool):
        """Called by CLI or API to approve/reject."""
        req = self._pending_requests.get(request_id)
        if not req:
            logger.warning(f"Gatekeeper: Unknown request {request_id}")
            return
        
        req.status = "approved" if decision else "rejected"
        req._sync_result = bool(decision)
        req._event.set()
        if req._future is not None and not req._future.done():
            req._future.set_result(bool(decision))
        logger.info(f"Gatekeeper: Request {request_id} resolved -> {req.status}")

# Global instance
approval_gate = ApprovalGatekeeper()
