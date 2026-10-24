from __future__ import annotations

from dataclasses import dataclass
import asyncio
import os
from threading import Lock, RLock, Semaphore
from typing import Awaitable, Callable, Dict, Optional, TypeVar, Union


T = TypeVar("T")

# Canonical Lane IDs (OpenClaw inspired)
LANE_MAIN = "main"        # Default global lane
LANE_MAINTENANCE = "cron" # Background/Self-programming global lane
LANE_SUBAGENT = "subagent" # Sub-task concurrency control

def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        return max(1, value)
    except Exception:
        return default


DEFAULT_LANE_CONCURRENCY: Dict[str, int] = {
    "main": _env_int("QUENTIN_MAIN_LANE_CONCURRENCY", 1),
    "cron": _env_int("QUENTIN_CRON_LANE_CONCURRENCY", 1),
    "subagent": _env_int("QUENTIN_SUBAGENT_LANE_CONCURRENCY", 1),
}


def resolve_session_lane(key: str) -> str:
    cleaned = (key or "").strip()
    if not cleaned:
        return "session:unknown"
    return cleaned if cleaned.startswith("session:") else f"session:{cleaned}"

def resolve_global_lane(
    *,
    domain: str | None = None,
    environment: str | None = None,
    is_background: bool = False,
) -> str:
    """
    OpenClaw parity: global-vs-session lane resolution.

    - Session lane: per-session serialization (lock)
    - Global lane: global concurrency budget (semaphore)
    """
    override = (os.getenv("QUENTIN_GLOBAL_LANE_DEFAULT") or "").strip().lower()
    if override:
        return override

    env = (environment or "").strip().lower()
    dom = (domain or "").strip().lower()
    if is_background or dom in ("cron", "maintenance", "selfprog") or env in ("cron", "maintenance"):
        return LANE_MAINTENANCE
    return LANE_MAIN


def resolve_lane_hierarchy(
    *,
    session_key: str,
    domain: str | None = None,
    environment: str | None = None,
    is_background: bool = False,
    is_subagent: bool = False,
) -> tuple[str, str, str | None]:
    """
    Hierarchical lane resolution.

    Returns: (session_lane, global_lane, sublane)
    - `sublane` is an optional extra global semaphore layer for subagents.
    """
    session_lane = resolve_session_lane(session_key)
    global_lane = resolve_global_lane(domain=domain, environment=environment, is_background=is_background)
    sublane = LANE_SUBAGENT if is_subagent else None
    return session_lane, global_lane, sublane


@dataclass
class LaneStats:
    active: int = 0
    waiting: int = 0


class LaneManager:
    def __init__(self) -> None:
        self._lane_locks: Dict[str, Lock] = {}
        self._lane_semaphores: Dict[str, Semaphore] = {}
        self._lane_stats: Dict[str, LaneStats] = {}
        self._guard = Lock()
        for lane, n in DEFAULT_LANE_CONCURRENCY.items():
            self._lane_semaphores[lane] = Semaphore(max(1, int(n)))
            self._lane_stats[lane] = LaneStats(active=0)

    def set_concurrency(self, lane: str, max_concurrent: int) -> None:
        cleaned = (lane or "").strip() or "main"
        n = max(1, int(max_concurrent))
        with self._guard:
            self._lane_semaphores[cleaned] = Semaphore(n)
            self._lane_stats.setdefault(cleaned, LaneStats())

    def _get_lock(self, lane: str) -> Lock:
        cleaned = (lane or "").strip() or "main"
        with self._guard:
            lock = self._lane_locks.get(cleaned)
            if lock is None:
                # Re-entrant to tolerate nested lane enforcement (e.g. CLI/API wrapper + internal loop).
                lock = RLock()
                self._lane_locks[cleaned] = lock
            self._lane_stats.setdefault(cleaned, LaneStats())
            return lock

    def _get_semaphore(self, lane: str) -> Semaphore:
        cleaned = (lane or "").strip() or "main"
        with self._guard:
            sem = self._lane_semaphores.get(cleaned)
            if sem is None:
                sem = Semaphore(1)
                self._lane_semaphores[cleaned] = sem
                self._lane_stats.setdefault(cleaned, LaneStats())
            return sem

    def run_in_lanes(
        self,
        *,
        session_lane: str,
        global_lane: str = "main",
        fn: Callable[[], T],
        timeout_sec: float = 300.0,
    ) -> T:
        session_lock = self._get_lock(session_lane)
        global_semaphore = self._get_semaphore(global_lane)
        
        # P5: Deadlock Protection
        if not session_lock.acquire(timeout=timeout_sec):
            raise TimeoutError(f"Session lane '{session_lane}' is locked and timed out after {timeout_sec}s")
            
        try:
            with self._guard:
                self._lane_stats[session_lane].waiting += 1
            
            if not global_semaphore.acquire(timeout=timeout_sec):
                raise TimeoutError(f"Global lane '{global_lane}' is saturated and timed out after {timeout_sec}s")
                
            try:
                with self._guard:
                    self._lane_stats[global_lane].active += 1
                    self._lane_stats[session_lane].waiting = max(0, self._lane_stats[session_lane].waiting - 1)
                return fn()
            finally:
                with self._guard:
                    self._lane_stats[global_lane].active = max(
                        0, self._lane_stats[global_lane].active - 1
                    )
                global_semaphore.release()
        finally:
            session_lock.release()

    def get_queue_size(self, lane: str) -> int:
        cleaned = (lane or "").strip() or "main"
        with self._guard:
            return int(self._lane_stats.get(cleaned, LaneStats()).waiting)


_LANE_MANAGER: Optional[LaneManager] = None


def get_lane_manager() -> LaneManager:
    global _LANE_MANAGER
    if _LANE_MANAGER is None:
        _LANE_MANAGER = LaneManager()
    return _LANE_MANAGER


def set_concurrency(lane: str, max_concurrent: int) -> None:
    get_lane_manager().set_concurrency(lane, max_concurrent)


def run_in_lanes(session_lane: str, fn: Callable[[], T], global_lane: str = "main") -> T:
    return get_lane_manager().run_in_lanes(
        session_lane=session_lane,
        global_lane=global_lane,
        fn=fn,
    )


def get_queue_size(lane: str) -> int:
    """
    Best-effort queue size for sync lanes (counts waiting tasks).
    """
    return get_lane_manager().get_queue_size(lane)


# ---------------------------------------------------------------------------
# Async lane queue (OpenClaw-style enqueue API)
# ---------------------------------------------------------------------------

AsyncFn = Callable[[], Union[Awaitable[T], T]]


class AsyncLaneManager:
    def __init__(self) -> None:
        self._lane_locks: Dict[str, asyncio.Lock] = {}
        self._lane_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._lane_stats: Dict[str, LaneStats] = {}
        self._guard = asyncio.Lock()
        for lane, n in DEFAULT_LANE_CONCURRENCY.items():
            self._lane_semaphores[lane] = asyncio.Semaphore(max(1, int(n)))
            self._lane_stats[lane] = LaneStats(active=0, waiting=0)

    async def set_concurrency(self, lane: str, max_concurrent: int) -> None:
        cleaned = (lane or "").strip() or "main"
        n = max(1, int(max_concurrent))
        async with self._guard:
            self._lane_semaphores[cleaned] = asyncio.Semaphore(n)
            self._lane_stats.setdefault(cleaned, LaneStats(active=0, waiting=0))

    async def get_queue_size(self, lane: str) -> int:
        cleaned = (lane or "").strip() or "main"
        async with self._guard:
            return int(self._lane_stats.get(cleaned, LaneStats()).waiting)

    async def _get_lock(self, lane: str) -> asyncio.Lock:
        cleaned = (lane or "").strip() or "main"
        async with self._guard:
            lock = self._lane_locks.get(cleaned)
            if lock is None:
                lock = asyncio.Lock()
                self._lane_locks[cleaned] = lock
            self._lane_stats.setdefault(cleaned, LaneStats(active=0, waiting=0))
            return lock

    async def _get_semaphore(self, lane: str) -> asyncio.Semaphore:
        cleaned = (lane or "").strip() or "main"
        async with self._guard:
            sem = self._lane_semaphores.get(cleaned)
            if sem is None:
                sem = asyncio.Semaphore(1)
                self._lane_semaphores[cleaned] = sem
                self._lane_stats.setdefault(cleaned, LaneStats(active=0, waiting=0))
            return sem

    async def enqueue(
        self,
        *,
        session_lane: str,
        coro_fn: AsyncFn[T],
        global_lane: str = "main",
        timeout_sec: float = 300.0,
    ) -> T:
        session_lock = await self._get_lock(session_lane)
        global_sem = await self._get_semaphore(global_lane)

        try:
            # Use wait_for for async timeout
            return await asyncio.wait_for(
                self._run_queued(session_lock, global_sem, session_lane, global_lane, coro_fn),
                timeout=timeout_sec
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Task in lane '{session_lane}' timed out after {timeout_sec}s")

    async def _run_queued(self, session_lock, global_sem, session_lane, global_lane, coro_fn) -> T:
        async with session_lock:
            async with self._guard:
                self._lane_stats[session_lane].waiting += 1
            await global_sem.acquire()
            try:
                async with self._guard:
                    self._lane_stats[global_lane].active += 1
                    self._lane_stats[session_lane].waiting = max(0, self._lane_stats[session_lane].waiting - 1)
                res = coro_fn()
                if hasattr(res, "__await__"):
                    return await res  # type: ignore[return-value]
                return res  # type: ignore[return-value]
            finally:
                async with self._guard:
                    self._lane_stats[global_lane].active = max(0, self._lane_stats[global_lane].active - 1)
                global_sem.release()


_ASYNC_LANE_MANAGER: Optional[AsyncLaneManager] = None


def get_async_lane_manager() -> AsyncLaneManager:
    global _ASYNC_LANE_MANAGER
    if _ASYNC_LANE_MANAGER is None:
        _ASYNC_LANE_MANAGER = AsyncLaneManager()
    return _ASYNC_LANE_MANAGER


async def enqueue(lane: str, coro_fn: AsyncFn[T], *, global_lane: str = "main") -> T:
    """
    Async enqueue API expected by blueprint:
    - `lane` can be `session:{id}` or a raw session id (auto-prefixed)
    - session lanes are strict FIFO (concurrency=1), while `global_lane` enforces global concurrency.
    """
    session_lane = resolve_session_lane(lane)
    return await get_async_lane_manager().enqueue(session_lane=session_lane, coro_fn=coro_fn, global_lane=global_lane)


async def enqueue_hierarchical(
    *,
    session_key: str,
    coro_fn: AsyncFn[T],
    domain: str | None = None,
    environment: str | None = None,
    is_background: bool = False,
    is_subagent: bool = False,
    timeout_sec: float = 300.0,
) -> T:
    """
    OpenClaw parity API: resolve lanes from session key and metadata.
    """
    session_lane, global_lane, sublane = resolve_lane_hierarchy(
        session_key=session_key,
        domain=domain,
        environment=environment,
        is_background=is_background,
        is_subagent=is_subagent,
    )
    mgr = get_async_lane_manager()
    if not sublane:
        return await mgr.enqueue(session_lane=session_lane, global_lane=global_lane, coro_fn=coro_fn, timeout_sec=timeout_sec)

    # If sublane is requested, enforce it as a second global semaphore.
    sub_sem = await mgr._get_semaphore(sublane)  # noqa: SLF001 - intentional private reuse
    async def _wrapped() -> T:
        await sub_sem.acquire()
        try:
            res = coro_fn()
            if hasattr(res, "__await__"):
                return await res  # type: ignore[return-value]
            return res  # type: ignore[return-value]
        finally:
            sub_sem.release()

    return await mgr.enqueue(session_lane=session_lane, global_lane=global_lane, coro_fn=_wrapped, timeout_sec=timeout_sec)
