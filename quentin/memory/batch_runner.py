from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Optional

from quentin.kernel.audit import AuditEvent, default_audit_logger
from quentin.llm.context_budget import estimate_tokens
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryTier
from quentin.memory.policies import MemoryPolicyEngine
from quentin.utils.time import now_utc


@dataclass
class MemoryBatchConfig:
    """
    Budgeted batch runner for continual memory automation.

    This intentionally lives outside SleepLoop so it can be invoked independently
    (manual/cron/research), and so promotion/decay can be A/B tested.
    """

    enabled: bool = True
    batch_name: str = "nightly"  # nightly | weekly | manual
    max_records: int = 200
    max_duration_ms: int = 60_000
    max_tokens_est: int = 200_000
    enable_consolidation: bool = True


@dataclass
class MemoryBatchReport:
    batch_id: str
    batch_name: str
    started_at: str
    duration_ms: int = 0
    tokens_est: int = 0
    promoted: int = 0
    decayed: int = 0
    consolidated: int = 0
    stopped_reason: str = ""
    errors: int = 0
    error_messages: list[str] = None  # type: ignore[assignment]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _policy_name(policy: Any, key: str, default: str) -> str:
    if not policy:
        return default
    value = getattr(policy, key, None)
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for name_key in ("name", "rule", "id"):
            name = value.get(name_key)
            if name:
                return str(name)
    return default


class MemoryConsolidationBatchRunner:
    """
    Unified continual-memory batch runner:
    - optional consolidation (SleepLoop)
    - promotion (STS->MTS, MTS->LTS)
    - decay/forgetting (STS/MTS TTL)
    """

    def __init__(
        self,
        *,
        fabric: MemoryFabric,
        policy_engine: Optional[MemoryPolicyEngine] = None,
        config: Optional[MemoryBatchConfig] = None,
        sleep_loop: Optional[Any] = None,
    ) -> None:
        self.fabric = fabric
        self.policy_engine = policy_engine or MemoryPolicyEngine()
        self.config = config or MemoryBatchConfig()
        self.sleep_loop = sleep_loop

    def run_once(self) -> MemoryBatchReport:
        batch_id = f"mem_batch::{uuid.uuid4().hex}"
        started = time.perf_counter()
        report = MemoryBatchReport(
            batch_id=batch_id,
            batch_name=str(self.config.batch_name or "nightly"),
            started_at=now_utc().isoformat(),
            error_messages=[],
        )

        if not self.config.enabled:
            report.stopped_reason = "disabled"
            return report

        try:
            if self.config.enable_consolidation:
                report.consolidated += self._run_consolidation_best_effort(batch_id=batch_id)
        except Exception as e:
            report.errors += 1
            report.error_messages.append(f"consolidation:{e!r}")

        # Promotion + decay are always safe to run; they operate on existing records.
        try:
            report.promoted += self._run_promotion(batch_id=batch_id, report=report)
        except Exception as e:
            report.errors += 1
            report.error_messages.append(f"promotion:{e!r}")

        try:
            report.decayed += self._run_decay(batch_id=batch_id, report=report)
        except Exception as e:
            report.errors += 1
            report.error_messages.append(f"decay:{e!r}")

        report.duration_ms = int((time.perf_counter() - started) * 1000)
        self._trace_and_audit(batch_id=batch_id, report=report)
        return report

    def _should_stop(self, report: MemoryBatchReport, started: float) -> Optional[str]:
        if self.config.max_duration_ms and int((time.perf_counter() - started) * 1000) > int(self.config.max_duration_ms):
            return "max_duration_ms"
        if self.config.max_tokens_est and report.tokens_est > int(self.config.max_tokens_est):
            return "max_tokens_est"
        promoted_decayed = report.promoted + report.decayed
        if self.config.max_records and promoted_decayed >= int(self.config.max_records):
            return "max_records"
        return None

    def _run_consolidation_best_effort(self, *, batch_id: str) -> int:
        """
        Run SleepLoop once (best-effort). This is intentionally optional because:
        - it may require LLM access
        - it is async
        - some environments may want promotion/decay only
        """
        sleep_loop = self.sleep_loop
        if sleep_loop is None:
            try:
                from quentin.sleep.loop_impl import SleepLoop

                sleep_loop = SleepLoop(memory_fabric=self.fabric, trace_recorder=self.fabric.trace_recorder)
            except Exception:
                sleep_loop = None

        if sleep_loop is None or not hasattr(sleep_loop, "run_once"):
            return 0

        try:
            asyncio.get_running_loop()
            # Caller is in an event loop; avoid nested loops in sync API.
            return 0
        except RuntimeError:
            pass

        result = asyncio.run(sleep_loop.run_once())
        if hasattr(result, "to_dict"):
            payload = result.to_dict()
        elif isinstance(result, dict):
            payload = result
        else:
            payload = {"result": str(result)}
        try:
            # SleepLoop already records its own trace; this is a correlation marker.
            self.fabric._record_trace("memory_batch_consolidation", {"batch_id": batch_id, **payload})  # type: ignore[attr-defined]
        except Exception:
            pass
        return int(payload.get("consolidated_traces") or 0)

    def _run_promotion(self, *, batch_id: str, report: MemoryBatchReport) -> int:
        started = time.perf_counter()
        promoted = 0

        # Prefer recently accessed/promising records; store decides ordering.
        candidates = []
        candidates.extend(self.fabric.get_records_for_processing(tier=MemoryTier.STS, limit=max(50, int(self.config.max_records))))
        candidates.extend(self.fabric.get_records_for_processing(tier=MemoryTier.MTS, limit=max(50, int(self.config.max_records))))

        now = now_utc()
        for rec in candidates:
            stop = self._should_stop(report, started)
            if stop:
                report.stopped_reason = stop
                break

            try:
                report.tokens_est += int(estimate_tokens(rec.content or ""))
            except Exception:
                pass

            to_tier = self.policy_engine.decide_promotion(rec, now=now)
            if not to_tier or to_tier == rec.tier:
                continue

            old_tier = rec.tier
            try:
                self.fabric.store.promote(rec.id, to_tier)
                rec.tier = to_tier
                rec.updated_at = now
                entry = {
                    "ts": now.isoformat(),
                    "action": "promote",
                    "from": getattr(old_tier, "value", str(old_tier)),
                    "to": getattr(to_tier, "value", str(to_tier)),
                    "promotion_rule": _policy_name(rec.update_policy, "promotion_rule", default="default_promotion_v1"),
                    "batch": self.config.batch_name,
                    "batch_id": batch_id,
                }
                rec.update_history.append(entry)
                rec.metadata.setdefault("update_history", [])
                if isinstance(rec.metadata.get("update_history"), list):
                    rec.metadata["update_history"].append(entry)
                try:
                    self.fabric.store.update(rec)
                except Exception:
                    # Some stores may not persist update_history; metadata should still carry it.
                    pass
                promoted += 1
                # Mutate report in-loop so budgets (max_records) can stop promptly.
                report.promoted = promoted
            except Exception:
                report.errors += 1

        return promoted

    def _run_decay(self, *, batch_id: str, report: MemoryBatchReport) -> int:
        started = time.perf_counter()
        decayed = 0
        candidates = []
        candidates.extend(self.fabric.get_records_for_processing(tier=MemoryTier.STS, limit=max(50, int(self.config.max_records))))
        candidates.extend(self.fabric.get_records_for_processing(tier=MemoryTier.MTS, limit=max(50, int(self.config.max_records))))

        now = now_utc()
        for rec in candidates:
            stop = self._should_stop(report, started)
            if stop:
                report.stopped_reason = stop
                break

            try:
                report.tokens_est += int(estimate_tokens(rec.content or ""))
            except Exception:
                pass

            should = self.policy_engine.should_decay(rec, now=now)
            if not should:
                continue

            try:
                self.fabric.store.mark_decayed(rec.id)
                entry = {
                    "ts": now.isoformat(),
                    "action": "decay",
                    "tier": getattr(rec.tier, "value", str(rec.tier)),
                    "decay_rule": _policy_name(rec.update_policy, "decay_rule", default="default_decay_v1"),
                    "batch": self.config.batch_name,
                    "batch_id": batch_id,
                }
                rec.update_history.append(entry)
                rec.metadata.setdefault("update_history", [])
                if isinstance(rec.metadata.get("update_history"), list):
                    rec.metadata["update_history"].append(entry)
                try:
                    self.fabric.store.update(rec)
                except Exception:
                    pass
                decayed += 1
                report.decayed = decayed
            except Exception:
                report.errors += 1

        return decayed

    def _trace_and_audit(self, *, batch_id: str, report: MemoryBatchReport) -> None:
        payload = report.to_dict()
        try:
            self.fabric._record_trace("memory_batch", payload)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            default_audit_logger().append(
                AuditEvent(
                    action_id=batch_id,
                    event_type="memory_batch",
                    phase="finished",
                    actor="memory_batch_runner",
                    payload=payload,
                )
            )
        except Exception:
            pass
