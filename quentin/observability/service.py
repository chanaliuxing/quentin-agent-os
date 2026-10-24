# quentin/observability/service.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json
import os

from quentin.diagnostics.intelligence_auditor import build_intelligence_audit


def _read_jsonl(path: Path, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    if limit is not None and limit > 0:
        return rows[-limit:]
    return rows


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _group_key(*parts: str) -> str:
    return "::".join(str(p or "unknown") for p in parts)


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    xs = sorted(float(v) for v in values)
    if len(xs) == 1:
        return xs[0]
    pos = max(0.0, min(1.0, float(p))) * float(len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    if lo == hi:
        return xs[lo]
    frac = pos - float(lo)
    return xs[lo] + ((xs[hi] - xs[lo]) * frac)


def _embedding_batch_hints(*, provider: str, batch: Dict[str, Any], embedding_failure_rate: Optional[float] = None) -> List[str]:
    hints: List[str] = []
    p = str(provider or "unknown").strip().lower()
    pd = int(batch.get("provider_disabled_total") or 0)
    fb = int(batch.get("fallback_calls_total") or 0)
    rt = int(batch.get("retry_attempts_total") or 0)
    if pd > 0:
        if p == "openai":
            hints.append("openai_batch_disabled_check_api_key_org_billing")
        elif p == "gemini":
            hints.append("gemini_batch_disabled_check_api_key_project_quota")
        else:
            hints.append("embedding_batch_disabled_check_provider_credentials_and_quota")
    if fb >= 5:
        hints.append("embedding_batch_fallback_spike_consider_reduce_concurrency_or_batch_size")
    if rt >= 20:
        hints.append("embedding_retry_pressure_high_consider_backoff_and_rate_limit_tuning")
    if embedding_failure_rate is not None and embedding_failure_rate >= 0.2:
        hints.append("embedding_failure_rate_high_check_provider_health_and_credentials")
    return hints


def _memory_performance_hints(*, fabric_status: Dict[str, Any], total_records: Optional[int] = None) -> List[str]:
    hints: List[str] = []
    vec = (fabric_status or {}).get("vector") if isinstance(fabric_status, dict) else {}
    if not isinstance(vec, dict):
        return hints
    backend = str(vec.get("backend") or "unknown").strip().lower()
    math_backend = str(vec.get("math_backend") or "unknown").strip().lower()
    total = int(total_records or int((fabric_status or {}).get("total_records") or 0))
    if backend == "client_scan" and total >= 5000:
        hints.append("memory_vector_backend_client_scan_enable_sqlite_vec_or_pgvector_for_large_scale")
    if backend == "client_scan" and math_backend == "python":
        hints.append("memory_vector_math_python_only_install_numpy_or_enable_vector_index")
    warnings = (fabric_status or {}).get("warnings") if isinstance(fabric_status, dict) else None
    if isinstance(warnings, list) and "large_corpus_without_fts_or_sqlite_vec" in warnings:
        hints.append("memory_text_path_without_fts_enable_quentin_memory_fts_for_large_corpus")
    return hints


def _count_jsonl_lines(path: Path, *, limit: Optional[int] = None) -> int:
    if not path.exists():
        return 0
    n = 0
    try:
        with path.open("r", encoding="utf-8") as f:
            for _ in f:
                n += 1
                if limit is not None and limit > 0 and n >= limit:
                    break
    except Exception:
        return 0
    return n


def _resolve_task_queue_path(*, repo_root: Path) -> Path:
    override = str((os.environ.get("QUENTIN_TASK_QUEUE_PATH") or "")).strip()
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        return p
    return (repo_root / "data" / "tasks" / "queue.jsonl").resolve()


@dataclass
class ObservabilityService:
    """
    Blueprint v3 observability facade.

    Design goal:
    - Stable output schema (fields always present; values may be 0/null when unavailable)
    - Prefer reading persisted artifacts under `data/` so overview works even without a live runtime.
    """

    runtime: Optional[Any] = None
    repo_root: str | Path = "."

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root).resolve()

    # --------------------------------------------------------------------- Core aggregations
    async def get_overview(self) -> Dict[str, Any]:
        task = self._task_metrics()
        actions = self._action_metrics()
        tools = self._tool_metrics()
        memory = self._memory_metrics()
        patches = self._patch_metrics()
        release = self._release_metrics()
        intelligence = self._intelligence_metrics()
        communication = self._communication_metrics()
        intelligence_audit = build_intelligence_audit(repo_root=self.repo_root)
        experiments = await self._experiment_metrics()

        overview = {
            "timestamp": datetime.now(UTC).isoformat(),
            "domain": {
                "task": task,
                "actions": actions,
            },
            "tools": tools,
            "memory": memory,
            "patches": patches,
            "release": release,
            "intelligence": intelligence,
            "communication": communication,
            "intelligence_audit": intelligence_audit,
            "experiments": experiments,
        }

        # Optional persistence into MemoryFabric for cross-session learning (default OFF).
        if (os.getenv("QUENTIN_DIAGNOSTICS_TO_MEMORY", "0") or "").strip().lower() in ("1", "true", "yes", "on"):
            try:
                from quentin.memory.fabric import MemoryFabric
                from quentin.memory.models import MemoryTier

                fabric = MemoryFabric(repo_root=self.repo_root, trace_recorder=None)
                fabric.remember_atomic(
                    content=f"observability_overview {json.dumps({'timestamp': overview.get('timestamp'), 'intelligence_audit': intelligence_audit}, ensure_ascii=False)}",
                    source="observability",
                    tier=MemoryTier.STS,
                    domain="core",
                    importance=0.2,
                    metadata={"overview": overview, "intelligence_audit": intelligence_audit},
                    kind="episodic",
                )
            except Exception:
                pass
        # Optional event bridge into SystemEventQueue (pluggable EventStore backend).
        try:
            events_on = (os.getenv("QUENTIN_DIAGNOSTICS_TO_EVENTS", "0") or "").strip().lower() in ("1", "true", "yes", "on")
            global_events_on = (os.getenv("QUENTIN_OUTCOME_EVENTS", "0") or "").strip().lower() in ("1", "true", "yes", "on")
            if events_on or global_events_on:
                from quentin.runtime.system_events import SystemEventQueue

                queue = SystemEventQueue(repo_root=self.repo_root)
                queue.enqueue_event(
                    session_id=str(os.getenv("QUENTIN_SESSION_ID", "brain") or "brain"),
                    event_type="diagnostics_overview_ready",
                    payload={
                        "timestamp": str(overview.get("timestamp") or ""),
                        "intelligence_audit": intelligence_audit,
                    },
                    source="observability",
                )
        except Exception:
            pass

        return overview

    # --------------------------------------------------------------------- Communication / listener telemetry
    def _communication_metrics(self) -> Dict[str, Any]:
        listener_count = 0
        restart_total = 0
        dropped_total = 0
        restart_reasons: Dict[str, int] = {}
        by_platform: List[Dict[str, Any]] = []
        try:
            from quentin.infra.channels.listener_manager import listener_manager

            st = listener_manager.status()
        except Exception:
            st = {"status": "error", "listeners": [], "count": 0}

        for li in list(st.get("listeners") or []):
            if not isinstance(li, dict):
                continue
            listener_count += 1
            rc = int(li.get("restart_count") or 0)
            dc = int(li.get("dropped_count") or 0)
            restart_total += rc
            dropped_total += dc
            p = str(li.get("platform") or "unknown")
            row = {
                "platform": p,
                "status": str(li.get("status") or "unknown"),
                "restart_count": rc,
                "dropped_count": dc,
                "last_restart_reason": str(li.get("last_restart_reason") or ""),
                "backoff_profile": str(li.get("backoff_profile") or "exponential"),
                "rate_limit_per_min": int(li.get("rate_limit_per_min") or 0),
            }
            by_platform.append(row)
            for k, v in dict(li.get("restart_reasons") or {}).items():
                kk = str(k or "").strip() or "unknown"
                try:
                    restart_reasons[kk] = restart_reasons.get(kk, 0) + int(v or 0)
                except Exception:
                    continue

        now_ts = datetime.now(UTC).timestamp()
        listener_state = self.repo_root / "data" / "channels" / "listener_state.json"
        dead_total = 0
        dead_by_platform: Dict[str, int] = {}
        dead_recent = 0
        dead_prev = 0
        dead_window_sec = max(600, int(os.getenv("QUENTIN_DEAD_LETTER_TREND_WINDOW_SEC", "43200") or "43200"))
        if listener_state.exists():
            try:
                raw = json.loads(listener_state.read_text(encoding="utf-8"))
            except Exception:
                raw = {}
            dead = list((raw or {}).get("dead_letters") or [])
            dead_total = len(dead)
            for d in dead:
                if not isinstance(d, dict):
                    continue
                p = str(d.get("platform") or "unknown")
                dead_by_platform[p] = dead_by_platform.get(p, 0) + 1
                ts = _safe_float(d.get("ts")) or 0.0
                if ts <= 0.0:
                    continue
                age = now_ts - ts
                if 0.0 <= age < float(dead_window_sec):
                    dead_recent += 1
                elif float(dead_window_sec) <= age < float(dead_window_sec * 2):
                    dead_prev += 1
        dead_growth_ratio = (float(dead_recent) / max(1.0, float(dead_prev))) if dead_recent > 0 else 0.0

        canvas_file = self.repo_root / "data" / "canvas_components.json"
        canvas_ack_pending = 0
        canvas_active = 0
        canvas_ack_timeout_sec = int(os.getenv("QUENTIN_CANVAS_ACK_TIMEOUT_SEC", "120") or "120")
        if canvas_file.exists():
            try:
                cdata = json.loads(canvas_file.read_text(encoding="utf-8"))
            except Exception:
                cdata = {}
            comps = (cdata or {}).get("components") if isinstance(cdata, dict) else {}
            if isinstance(comps, dict):
                for _, node in comps.items():
                    if not isinstance(node, dict):
                        continue
                    stt = str(node.get("status") or "active").strip().lower()
                    if stt not in {"active", "pending", "running"}:
                        continue
                    canvas_active += 1
                    last_ack = node.get("last_ack") if isinstance(node.get("last_ack"), dict) else {}
                    last_ack_ts = _safe_float((last_ack or {}).get("ts")) or 0.0
                    updated_at = _safe_float(node.get("updated_at")) or 0.0
                    ref_ts = max(last_ack_ts, updated_at)
                    age_sec = max(0.0, now_ts - ref_ts)
                    if ref_ts <= 0.0 or age_sec >= float(canvas_ack_timeout_sec):
                        canvas_ack_pending += 1

        leases_file = self.repo_root / "data" / "nodes_leases.json"
        lease_events_file = self.repo_root / "data" / "metrics" / "lease_events.jsonl"
        lease_total = 0
        lease_expired = 0
        lease_expiring_soon = 0
        lease_expiring_threshold_sec = max(5, int(os.getenv("QUENTIN_LEASE_EXPIRING_SOON_SEC", "30") or "30"))
        leader_epoch_max = 0
        if leases_file.exists():
            try:
                lraw = json.loads(leases_file.read_text(encoding="utf-8"))
            except Exception:
                lraw = {}
            leases = (lraw or {}).get("leases") if isinstance(lraw, dict) else {}
            if isinstance(leases, dict):
                for _, rec in leases.items():
                    if not isinstance(rec, dict):
                        continue
                    lease_total += 1
                    exp = _safe_float(rec.get("expires_at")) or 0.0
                    if exp <= now_ts:
                        lease_expired += 1
                    elif (exp - now_ts) <= float(lease_expiring_threshold_sec):
                        lease_expiring_soon += 1
                    ek = str(rec.get("lease_key") or "")
                    if ek.startswith("leader::"):
                        leader_epoch_max = max(leader_epoch_max, int(rec.get("epoch") or 0))

        lease_recent_window_sec = max(300, int(os.getenv("QUENTIN_LEASE_EVENT_WINDOW_SEC", "3600") or "3600"))
        lease_recent_events = 0
        lease_contention_events = 0
        lease_fencing_conflicts = 0
        lease_quorum_failures = 0
        if lease_events_file.exists():
            rows = _read_jsonl(lease_events_file, limit=5000)
            for r in rows:
                ts = _safe_float(r.get("ts")) or 0.0
                if ts <= 0.0 or (now_ts - ts) > float(lease_recent_window_sec):
                    continue
                lease_recent_events += 1
                kind = str(r.get("kind") or "")
                if kind in {"leader_blocked_higher_priority", "acquire_blocked"}:
                    lease_contention_events += 1
                if kind == "fencing_conflict":
                    lease_fencing_conflicts += 1
                if kind == "quorum_not_met":
                    lease_quorum_failures += 1

        return {
            "listeners": {
                "count": int(listener_count),
                "restart_total": int(restart_total),
                "dropped_total": int(dropped_total),
                "restart_reasons": restart_reasons,
                "by_platform": by_platform,
            },
            "dead_letters": {
                "total": int(dead_total),
                "by_platform": dead_by_platform,
                "trend": {
                    "window_sec": int(dead_window_sec),
                    "recent_count": int(dead_recent),
                    "previous_count": int(dead_prev),
                    "growth_ratio": float(dead_growth_ratio),
                },
                "source": "data/channels/listener_state.json",
            },
            "canvas_handshake": {
                "ack_timeout_sec": int(canvas_ack_timeout_sec),
                "active_components": int(canvas_active),
                "ack_pending": int(canvas_ack_pending),
                "source": "data/canvas_components.json",
            },
            "leases": {
                "total": int(lease_total),
                "expired_count": int(lease_expired),
                "expiring_soon_count": int(lease_expiring_soon),
                "expiring_soon_threshold_sec": int(lease_expiring_threshold_sec),
                "leader_epoch_max": int(leader_epoch_max),
                "recent_event_window_sec": int(lease_recent_window_sec),
                "recent_event_count": int(lease_recent_events),
                "contention_events_recent": int(lease_contention_events),
                "fencing_conflicts_recent": int(lease_fencing_conflicts),
                "quorum_failures_recent": int(lease_quorum_failures),
                "sources": [
                    "data/nodes_leases.json",
                    "data/metrics/lease_events.jsonl",
                ],
            },
        }

    # --------------------------------------------------------------------- Tasks
    def _task_metrics(self) -> Dict[str, Any]:
        events_path = self.repo_root / "data" / "traces" / "events.jsonl"
        summaries_path = self.repo_root / "data" / "traces" / "summaries.jsonl"

        events = _read_jsonl(events_path, limit=5000)
        summaries = _read_jsonl(summaries_path, limit=5000)

        # trace_id -> domain/environment mapping from TASK_RECEIVED payloads
        trace_meta: Dict[str, Dict[str, str]] = {}
        for e in events:
            if str(e.get("event_type")) != "task_received":
                continue
            payload = e.get("payload") or {}
            ctx = payload.get("context") or {}
            trace_meta[str(e.get("trace_id"))] = {
                "domain": str(ctx.get("domain") or payload.get("domain") or "unknown"),
                "environment": str(ctx.get("environment") or payload.get("environment") or "unknown"),
            }

        by_domain: Dict[str, Dict[str, Any]] = {}
        total = 0
        for s in summaries:
            trace_id = str(s.get("trace_id") or "")
            status = str(s.get("status") or "unknown")
            meta = trace_meta.get(trace_id) or {"domain": "unknown", "environment": "unknown"}
            domain = meta["domain"]
            env = meta["environment"]
            key = _group_key(domain, env)
            bucket = by_domain.setdefault(
                key,
                {
                    "domain": domain,
                    "environment": env,
                    "tasks": 0,
                    "success": 0,
                    "failed": 0,
                    "partial": 0,
                },
            )
            bucket["tasks"] += 1
            total += 1
            if status == "success":
                bucket["success"] += 1
            elif status == "failed":
                bucket["failed"] += 1
            else:
                bucket["partial"] += 1

        rows = list(by_domain.values())
        for r in rows:
            tasks = max(1, int(r.get("tasks") or 0))
            r["success_rate"] = (float(r.get("success") or 0) / tasks) if tasks else 0.0

        return {
            "total_tasks": total,
            "by_domain_env": rows,
            "source": "data/traces/*.jsonl",
        }

    # --------------------------------------------------------------------- Actions (LLM/tool/patch/experiment)
    def _action_metrics(self) -> Dict[str, Any]:
        policy_path = self.repo_root / "data" / "policy_decisions.jsonl"
        audit_path = self.repo_root / "data" / "audit_events.jsonl"

        policy_rows = _read_jsonl(policy_path, limit=10000)
        audit_rows = _read_jsonl(audit_path, limit=20000)

        # action_id -> action meta (domain/env/type)
        action_meta: Dict[str, Dict[str, str]] = {}
        for row in policy_rows:
            act = (row.get("action") or {}) if isinstance(row.get("action"), dict) else {}
            action_id = str(act.get("action_id") or "")
            if not action_id:
                continue
            action_meta[action_id] = {
                "action_type": str(act.get("action_type") or "unknown"),
                "domain": str(act.get("domain") or "unknown"),
                "environment": str(act.get("environment") or "unknown"),
                "risk_level": str(act.get("risk_level") or "unknown"),
            }

        # Aggregate decisions by (domain, env, action_type)
        counts: Dict[str, Dict[str, Any]] = {}
        for row in policy_rows:
            act = row.get("action") or {}
            dec = row.get("decision") or {}
            action_id = str(act.get("action_id") or "")
            domain = str(act.get("domain") or "unknown")
            env = str(act.get("environment") or "unknown")
            action_type = str(act.get("action_type") or "unknown")
            allow = bool(dec.get("allow", False))
            key = _group_key(domain, env, action_type)
            bucket = counts.setdefault(
                key,
                {
                    "domain": domain,
                    "environment": env,
                    "action_type": action_type,
                    "requests": 0,
                    "allowed": 0,
                    "denied": 0,
                    "estimated_cost_tokens": 0,
                },
            )
            bucket["requests"] += 1
            bucket["estimated_cost_tokens"] += int(act.get("estimated_cost_tokens") or 0)
            if allow:
                bucket["allowed"] += 1
            else:
                bucket["denied"] += 1

        # Latency/cost from audits (best-effort)
        latency_by_key: Dict[str, List[float]] = {}
        llm_tokens_by_key: Dict[str, List[int]] = {}
        for row in audit_rows:
            action_id = str(row.get("action_id") or "")
            phase = str(row.get("phase") or "")
            payload = row.get("payload") or {}
            meta = action_meta.get(action_id)
            if not meta:
                continue
            key = _group_key(meta["domain"], meta["environment"], meta["action_type"])
            if phase not in ("success", "error"):
                continue
            lat = _safe_float(payload.get("latency_ms"))
            if lat is not None:
                latency_by_key.setdefault(key, []).append(lat)
            # LLM usage (remote providers): attempt to extract token counts from audit payload.
            if meta.get("action_type") == "llm_call":
                remote = payload.get("remote_meta") or {}
                usage = remote.get("usage") if isinstance(remote, dict) else None
                if isinstance(usage, dict):
                    total = usage.get("total_tokens")
                    if total is None:
                        # Some providers use different keys; keep best-effort.
                        total = usage.get("totalTokens") or usage.get("total_token_count")
                    it = _safe_int(total)
                    if it is not None:
                        llm_tokens_by_key.setdefault(key, []).append(it)

        rows = list(counts.values())
        for r in rows:
            key = _group_key(r["domain"], r["environment"], r["action_type"])
            latencies = latency_by_key.get(key) or []
            r["avg_latency_ms"] = (sum(latencies) / len(latencies)) if latencies else None
            if r["action_type"] == "llm_call":
                toks = llm_tokens_by_key.get(key) or []
                r["avg_total_tokens"] = (sum(toks) / len(toks)) if toks else None
            reqs = max(1, int(r.get("requests") or 0))
            r["allow_rate"] = float(r.get("allowed") or 0) / reqs

        return {
            "by_domain_env_action": rows,
            "sources": ["data/policy_decisions.jsonl", "data/audit_events.jsonl"],
        }

    # --------------------------------------------------------------------- Tools (per tool_name)
    def _tool_metrics(self) -> Dict[str, Any]:
        events_path = self.repo_root / "data" / "traces" / "events.jsonl"
        events = _read_jsonl(events_path, limit=20000)
        counts: Dict[str, Dict[str, Any]] = {}
        for e in events:
            if str(e.get("event_type")) != "tool_call":
                continue
            payload = e.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            tool_name = str(payload.get("tool_name") or "unknown")
            phase = str(payload.get("phase") or "")
            bucket = counts.setdefault(
                tool_name,
                {"tool_name": tool_name, "calls": 0, "success": 0, "failed": 0, "avg_latency_ms": None},
            )
            bucket["calls"] += 1
            if phase == "success":
                bucket["success"] += 1
            elif phase:
                bucket["failed"] += 1

        # Latency (best-effort) from audit logs, keyed by tool_name.
        audit_path = self.repo_root / "data" / "audit_events.jsonl"
        audit_rows = _read_jsonl(audit_path, limit=50000)
        latency: Dict[str, List[float]] = {}
        for row in audit_rows:
            if str(row.get("event_type")) != "tool_call":
                continue
            payload = row.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            tool_name = str(payload.get("tool_name") or "unknown")
            lat = _safe_float(payload.get("latency_ms"))
            if lat is not None:
                latency.setdefault(tool_name, []).append(lat)

        rows = []
        for tool_name, b in counts.items():
            lats = latency.get(tool_name) or []
            b["avg_latency_ms"] = (sum(lats) / len(lats)) if lats else None
            b["success_rate"] = (float(b["success"]) / float(max(1, b["calls"]))) if b["calls"] else 0.0
            rows.append(b)
        rows.sort(key=lambda r: (-(r.get("calls") or 0), r.get("tool_name") or ""))
        return {"by_tool": rows, "source": "data/traces/events.jsonl + data/audit_events.jsonl"}

    # --------------------------------------------------------------------- Memory
    def _memory_metrics(self) -> Dict[str, Any]:
        events_path = self.repo_root / "data" / "traces" / "events.jsonl"
        events = _read_jsonl(events_path, limit=20000)

        memory_events = [e for e in events if str(e.get("event_type")) == "memory"]
        sleep_events = [e for e in events if str(e.get("event_type")) == "sleep"]

        # Aggregate MemoryFabric events (best-effort).
        by_action: Dict[str, Dict[str, Any]] = {}
        totals = {
            "remember": 0,
            "recall": 0,
            "recall_across_sessions": 0,
            "recall_across_sessions_async": 0,
            "promote_to_mts": 0,
            "promote_to_lts": 0,
            "decay_records": 0,
        }
        vector_status: Dict[str, int] = {}
        recall = {
            "calls": 0,
            "vector_calls": 0,
            "results_total": 0,
            "latency_ms_total": 0.0,
            "latency_ms_count": 0,
            "latency_ms_p50": None,
            "latency_ms_p95": None,
            "hybrid_calls": 0,
            "source_counts": {},
            "candidate_totals": {"text": 0, "vec": 0, "fused": 0},
            "candidate_samples": 0,
            "cross_session_calls": 0,
            "cross_session_async_calls": 0,
            "cross_session_timeouts": 0,
            "cross_session_cancelled": 0,
        }
        recall_latencies: List[float] = []
        recall_hit_buckets: Dict[str, Dict[str, Any]] = {}

        for e in memory_events:
            payload = e.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            action = str(payload.get("action") or "unknown")
            bucket = by_action.setdefault(action, {"action": action, "events": 0, "items": 0})
            bucket["events"] += 1

            if action == "remember":
                totals["remember"] += 1
                vs = str(payload.get("vector_status") or "unknown")
                vector_status[vs] = vector_status.get(vs, 0) + 1
                bucket["items"] += 1
            elif action == "recall":
                totals["recall"] += 1
                recall["calls"] += 1
                if bool(payload.get("use_vector")):
                    recall["vector_calls"] += 1
                if str(payload.get("mode") or "") == "hybrid":
                    recall["hybrid_calls"] += 1
                rc = _safe_int(payload.get("result_count")) or 0
                recall["results_total"] += int(rc)
                lat = _safe_float(payload.get("latency_ms"))
                if lat is not None:
                    recall["latency_ms_total"] += float(lat)
                    recall["latency_ms_count"] += 1
                    recall_latencies.append(float(lat))
                bucket["items"] += int(rc)
                tier = str(payload.get("query_tier") or "unknown")
                kind = str(payload.get("query_kind") or "unknown")
                domain = str(payload.get("query_domain") or "unknown")
                hit_key = _group_key(tier, kind, domain)
                hb = recall_hit_buckets.setdefault(
                    hit_key,
                    {"tier": tier, "kind": kind, "domain": domain, "calls": 0, "hits": 0},
                )
                hb["calls"] += 1
                if rc > 0:
                    hb["hits"] += 1
                src_counts = payload.get("source_counts") or {}
                if isinstance(src_counts, dict):
                    for src, cnt in src_counts.items():
                        sk = str(src or "unknown")
                        try:
                            c = int(cnt or 0)
                        except Exception:
                            c = 0
                        recall["source_counts"][sk] = int(recall["source_counts"].get(sk, 0)) + c
                tc = _safe_int(payload.get("text_count"))
                vc = _safe_int(payload.get("vec_count"))
                fc = _safe_int(payload.get("fused_count"))
                if tc is not None or vc is not None or fc is not None:
                    recall["candidate_samples"] += 1
                    if tc is not None:
                        recall["candidate_totals"]["text"] += int(tc)
                    if vc is not None:
                        recall["candidate_totals"]["vec"] += int(vc)
                    if fc is not None:
                        recall["candidate_totals"]["fused"] += int(fc)
            elif action in ("recall_across_sessions", "recall_across_sessions_async"):
                if action in totals:
                    totals[action] += 1
                recall["cross_session_calls"] += 1
                if action == "recall_across_sessions_async":
                    recall["cross_session_async_calls"] += 1
                    if bool(payload.get("cancelled")):
                        recall["cross_session_cancelled"] += 1
                tos = payload.get("timed_out_sessions") or []
                if isinstance(tos, list):
                    recall["cross_session_timeouts"] += len(tos)
            elif action in ("promote_to_mts", "promote_to_lts", "decay_records"):
                ids = payload.get("ids") or []
                count = len(ids) if isinstance(ids, list) else 0
                bucket["items"] += int(count)
                if action in totals:
                    totals[action] += int(count)

        sleep_outputs = {
            "training_pairs": 0,
            "skill_candidates": 0,
            "procedural_memories": 0,
            "consolidated_traces": 0,
        }
        for e in sleep_events:
            payload = e.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            if str(payload.get("action") or "") != "v3_outputs_emitted":
                continue
            sleep_outputs["training_pairs"] += int(payload.get("training_pairs") or 0)
            sleep_outputs["skill_candidates"] += int(payload.get("skill_candidates") or 0)
            sleep_outputs["procedural_memories"] += int(payload.get("procedural_memories") or 0)
            sleep_outputs["consolidated_traces"] += int(payload.get("consolidated_traces") or 0)

        tp_path = self.repo_root / "data" / "training_pairs" / "training_pairs.jsonl"
        sc_path = self.repo_root / "data" / "training_pairs" / "skill_candidates.jsonl"
        tp_lines = _count_jsonl_lines(tp_path)
        sc_lines = _count_jsonl_lines(sc_path)

        # Try runtime-provided stats if available (as an override).
        memory = getattr(self.runtime, "memory", None) or getattr(self.runtime, "memory_fabric", None)
        if memory is not None and hasattr(memory, "stats") and callable(getattr(memory, "stats")):
            try:
                stats = memory.stats()
                if hasattr(stats, "__await__"):
                    # Caller can await if desired; keep overview non-blocking by skipping in sync path.
                    pass
                else:
                    return {
                        "tiers": stats,
                        "total": None,
                        "events": {"by_action": list(by_action.values()), "totals": totals, "vector_status": vector_status, "recall": recall},
                        "sleep_outputs": sleep_outputs,
                        "training_pairs": {"lines": tp_lines, "path": str(tp_path)},
                        "skill_candidates": {"lines": sc_lines, "path": str(sc_path)},
                        "fabric_status": stats if isinstance(stats, dict) else {},
                        "embedding_batch": {
                            "retry_attempts_total": int(((stats or {}).get("batch") or {}).get("retry_attempts_total") or 0),
                            "fallback_calls_total": int(((stats or {}).get("batch") or {}).get("fallback_calls_total") or 0),
                            "resumed_jobs_total": int(((stats or {}).get("batch") or {}).get("resumed_jobs_total") or 0),
                            "provider_disabled_total": int(((stats or {}).get("batch") or {}).get("provider_disabled_total") or 0),
                        },
                        "embedding_batch_hints": _embedding_batch_hints(
                            provider=str((stats or {}).get("provider") or "unknown"),
                            batch=((stats or {}).get("batch") or {}),
                        ),
                        "memory_performance_hints": _memory_performance_hints(
                            fabric_status=(stats if isinstance(stats, dict) else {}),
                            total_records=int((stats or {}).get("total_records") or 0),
                        ),
                        "sources": ["runtime.memory.stats()", str(events_path), str(tp_path), str(sc_path)],
                    }
            except Exception:
                pass

        # Fallback: read SQLite memory.db if present.
        db_path = self.repo_root / "data" / "memory.db"
        tiers: Dict[str, int] = {}
        total = 0
        source = "none"

        if db_path.exists():
            try:
                import sqlite3

                conn = sqlite3.connect(str(db_path))
                try:
                    cur = conn.execute("SELECT tier, COUNT(1) FROM memories GROUP BY tier")
                    rows = cur.fetchall()
                finally:
                    conn.close()
                for tier, cnt in rows:
                    tiers[str(tier)] = int(cnt)
                    total += int(cnt)
                source = str(db_path)
            except Exception:
                source = f"sqlite_error:{db_path}"

        embedding_health = {}
        try:
            from quentin.infra.llm.embeddings import get_embedding_health_snapshot
            embedding_health = get_embedding_health_snapshot()
        except Exception:
            embedding_health = {}

        embedding_failure_rate = None
        try:
            total_success = 0
            total_failure = 0
            for s in embedding_health.values():
                total_success += int(s.get("success") or 0)
                total_failure += int(s.get("failure") or 0)
            denom = total_success + total_failure
            embedding_failure_rate = (float(total_failure) / float(denom)) if denom else None
        except Exception:
            embedding_failure_rate = None

        if recall["latency_ms_count"] > 0:
            recall["avg_latency_ms"] = recall["latency_ms_total"] / float(recall["latency_ms_count"])
            recall["latency_ms_p50"] = _percentile(recall_latencies, 0.50)
            recall["latency_ms_p95"] = _percentile(recall_latencies, 0.95)
        else:
            recall["avg_latency_ms"] = None
            recall["latency_ms_p50"] = None
            recall["latency_ms_p95"] = None
        if recall["calls"] > 0:
            recall["hybrid_ratio"] = float(recall["hybrid_calls"]) / float(recall["calls"])
        else:
            recall["hybrid_ratio"] = 0.0
        if recall["candidate_samples"] > 0:
            samples = float(recall["candidate_samples"])
            recall["candidate_avg"] = {
                "text": float(recall["candidate_totals"]["text"]) / samples,
                "vec": float(recall["candidate_totals"]["vec"]) / samples,
                "fused": float(recall["candidate_totals"]["fused"]) / samples,
            }
        else:
            recall["candidate_avg"] = {"text": 0.0, "vec": 0.0, "fused": 0.0}
        recall_hit_rate = []
        for hb in recall_hit_buckets.values():
            calls = int(hb.get("calls") or 0)
            hits = int(hb.get("hits") or 0)
            hb["hit_rate"] = (float(hits) / float(calls)) if calls else 0.0
            recall_hit_rate.append(hb)
        recall_hit_rate.sort(key=lambda x: (-(x.get("calls") or 0), x.get("tier") or ""))

        fabric_status = {
            "store": "sqlite_file" if db_path.exists() else "none",
            "provider": "unknown",
            "model": "unknown",
            "tier_counts": dict(tiers),
            "total_records": int(total),
        }
        embedding_batch = {
            "retry_attempts_total": int(((fabric_status or {}).get("batch") or {}).get("retry_attempts_total") or 0),
            "fallback_calls_total": int(((fabric_status or {}).get("batch") or {}).get("fallback_calls_total") or 0),
            "resumed_jobs_total": int(((fabric_status or {}).get("batch") or {}).get("resumed_jobs_total") or 0),
            "provider_disabled_total": int(((fabric_status or {}).get("batch") or {}).get("provider_disabled_total") or 0),
        }

        return {
            "tiers": tiers,
            "total": total,
            "events": {
                "by_action": list(by_action.values()),
                "totals": totals,
                "vector_status": vector_status,
                "recall": recall,
                "recall_hit_rate": recall_hit_rate,
            },
            "embedding_health": embedding_health,
            "embedding_failure_rate": embedding_failure_rate,
            "sleep_outputs": sleep_outputs,
            "training_pairs": {"lines": tp_lines, "path": str(tp_path)},
            "skill_candidates": {"lines": sc_lines, "path": str(sc_path)},
            "fabric_status": fabric_status,
            "embedding_batch": embedding_batch,
            "embedding_batch_hints": _embedding_batch_hints(
                provider=str(fabric_status.get("provider") or "unknown"),
                batch=embedding_batch,
                embedding_failure_rate=embedding_failure_rate,
            ),
            "memory_performance_hints": _memory_performance_hints(
                fabric_status=fabric_status,
                total_records=int(total or 0),
            ),
            "sources": [source, str(events_path), str(tp_path), str(sc_path)],
        }

    # --------------------------------------------------------------------- Patches
    def _patch_metrics(self) -> Dict[str, Any]:
        store_path = self.repo_root / "data" / "patches.json"
        reports_dir = self.repo_root / "data" / "patch_reports"

        patches = []
        if store_path.exists():
            try:
                data = json.loads(store_path.read_text(encoding="utf-8") or "{}")
                patches = list((data.get("patches") or {}).values()) if isinstance(data, dict) else []
            except Exception:
                patches = []

        by_status: Dict[str, int] = {}
        for p in patches:
            status = str((p or {}).get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1

        reports = []
        if reports_dir.exists() and reports_dir.is_dir():
            for path in sorted(reports_dir.glob("*.json"))[-200:]:
                try:
                    reports.append(json.loads(path.read_text(encoding="utf-8")))
                except Exception:
                    continue

        return {
            "patches": len(patches),
            "by_status": by_status,
            "reports": len(reports),
            "source": {"patch_store": str(store_path), "patch_reports": str(reports_dir)},
        }

    # --------------------------------------------------------------------- Release protocol (shadow/canary)
    def _release_metrics(self) -> Dict[str, Any]:
        """
        Summarize variant lifecycle records (shared by experiments and patches).
        This is intentionally schema-stable; values may be empty if the file doesn't exist.
        """
        try:
            from quentin.l3.research.release_protocol import FileBackedVariantLifecycleStore, summarize_lifecycle

            store = FileBackedVariantLifecycleStore(repo_root=self.repo_root)
            return {
                "all": summarize_lifecycle(store=store, prefix=""),
                "patches": summarize_lifecycle(store=store, prefix="patch:"),
                "experiments": summarize_lifecycle(store=store, prefix="exp:"),
            }
        except Exception:
            return {
                "all": {"total": 0, "by_status": {}, "by_environment": {}, "by_prefix": {}, "source": str(self.repo_root / "data" / "research" / "variant_lifecycle.json")},
                "patches": {"total": 0, "by_status": {}, "by_environment": {}, "by_prefix": {}, "source": str(self.repo_root / "data" / "research" / "variant_lifecycle.json")},
                "experiments": {"total": 0, "by_status": {}, "by_environment": {}, "by_prefix": {}, "source": str(self.repo_root / "data" / "research" / "variant_lifecycle.json")},
            }

    # --------------------------------------------------------------------- Experiments
    async def _experiment_metrics(self) -> Dict[str, Any]:
        try:
            from quentin.infra.storage.kv_store import KVStore

            kv = getattr(self.runtime, "kv_store", None) or KVStore()
            keys = await kv.list_keys(prefix="exp:record:")
            return {"experiments": len(keys), "source": "kv_store(exp:record:*)"}
        except Exception:
            return {"experiments": 0, "source": "kv_store_error"}

    # --------------------------------------------------------------------- Intelligence (planner/council/guard feedback)
    def _intelligence_metrics(self) -> Dict[str, Any]:
        events_path = self.repo_root / "data" / "traces" / "events.jsonl"
        audit_path = self.repo_root / "data" / "audit_events.jsonl"
        guardrail_state_path = self.repo_root / "data" / "runtime" / "brain_guardrail_state.json"
        queue_path = _resolve_task_queue_path(repo_root=self.repo_root)
        events = _read_jsonl(events_path, limit=50000)
        audits = _read_jsonl(audit_path, limit=50000)
        queue_rows = _read_jsonl(queue_path, limit=20000)
        vision_feedback = {"total_rows": 0, "avg_outcome_score": 0.0, "by_task_class": [], "source": ""}
        try:
            from quentin.cognitive.vision_budget import summarize_vision_budget_feedback

            vision_feedback = summarize_vision_budget_feedback(limit=1200)
        except Exception:
            pass

        planning_events = [
            e for e in events if str(e.get("event_type") or "").strip().lower() == "planning"
        ]
        total_plans = len(planning_events)
        plans_with_repairs = 0
        risky_plans = 0
        risky_plans_with_discovery = 0
        repair_reason_counts: Dict[str, int] = {}
        variant_counts: Dict[str, int] = {}
        tool_family_counts: Dict[str, int] = {}
        error_subcategory_counts: Dict[str, int] = {}
        strategy_patch_counts: Dict[str, int] = {}
        for e in planning_events:
            payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            repairs = payload.get("planner_repairs")
            if isinstance(repairs, list) and repairs:
                plans_with_repairs += 1
                for r in repairs:
                    key = str(r or "unknown")
                    repair_reason_counts[key] = repair_reason_counts.get(key, 0) + 1
            dg = payload.get("discovery_guard") if isinstance(payload.get("discovery_guard"), dict) else {}
            risky_steps = int(dg.get("risky_steps") or 0)
            if risky_steps > 0:
                risky_plans += 1
                if bool(dg.get("discovery_before_risky")):
                    risky_plans_with_discovery += 1
            ctxi = payload.get("context_injected") if isinstance(payload.get("context_injected"), dict) else {}
            pd = ctxi.get("planning_diagnostics") if isinstance(ctxi.get("planning_diagnostics"), dict) else {}
            variant_id = str(pd.get("payload_variant_id") or "").strip()
            if variant_id:
                variant_counts[variant_id] = variant_counts.get(variant_id, 0) + 1
            tool_family = str(pd.get("payload_tool_family") or "").strip().lower()
            if tool_family:
                tool_family_counts[tool_family] = tool_family_counts.get(tool_family, 0) + 1
            error_sub = str(pd.get("error_subcategory") or "").strip().lower()
            if error_sub:
                error_subcategory_counts[error_sub] = error_subcategory_counts.get(error_sub, 0) + 1
            spid = str(pd.get("strategy_patch_id") or "").strip()
            if spid:
                strategy_patch_counts[spid] = strategy_patch_counts.get(spid, 0) + 1

        blocked_action_counts: Dict[str, int] = {}
        blocked_total = 0
        blocked_repeated_total = 0
        known_actions = ("nano", "vim", "vi", "emacs", "wget", "curl", "man", "less", "more")
        import re
        p_interactive = re.compile(r"interactive command ['\"]?([a-zA-Z0-9._/-]+)['\"]?")
        for row in audits:
            if str(row.get("event_type") or "") != "tool_call":
                continue
            phase = str(row.get("phase") or "").strip().lower()
            if phase not in {"denied", "error"}:
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            txt = (
                f"{payload.get('reason', '')} {payload.get('error', '')} "
                f"{payload.get('command_head', '')} {json.dumps(payload, ensure_ascii=False)}"
            ).lower()
            action = ""
            m = p_interactive.search(txt)
            if m:
                action = str(m.group(1) or "").lower()
            if not action:
                for k in known_actions:
                    if re.search(rf"(^|[^a-z0-9_]){re.escape(k)}([^a-z0-9_]|$)", txt):
                        action = k
                        break
            if not action:
                continue
            blocked_total += 1
            blocked_action_counts[action] = blocked_action_counts.get(action, 0) + 1

        for c in blocked_action_counts.values():
            if c > 1:
                blocked_repeated_total += c
        top_blocked = sorted(
            [{"action": k, "count": v} for k, v in blocked_action_counts.items()],
            key=lambda x: (-int(x.get("count") or 0), str(x.get("action") or "")),
        )[:10]

        done_quality_rows = [
            r for r in audits if str(r.get("event_type") or "") == "done_council_quality"
        ]
        done_quality_counts: Dict[str, int] = {}
        for r in done_quality_rows:
            ph = str(r.get("phase") or "unknown")
            done_quality_counts[ph] = done_quality_counts.get(ph, 0) + 1
        weak = int(done_quality_counts.get("weak_reasoning_detected", 0))
        retry_ok = int(done_quality_counts.get("retry_improved", 0))
        fallback = int(done_quality_counts.get("fallback_reason_applied", 0))
        weak_resolution_rate = (float(retry_ok) / float(weak)) if weak else None

        recovery_loop: Dict[str, Any] = {
            "success_rate": 0.0,
            "sample_size": 0,
            "outcomes_tail": [],
            "recent_window_rate": None,
            "prior_window_rate": None,
            "trend_delta": None,
            "trend_window_size": 0,
            "focus_breakdown": [],
            "source": str(guardrail_state_path),
            "queue_source": str(queue_path),
        }
        if guardrail_state_path.exists():
            try:
                raw = json.loads(guardrail_state_path.read_text(encoding="utf-8") or "{}")
                outcomes = raw.get("intelligence_recovery_outcomes")
                if isinstance(outcomes, list):
                    vals = [bool(x) for x in outcomes][-24:]
                    recovery_loop["sample_size"] = len(vals)
                    recovery_loop["outcomes_tail"] = vals[-10:]
                    recovery_loop["success_rate"] = (
                        float(sum(1 for v in vals if v)) / float(len(vals))
                        if vals
                        else 0.0
                    )
                    # Two-window trend: compare the latest window against the previous window.
                    if len(vals) >= 4:
                        w = min(5, len(vals) // 2)
                        if w >= 2:
                            prior = vals[-(2 * w):-w]
                            recent = vals[-w:]
                            prior_rate = float(sum(1 for v in prior if v)) / float(w)
                            recent_rate = float(sum(1 for v in recent if v)) / float(w)
                            recovery_loop["trend_window_size"] = int(w)
                            recovery_loop["prior_window_rate"] = float(prior_rate)
                            recovery_loop["recent_window_rate"] = float(recent_rate)
                            recovery_loop["trend_delta"] = float(recent_rate - prior_rate)
            except Exception:
                pass
        focus_stats: Dict[str, Dict[str, Any]] = {}
        for row in queue_rows:
            md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            if str(md.get("kind") or "") != "intelligence_regression_recovery":
                continue
            focus = str(md.get("recovery_focus") or "general_regression").strip() or "general_regression"
            status = str(row.get("status") or "").strip().lower()
            bucket = focus_stats.setdefault(
                focus,
                {"focus": focus, "total": 0, "done": 0, "failed": 0, "success_rate": None},
            )
            bucket["total"] += 1
            if status == "done":
                bucket["done"] += 1
            elif status == "failed":
                bucket["failed"] += 1
        focus_rows: List[Dict[str, Any]] = []
        for b in focus_stats.values():
            settled = int(b.get("done") or 0) + int(b.get("failed") or 0)
            b["success_rate"] = (float(b.get("done") or 0) / float(settled)) if settled > 0 else None
            focus_rows.append(b)
        focus_rows.sort(key=lambda x: (-int(x.get("total") or 0), str(x.get("focus") or "")))
        recovery_loop["focus_breakdown"] = focus_rows[:10]

        return {
            "planner_repairs": {
                "total_plans": total_plans,
                "plans_with_repairs": plans_with_repairs,
                "repair_rate": (float(plans_with_repairs) / float(total_plans)) if total_plans else 0.0,
                "repair_reason_counts": repair_reason_counts,
                "discovery_precheck": {
                    "risky_plans": risky_plans,
                    "compliant_plans": risky_plans_with_discovery,
                    "compliance_rate": (
                        float(risky_plans_with_discovery) / float(risky_plans)
                        if risky_plans
                        else 1.0
                    ),
                },
            },
            "planning_diagnostics": {
                "payload_variant_counts": variant_counts,
                "payload_tool_family_counts": tool_family_counts,
                "error_subcategory_counts": error_subcategory_counts,
                "strategy_patch_counts": strategy_patch_counts,
            },
            "blocked_action_recurrence": {
                "blocked_total": blocked_total,
                "blocked_repeated_total": blocked_repeated_total,
                "repeat_ratio": (float(blocked_repeated_total) / float(blocked_total)) if blocked_total else 0.0,
                "top_actions": top_blocked,
            },
            "done_council_quality": {
                "weak_reasoning_detected": weak,
                "retry_improved": retry_ok,
                "fallback_reason_applied": fallback,
                "weak_resolution_rate": weak_resolution_rate,
            },
            "recovery_loop": recovery_loop,
            "vision_budget_feedback": vision_feedback,
            "sources": [str(events_path), str(audit_path), str(guardrail_state_path), str(queue_path)],
        }
