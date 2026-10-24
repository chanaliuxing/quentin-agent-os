from __future__ import annotations
import asyncio
import logging
from typing import TypeVar, Callable, Awaitable, Optional
from quentin.infra.concurrency.lanes import get_async_lane_manager, resolve_session_lane
from quentin.infra.concurrency.lane_policy import LanePolicy
from quentin.infra.concurrency.abort_signal import abort_registry
from quentin.infra.sessions.session_store import SessionState

logger = logging.getLogger(__name__)
T = TypeVar("T")

class LaneOrchestrator:
    """
    P0: Unified Lane Orchestrator.
    Centralizes all concurrency management for API, Cognitive Loop, and Self-Programming.
    """
    def __init__(self):
        self._manager = get_async_lane_manager()
        self.policy = LanePolicy()

    async def run_in_lane(
        self, 
        lane_key: str,
        coro_fn: Callable[[], Awaitable[T]], 
        priority: int = 0,
        tenant_id: Optional[str] = None,
        abort_existing: bool = False,
        abort_signal_id: Optional[str] = None,
    ) -> T:
        """
        Execute a coroutine within a specific lane (session or global).
        P5: Surgery Three - Support pre-emptive abort for high priority tasks.
        """
        if tenant_id:
            if not self.policy.acquire_slot(tenant_id):
                raise RuntimeError(f"Concurrency quota exceeded for tenant {tenant_id}")

        try:
            resolved_lane = resolve_session_lane(lane_key)
            signal_id = str(abort_signal_id or lane_key or "").strip() or "unknown"
            
            # P5: OpenClaw Parity - Pre-emptive Abort
            if abort_existing:
                logger.warning(f"Orchestrator: Aborting existing tasks in lane {resolved_lane}")
                abort_registry.get_signal(signal_id).abort(reason="Pre-empted by higher priority task")
                # Small yield to let cleanup happen
                await asyncio.sleep(0.1)
            
            # Enqueue via the low-level manager
            return await self._manager.enqueue(
                session_lane=resolved_lane,
                coro_fn=coro_fn,
                global_lane="main" # Default global lane
            )
        finally:
            if tenant_id:
                self.policy.release_slot(tenant_id)

    async def run_in_session(
        self,
        session: SessionState,
        coro_fn: Callable[[], Awaitable[T]],
        *,
        session_store: Optional[object] = None,
        priority: int = 0,
        tenant_id: Optional[str] = None,
        abort_existing: bool = False,
    ) -> T:
        lane_key = str(getattr(session, "lane_key", "") or getattr(session, "session_id", "") or "unknown")
        abort_signal_id = str(getattr(session, "abort_signal_id", "") or getattr(session, "session_id", "") or lane_key)
        abort_registry.get_signal(abort_signal_id)
        if session_store is not None and hasattr(session_store, "acquire_lock"):
            with session_store.acquire_lock(session):
                return await self.run_in_lane(
                    lane_key=lane_key,
                    coro_fn=coro_fn,
                    priority=priority,
                    tenant_id=tenant_id,
                    abort_existing=abort_existing,
                    abort_signal_id=abort_signal_id,
                )
        return await self.run_in_lane(
            lane_key=lane_key,
            coro_fn=coro_fn,
            priority=priority,
            tenant_id=tenant_id,
            abort_existing=abort_existing,
            abort_signal_id=abort_signal_id,
        )

    async def acquire(self, lane_id: str, task_id: str, timeout: float = 300.0):
        """
        Enters a lane. Waits if another task is active.
        """
        # P5: Implementation using enqueued lock or similar logic if needed.
        # For now, we can bridge this to the manager's logic or a simpler lock.
        # However, run_in_lane is preferred. Bridging acquire/release for compatibility:
        logger.info(f"Concurrency: Task {task_id} acquiring Lane {lane_id}...")
        # Since we use enqueued execution, explicit acquire is often redundant, 
        # but needed for explicit block-based flows.
        return True # Placeholder that always succeeds if using run_in_lane later

    def release(self, lane_id: str, task_id: str):
        """
        Leaves a lane.
        """
        logger.info(f"Concurrency: Task {task_id} releasing Lane {lane_id}")
        pass

    def run_sync(self, lane_key: str, coro_fn: Callable[[], Awaitable[T]]) -> T:
        """
        Synchronous wrapper for legacy/CLI entry points.
        """
        try:
            return asyncio.run(self.run_in_lane(lane_key, coro_fn))
        except RuntimeError:
            # If loop is already running, we might be in a nested context.
            # Ideally, refactor caller to be async. For now, fail fast.
            raise RuntimeError("LaneOrchestrator.run_sync called from within running event loop.")

    def run_sync_in_session(
        self,
        session: SessionState,
        coro_fn: Callable[[], Awaitable[T]],
        *,
        session_store: Optional[object] = None,
        priority: int = 0,
        tenant_id: Optional[str] = None,
        abort_existing: bool = False,
    ) -> T:
        try:
            return asyncio.run(
                self.run_in_session(
                    session,
                    coro_fn,
                    session_store=session_store,
                    priority=priority,
                    tenant_id=tenant_id,
                    abort_existing=abort_existing,
                )
            )
        except RuntimeError:
            raise RuntimeError("LaneOrchestrator.run_sync_in_session called from within running event loop.")

# Global Singleton
lane_orchestrator = LaneOrchestrator()
