from __future__ import annotations

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from quentin.memory.models import MemoryQuery, MemoryRecord


@dataclass
class SessionSearchSpec:
    session_id: str
    source_prefixes: List[str]
    weight: float = 1.0
    top_k_override: Optional[int] = None
    priority: int = 0


@dataclass
class SearchManagerConfig:
    max_workers: int = 4
    per_session_timeout_s: float = 3.0
    rerank_enabled: bool = True
    rerank_time_half_life_hours: float = 24.0
    source_priors: Optional[Dict[str, float]] = None
    domain_match_bonus: float = 0.15
    max_sessions_scanned: int = 0
    max_candidates_reranked: int = 0
    adaptive_degrade_enabled: bool = True
    timeout_pressure_threshold: float = 0.4
    adaptive_session_cap_factor: int = 3


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value.strip():
        s = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None


def rrf_merge_ranked_lists(
    *,
    ranked_lists: Sequence[Sequence[MemoryRecord]],
    weights: Optional[Sequence[float]] = None,
    k: int = 60,
    top_k: int = 10,
) -> List[MemoryRecord]:
    scores: Dict[str, float] = {}
    by_id: Dict[str, MemoryRecord] = {}
    ws = list(weights or [])

    for i, records in enumerate(ranked_lists):
        w = float(ws[i]) if i < len(ws) else 1.0
        for rank, rec in enumerate(records):
            rid = str(getattr(rec, "id", "") or "")
            if not rid:
                continue
            by_id[rid] = rec
            scores[rid] = scores.get(rid, 0.0) + (w * (1.0 / float(k + rank + 1)))

    ordered = sorted(scores.keys(), key=lambda rid: scores[rid], reverse=True)
    return [by_id[rid] for rid in ordered[: max(1, int(top_k))]]


def _apply_rerank(
    *,
    records: List[MemoryRecord],
    query_domain: Optional[str],
    cfg: SearchManagerConfig,
) -> List[MemoryRecord]:
    if not records or not cfg.rerank_enabled:
        return records
    half_life_hours = max(0.1, float(cfg.rerank_time_half_life_hours or 24.0))
    source_priors = dict(cfg.source_priors or {})
    now = _utc_now()
    scored: List[tuple[float, MemoryRecord]] = []
    qd = str(query_domain or "").strip().lower()

    for i, rec in enumerate(records):
        base = 1.0 / float(i + 1)
        src = str(getattr(rec, "source", "") or "")
        src_bonus = 0.0
        for prefix, bonus in source_priors.items():
            if src.startswith(str(prefix)):
                src_bonus = max(src_bonus, float(bonus))
        domain_bonus = 0.0
        rd = str(getattr(rec, "domain", "") or "").strip().lower()
        if qd and rd and qd == rd:
            domain_bonus = float(cfg.domain_match_bonus or 0.0)
        created = _parse_dt(getattr(rec, "created_at", None))
        if created is None:
            created = _parse_dt((getattr(rec, "metadata", {}) or {}).get("created_at"))
        if created is None:
            age_hours = half_life_hours * 2.0
        else:
            age_hours = max(0.0, (now - created).total_seconds() / 3600.0)
        decay = 0.5 ** (age_hours / half_life_hours)
        total = (base + src_bonus + domain_bonus) * decay
        scored.append((total, rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [rec for _, rec in scored]


class ParallelSearchManager:
    """
    OpenClaw manager-search/search-manager parity increment:
    parallel cross-session recall scheduling + RRF fusion.
    """

    def __init__(self, *, config: Optional[SearchManagerConfig] = None, max_workers: Optional[int] = None) -> None:
        cfg = config or SearchManagerConfig()
        if max_workers is not None:
            cfg.max_workers = int(max_workers)
        self.config = cfg
        self.max_workers = max(1, int(self.config.max_workers or 1))

    def _timeout_pressure_threshold(self) -> float:
        raw = getattr(self.config, "timeout_pressure_threshold", None)
        if raw is None:
            return 0.4
        try:
            return max(0.0, min(1.0, float(raw)))
        except Exception:
            return 0.4

    def _apply_adaptive_session_cap(
        self,
        *,
        ordered_specs: List[SessionSearchSpec],
        overall_timeout_s: Optional[float] = None,
    ) -> tuple[List[SessionSearchSpec], bool]:
        if not bool(self.config.adaptive_degrade_enabled):
            return ordered_specs, False
        cap_by_factor = max(1, int(self.max_workers) * max(1, int(self.config.adaptive_session_cap_factor or 3)))
        cap = min(len(ordered_specs), cap_by_factor)
        if overall_timeout_s is not None:
            expected_rounds = max(1, int(math.ceil(float(len(ordered_specs)) / float(max(1, self.max_workers)))))
            expected_budget = float(self.config.per_session_timeout_s or 3.0) * float(expected_rounds)
            if float(overall_timeout_s) < expected_budget:
                cap = min(cap, max(1, int(self.max_workers) * 2))
        if cap < len(ordered_specs):
            return ordered_specs[:cap], True
        return ordered_specs, False

    def search_across_sessions(
        self,
        *,
        memory_fabric: Any,
        base_query: MemoryQuery,
        session_specs: Sequence[SessionSearchSpec],
        top_k: Optional[int] = None,
        per_session_factor: int = 3,
        rrf_k: int = 60,
    ) -> Dict[str, Any]:
        if not session_specs:
            return {
                "records": [],
                "by_session": {},
                "total_sessions": 0,
                "session_hits": {},
                "errors": {},
                "timed_out_sessions": [],
            }

        ordered_specs = sorted(
            list(session_specs),
            key=lambda s: (int(getattr(s, "priority", 0) or 0), float(getattr(s, "weight", 1.0) or 1.0)),
            reverse=True,
        )
        if int(self.config.max_sessions_scanned or 0) > 0:
            ordered_specs = ordered_specs[: int(self.config.max_sessions_scanned)]
        ordered_specs, adaptive_degrade_applied = self._apply_adaptive_session_cap(ordered_specs=ordered_specs)
        by_session: Dict[str, List[MemoryRecord]] = {}
        ranked_lists: List[List[MemoryRecord]] = []
        weights: List[float] = []
        errors: Dict[str, str] = {}
        timed_out_sessions: List[str] = []

        def _run(spec: SessionSearchSpec) -> tuple[str, List[MemoryRecord], float]:
            q = MemoryQuery(**dict(base_query.__dict__))
            q.top_k = int(spec.top_k_override or max(1, int(base_query.top_k) * max(1, int(per_session_factor))))
            records = memory_fabric.recall(q, pre_search_sync=False)
            prefixes = [str(p or "") for p in (spec.source_prefixes or []) if str(p or "")]
            if prefixes:
                records = [r for r in records if any(str(getattr(r, "source", "")).startswith(p) for p in prefixes)]
            return spec.session_id, records, float(spec.weight or 1.0)

        limit = min(self.max_workers, len(ordered_specs))
        timeout_s = max(0.1, float(self.config.per_session_timeout_s or 3.0))
        with ThreadPoolExecutor(max_workers=max(1, limit)) as pool:
            future_to_sid = {pool.submit(_run, spec): spec.session_id for spec in ordered_specs}
            for fut, sid in future_to_sid.items():
                try:
                    sid_out, records, weight = fut.result(timeout=timeout_s)
                    by_session[sid_out] = records
                    ranked_lists.append(records)
                    weights.append(weight)
                except TimeoutError:
                    fut.cancel()
                    timed_out_sessions.append(sid)
                    errors[sid] = f"timeout({timeout_s}s)"
                    by_session[sid] = []
                except Exception as e:  # noqa: BLE001
                    errors[sid] = str(e)
                    by_session[sid] = []

        fused = rrf_merge_ranked_lists(
            ranked_lists=ranked_lists,
            weights=weights,
            k=rrf_k,
            top_k=(top_k if top_k is not None else base_query.top_k),
        )
        timeout_ratio = float(len(timed_out_sessions)) / float(max(1, len(ordered_specs)))
        timeout_pressure = timeout_ratio >= self._timeout_pressure_threshold()
        rerank_enabled_effective = bool(self.config.rerank_enabled) and (not timeout_pressure)
        rerank_cap = int(self.config.max_candidates_reranked or 0)
        if timeout_pressure and rerank_cap <= 0:
            rerank_cap = max(1, int((top_k if top_k is not None else base_query.top_k) * 2))
        rerank_cfg = SearchManagerConfig(**{**self.config.__dict__, "rerank_enabled": rerank_enabled_effective})
        if rerank_cap > 0 and len(fused) > rerank_cap:
            head = fused[:rerank_cap]
            head = _apply_rerank(records=head, query_domain=getattr(base_query, "domain", None), cfg=rerank_cfg)
            fused = head + fused[rerank_cap:]
        else:
            fused = _apply_rerank(records=fused, query_domain=getattr(base_query, "domain", None), cfg=rerank_cfg)
        return {
            "records": fused,
            "by_session": by_session,
            "total_sessions": len(ordered_specs),
            "session_hits": {sid: len(recs) for sid, recs in by_session.items()},
            "errors": errors,
            "timed_out_sessions": timed_out_sessions,
            "scheduled_sessions": [s.session_id for s in ordered_specs],
            "rerank_applied": bool(rerank_enabled_effective),
            "budget": {
                "max_sessions_scanned": int(self.config.max_sessions_scanned or 0),
                "max_candidates_reranked": int(rerank_cap),
                "adaptive_degrade_applied": bool(adaptive_degrade_applied or timeout_pressure),
                "timeout_pressure": bool(timeout_pressure),
            },
        }

    async def search_across_sessions_async(
        self,
        *,
        memory_fabric: Any,
        base_query: MemoryQuery,
        session_specs: Sequence[SessionSearchSpec],
        top_k: Optional[int] = None,
        per_session_factor: int = 3,
        rrf_k: int = 60,
        cancel_event: Optional[asyncio.Event] = None,
        overall_timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not session_specs:
            return {
                "records": [],
                "by_session": {},
                "total_sessions": 0,
                "session_hits": {},
                "errors": {},
                "timed_out_sessions": [],
                "cancelled_sessions": [],
                "cancelled": False,
            }

        ordered_specs = sorted(
            list(session_specs),
            key=lambda s: (int(getattr(s, "priority", 0) or 0), float(getattr(s, "weight", 1.0) or 1.0)),
            reverse=True,
        )
        if int(self.config.max_sessions_scanned or 0) > 0:
            ordered_specs = ordered_specs[: int(self.config.max_sessions_scanned)]
        ordered_specs, adaptive_degrade_applied = self._apply_adaptive_session_cap(
            ordered_specs=ordered_specs,
            overall_timeout_s=overall_timeout_s,
        )
        by_session: Dict[str, List[MemoryRecord]] = {}
        ranked_lists: List[List[MemoryRecord]] = []
        weights: List[float] = []
        errors: Dict[str, str] = {}
        timed_out_sessions: List[str] = []
        cancelled_sessions: List[str] = []
        cancelled = False

        timeout_s = max(0.1, float(self.config.per_session_timeout_s or 3.0))

        async def _run(spec: SessionSearchSpec) -> tuple[str, List[MemoryRecord], float]:
            q = MemoryQuery(**dict(base_query.__dict__))
            q.top_k = int(spec.top_k_override or max(1, int(base_query.top_k) * max(1, int(per_session_factor))))

            def _recall_sync() -> List[MemoryRecord]:
                records = memory_fabric.recall(q, pre_search_sync=False)
                prefixes = [str(p or "") for p in (spec.source_prefixes or []) if str(p or "")]
                if prefixes:
                    records = [r for r in records if any(str(getattr(r, "source", "")).startswith(p) for p in prefixes)]
                return records

            records = await asyncio.to_thread(_recall_sync)
            return spec.session_id, records, float(spec.weight or 1.0)

        async def _run_guarded(spec: SessionSearchSpec) -> tuple[str, Optional[List[MemoryRecord]], float, str]:
            if cancel_event is not None and cancel_event.is_set():
                return spec.session_id, None, float(spec.weight or 1.0), "cancelled"
            try:
                sid, recs, weight = await asyncio.wait_for(_run(spec), timeout=timeout_s)
                return sid, recs, weight, "ok"
            except asyncio.TimeoutError:
                return spec.session_id, None, float(spec.weight or 1.0), "timeout"
            except Exception as e:  # noqa: BLE001
                return spec.session_id, None, float(spec.weight or 1.0), f"error:{e}"

        async def _run_all() -> List[tuple[str, Optional[List[MemoryRecord]], float, str]]:
            sem = asyncio.Semaphore(max(1, min(self.max_workers, len(ordered_specs))))

            async def _bounded(spec: SessionSearchSpec) -> tuple[str, Optional[List[MemoryRecord]], float, str]:
                async with sem:
                    return await _run_guarded(spec)

            tasks = [asyncio.create_task(_bounded(spec)) for spec in ordered_specs]
            return await asyncio.gather(*tasks, return_exceptions=False)

        try:
            rows = (
                await asyncio.wait_for(_run_all(), timeout=max(0.1, float(overall_timeout_s)))
                if overall_timeout_s is not None
                else await _run_all()
            )
        except asyncio.TimeoutError:
            cancelled = True
            rows = [(spec.session_id, None, float(spec.weight or 1.0), "timeout") for spec in ordered_specs]

        for sid, records, weight, status in rows:
            if status == "ok" and records is not None:
                by_session[sid] = records
                ranked_lists.append(records)
                weights.append(weight)
                continue
            by_session[sid] = []
            if status == "timeout":
                timed_out_sessions.append(sid)
                errors[sid] = f"timeout({timeout_s}s)"
            elif status == "cancelled":
                cancelled_sessions.append(sid)
                errors[sid] = "cancelled"
                cancelled = True
            elif status.startswith("error:"):
                errors[sid] = status.replace("error:", "", 1)

        fused = rrf_merge_ranked_lists(
            ranked_lists=ranked_lists,
            weights=weights,
            k=rrf_k,
            top_k=(top_k if top_k is not None else base_query.top_k),
        )
        timeout_ratio = float(len(timed_out_sessions)) / float(max(1, len(ordered_specs)))
        timeout_pressure = timeout_ratio >= self._timeout_pressure_threshold()
        rerank_enabled_effective = bool(self.config.rerank_enabled) and (not timeout_pressure)
        rerank_cap = int(self.config.max_candidates_reranked or 0)
        if timeout_pressure and rerank_cap <= 0:
            rerank_cap = max(1, int((top_k if top_k is not None else base_query.top_k) * 2))
        rerank_cfg = SearchManagerConfig(**{**self.config.__dict__, "rerank_enabled": rerank_enabled_effective})
        if rerank_cap > 0 and len(fused) > rerank_cap:
            head = fused[:rerank_cap]
            head = _apply_rerank(records=head, query_domain=getattr(base_query, "domain", None), cfg=rerank_cfg)
            fused = head + fused[rerank_cap:]
        else:
            fused = _apply_rerank(records=fused, query_domain=getattr(base_query, "domain", None), cfg=rerank_cfg)
        return {
            "records": fused,
            "by_session": by_session,
            "total_sessions": len(ordered_specs),
            "session_hits": {sid: len(recs) for sid, recs in by_session.items()},
            "errors": errors,
            "timed_out_sessions": timed_out_sessions,
            "cancelled_sessions": cancelled_sessions,
            "cancelled": cancelled,
            "scheduled_sessions": [s.session_id for s in ordered_specs],
            "rerank_applied": bool(rerank_enabled_effective),
            "budget": {
                "max_sessions_scanned": int(self.config.max_sessions_scanned or 0),
                "max_candidates_reranked": int(rerank_cap),
                "adaptive_degrade_applied": bool(adaptive_degrade_applied or timeout_pressure),
                "timeout_pressure": bool(timeout_pressure),
            },
        }
