"""
Observability Dashboard

Provides metrics and health checks for the AI Brain system.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryTier


@dataclass
class DashboardMetrics:
    """System-wide metrics."""

    # Sleep Loop
    sleep_loop_success_count: int = 0
    sleep_loop_failure_count: int = 0
    sleep_loop_success_rate: float = 0.0

    # Memory
    daily_summary_count: int = 0
    plan_vs_outcome_count: int = 0
    memory_sts_count: int = 0
    memory_mts_count: int = 0
    memory_lts_count: int = 0
    vector_store_size_mb: float = 0.0
    vector_recall_hit_rate: float = 0.0

    # Tool Calls
    tool_call_success_count: int = 0
    tool_call_failure_count: int = 0
    tool_call_success_rate: float = 0.0

    # Communication
    listener_count: int = 0
    listener_restart_total: int = 0
    listener_dropped_total: int = 0
    listener_dead_letter_total: int = 0
    canvas_ack_pending_count: int = 0

    # Auto-Evolution
    auto_evolution_success_count: int = 0
    auto_evolution_failure_count: int = 0
    auto_evolution_avg_profit_impact: float = 0.0

    # Strategy Council
    council_proposal_count: int = 0
    council_adoption_rate: float = 0.0
    hedge_var_reduction_avg: float = 0.0

    # Experiments & Evaluation
    experiment_count: int = 0
    experiment_runs_total: int = 0
    experiment_runs_completed: int = 0
    experiment_avg_success_rate: float = 0.0
    evaluation_cases_total: int = 0
    evaluation_avg_latency_ms: float = 0.0

    # Health
    vector_store_available: bool = True
    memory_fabric_healthy: bool = True
    eval_harness_healthy: bool = True
    last_updated: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ObservabilityDashboard:
    """Main dashboard for system observability."""

    def __init__(self, memory_fabric: Optional[MemoryFabric] = None, repo_root: str | Path = "."):
        self.memory_fabric = memory_fabric or MemoryFabric()
        self.repo_root = Path(repo_root).resolve()

    def collect_metrics(self) -> DashboardMetrics:
        """Collect all system metrics."""
        metrics = DashboardMetrics()

        # Memory metrics
        try:
            sts_count = len(list(self.memory_fabric.store.search(MemoryQuery(tier=MemoryTier.STS, top_k=10000))))
            mts_count = len(list(self.memory_fabric.store.search(MemoryQuery(tier=MemoryTier.MTS, top_k=10000))))
            lts_count = len(list(self.memory_fabric.store.search(MemoryQuery(tier=MemoryTier.LTS, top_k=10000))))

            metrics.memory_sts_count = sts_count
            metrics.memory_mts_count = mts_count
            metrics.memory_lts_count = lts_count
            metrics.memory_fabric_healthy = True
        except Exception:
            metrics.memory_fabric_healthy = False

        # Sleep loop metrics
        try:
            sleep_metrics = self._collect_sleep_loop_metrics()
            metrics.sleep_loop_success_count = sleep_metrics.get("success_count", 0)
            metrics.sleep_loop_failure_count = sleep_metrics.get("failure_count", 0)
            total = metrics.sleep_loop_success_count + metrics.sleep_loop_failure_count
            if total > 0:
                metrics.sleep_loop_success_rate = metrics.sleep_loop_success_count / total
        except Exception:
            pass

        # Tool call metrics
        try:
            tool_metrics = self._collect_tool_call_metrics()
            metrics.tool_call_success_count = tool_metrics.get("success_count", 0)
            metrics.tool_call_failure_count = tool_metrics.get("failure_count", 0)
            total = metrics.tool_call_success_count + metrics.tool_call_failure_count
            if total > 0:
                metrics.tool_call_success_rate = metrics.tool_call_success_count / total
        except Exception:
            pass

        # Communication metrics
        try:
            comm = self._collect_communication_metrics()
            metrics.listener_count = int(comm.get("listener_count") or 0)
            metrics.listener_restart_total = int(comm.get("listener_restart_total") or 0)
            metrics.listener_dropped_total = int(comm.get("listener_dropped_total") or 0)
            metrics.listener_dead_letter_total = int(comm.get("listener_dead_letter_total") or 0)
            metrics.canvas_ack_pending_count = int(comm.get("canvas_ack_pending_count") or 0)
        except Exception:
            pass

        # Plan vs outcome metrics
        try:
            plan_outcomes = self._load_plan_outcomes()
            metrics.plan_vs_outcome_count = len(plan_outcomes)
        except Exception:
            pass

        # Strategy council metrics
        try:
            council_metrics = self._collect_council_metrics()
            metrics.council_proposal_count = council_metrics.get("proposal_count", 0)
            metrics.council_adoption_rate = council_metrics.get("adoption_rate", 0.0)
            metrics.hedge_var_reduction_avg = council_metrics.get("hedge_var_reduction_avg", 0.0)
        except Exception:
            pass

        # Experiment & evaluation metrics
        try:
            exp_metrics = self._collect_experiment_metrics()
            metrics.experiment_count = exp_metrics.get("experiment_count", 0)
            metrics.experiment_runs_total = exp_metrics.get("runs_total", 0)
            metrics.experiment_runs_completed = exp_metrics.get("runs_completed", 0)
            metrics.experiment_avg_success_rate = exp_metrics.get("avg_success_rate", 0.0)
            metrics.evaluation_cases_total = exp_metrics.get("cases_total", 0)
            metrics.evaluation_avg_latency_ms = exp_metrics.get("avg_latency_ms", 0.0)
            metrics.eval_harness_healthy = True
        except Exception:
            metrics.eval_harness_healthy = False

        metrics.last_updated = datetime.now(timezone.utc).isoformat()
        return metrics

    def _collect_sleep_loop_metrics(self) -> Dict[str, Any]:
        """Collect sleep loop specific metrics."""
        events_path = self.repo_root / "data" / "traces" / "events.jsonl"
        if not events_path.exists():
            return {"success_count": 0, "failure_count": 0}

        success = 0
        failure = 0
        try:
            with events_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except Exception:
                        continue
                    if evt.get("event_type") == "sleep":
                        success += 1
                    if evt.get("event_type") == "error":
                        payload = evt.get("payload") or {}
                        if isinstance(payload, dict) and "SleepLoop" in str(payload.get("error") or ""):
                            failure += 1
        except Exception:
            return {"success_count": 0, "failure_count": 0}
        return {"success_count": success, "failure_count": failure}

    def _collect_tool_call_metrics(self) -> Dict[str, Any]:
        events_path = self.repo_root / "data" / "traces" / "events.jsonl"
        if not events_path.exists():
            return {"success_count": 0, "failure_count": 0}

        success = 0
        failure = 0
        try:
            with events_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except Exception:
                        continue
                    if evt.get("event_type") != "tool_call":
                        continue
                    payload = evt.get("payload") or {}
                    phase = str(payload.get("phase") or "")
                    if phase == "success":
                        success += 1
                    elif phase in ("error", "aborted", "denied"):
                        failure += 1
        except Exception:
            return {"success_count": 0, "failure_count": 0}
        return {"success_count": success, "failure_count": failure}

    def _load_plan_outcomes(self) -> List[Dict[str, Any]]:
        """Load recent plan vs outcome records."""
        path = self.repo_root / "runs" / "memory" / "plan_vs_outcome.jsonl"
        if not path.exists():
            return []

        outcomes = []
        try:
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            outcomes.append(json.loads(line))
                        except Exception:
                            continue
        except Exception:
            pass

        return outcomes

    def _collect_council_metrics(self) -> Dict[str, Any]:
        """Collect strategy council metrics."""
        outcomes = self._load_plan_outcomes()

        if not outcomes:
            return {
                "proposal_count": 0,
                "adoption_rate": 0.0,
                "hedge_var_reduction_avg": 0.0,
            }

        # Calculate metrics from plan outcomes
        hedge_reductions = []
        for o in outcomes:
            hedge_effect = o.get("hedge_effect", {})
            var_red = hedge_effect.get("var_reduction")
            if var_red is not None:
                hedge_reductions.append(var_red)

        avg_hedge = sum(hedge_reductions) / len(hedge_reductions) if hedge_reductions else 0.0

        return {
            "proposal_count": len(outcomes),
            "adoption_rate": 1.0 if outcomes else 0.0,  # Simplified
            "hedge_var_reduction_avg": avg_hedge,
        }

    def _collect_experiment_metrics(self) -> Dict[str, Any]:
        """Collect experiment and evaluation metrics."""
        # Load experiment results from JSONL
        eval_results_path = self.repo_root / "data" / "research" / "eval_results.jsonl"

        if not eval_results_path.exists():
            return {
                "experiment_count": 0,
                "runs_total": 0,
                "runs_completed": 0,
                "avg_success_rate": 0.0,
                "cases_total": 0,
                "avg_latency_ms": 0.0,
            }

        # Parse results
        experiments = set()
        runs = []
        all_cases = []
        success_rates = []
        latencies = []

        try:
            with open(eval_results_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        result = json.loads(line)
                        exp_id = result.get("experiment_id")
                        if exp_id:
                            experiments.add(exp_id)

                        run_id = result.get("run_id")
                        if run_id:
                            runs.append(result)

                        case_results = result.get("case_results", [])
                        all_cases.extend(case_results)

                        for case in case_results:
                            success = case.get("success", 0.0)
                            success_rates.append(success)

                            latency = case.get("latency_ms", 0.0)
                            if latency > 0:
                                latencies.append(latency)

                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        avg_success = sum(success_rates) / len(success_rates) if success_rates else 0.0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        return {
            "experiment_count": len(experiments),
            "runs_total": len(runs),
            "runs_completed": len(runs),  # Simplified - all in file are completed
            "avg_success_rate": avg_success,
            "cases_total": len(all_cases),
            "avg_latency_ms": avg_latency,
        }

    def _collect_communication_metrics(self) -> Dict[str, Any]:
        listener_count = 0
        listener_restart_total = 0
        listener_dropped_total = 0
        try:
            from quentin.infra.channels.listener_manager import listener_manager

            st = listener_manager.status()
        except Exception:
            st = {"status": "error", "listeners": [], "count": 0}
        for li in list(st.get("listeners") or []):
            if not isinstance(li, dict):
                continue
            listener_count += 1
            listener_restart_total += int(li.get("restart_count") or 0)
            listener_dropped_total += int(li.get("dropped_count") or 0)

        listener_dead_letter_total = 0
        ls = self.repo_root / "data" / "channels" / "listener_state.json"
        if ls.exists():
            try:
                raw = json.loads(ls.read_text(encoding="utf-8"))
                listener_dead_letter_total = len(list((raw or {}).get("dead_letters") or []))
            except Exception:
                listener_dead_letter_total = 0

        canvas_ack_pending_count = 0
        canvas_file = self.repo_root / "data" / "canvas_components.json"
        if canvas_file.exists():
            try:
                raw = json.loads(canvas_file.read_text(encoding="utf-8"))
            except Exception:
                raw = {}
            comps = (raw or {}).get("components") if isinstance(raw, dict) else {}
            if isinstance(comps, dict):
                now_ts = datetime.now(timezone.utc).timestamp()
                timeout_sec = 120
                for _, node in comps.items():
                    if not isinstance(node, dict):
                        continue
                    stt = str(node.get("status") or "active").strip().lower()
                    if stt not in {"active", "pending", "running"}:
                        continue
                    last_ack = node.get("last_ack") if isinstance(node.get("last_ack"), dict) else {}
                    last_ack_ts = float((last_ack or {}).get("ts") or 0.0)
                    updated_at = float(node.get("updated_at") or 0.0)
                    ref_ts = max(last_ack_ts, updated_at)
                    if ref_ts <= 0.0 or (now_ts - ref_ts) >= float(timeout_sec):
                        canvas_ack_pending_count += 1

        return {
            "listener_count": listener_count,
            "listener_restart_total": listener_restart_total,
            "listener_dropped_total": listener_dropped_total,
            "listener_dead_letter_total": listener_dead_letter_total,
            "canvas_ack_pending_count": canvas_ack_pending_count,
        }

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on all subsystems."""
        health = {
            "status": "healthy",
            "checks": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Memory fabric check
        try:
            self.memory_fabric.store.search(MemoryQuery(text="health_check", top_k=1))
            health["checks"]["memory_fabric"] = {"status": "ok", "message": "Memory fabric operational"}
        except Exception as e:
            health["checks"]["memory_fabric"] = {"status": "error", "message": str(e)}
            health["status"] = "degraded"

        # Vector store check
        try:
            # Check if we can perform vector queries
            test_vector = [0.1] * 128  # Dummy vector
            self.memory_fabric.store.search(MemoryQuery(vector=test_vector, top_k=1))
            health["checks"]["vector_store"] = {"status": "ok", "message": "Vector store operational"}
        except Exception as e:
            health["checks"]["vector_store"] = {"status": "warning", "message": f"Vector queries unavailable: {e}"}

        return health

    def get_summary(self) -> str:
        """Get a human-readable summary."""
        metrics = self.collect_metrics()
        health = self.health_check()

        summary = f"""
=== OBSERVABILITY DASHBOARD ===
Last Updated: {metrics.last_updated}

Memory:
  STS: {metrics.memory_sts_count}
  MTS: {metrics.memory_mts_count}
  LTS: {metrics.memory_lts_count}
  Plan vs Outcome: {metrics.plan_vs_outcome_count}

Sleep Loop:
  Success: {metrics.sleep_loop_success_count}
  Failure: {metrics.sleep_loop_failure_count}
  Success Rate: {metrics.sleep_loop_success_rate:.1%}

Communication:
  Listeners: {metrics.listener_count}
  Listener Restarts: {metrics.listener_restart_total}
  Listener Drops: {metrics.listener_dropped_total}
  Dead Letters: {metrics.listener_dead_letter_total}
  Canvas ACK Pending: {metrics.canvas_ack_pending_count}

Strategy Council:
  Proposals: {metrics.council_proposal_count}
  Adoption Rate: {metrics.council_adoption_rate:.1%}
  Avg Hedge Var Reduction: {metrics.hedge_var_reduction_avg:.2%}

Experiments & Evaluation:
  Experiments: {metrics.experiment_count}
  Runs: {metrics.experiment_runs_completed}/{metrics.experiment_runs_total}
  Avg Success Rate: {metrics.experiment_avg_success_rate:.1%}
  Evaluation Cases: {metrics.evaluation_cases_total}
  Avg Latency: {metrics.evaluation_avg_latency_ms:.1f}ms

Health: {health['status'].upper()}
"""
        for check_name, check in health['checks'].items():
            summary += f"  {check_name}: {check['status']}\n"

        return summary


def main():
    """CLI for observability dashboard."""
    import argparse

    parser = argparse.ArgumentParser(description="Observability Dashboard")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--health", action="store_true", help="Health check only")

    args = parser.parse_args()

    dashboard = ObservabilityDashboard()

    if args.health:
        health = dashboard.health_check()
        if args.json:
            print(json.dumps(health, indent=2))
        else:
            print(f"\nHealth Status: {health['status'].upper()}")
            for name, check in health['checks'].items():
                status_icon = "✓" if check['status'] == 'ok' else "⚠"  if check['status'] == 'warning' else "✗"
                print(f"  {status_icon} {name}: {check['message']}")
            print()
    else:
        metrics = dashboard.collect_metrics()
        if args.json:
            print(json.dumps(metrics.to_dict(), indent=2))
        else:
            print(dashboard.get_summary())


if __name__ == "__main__":
    main()
