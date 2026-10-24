import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from quentin.observability.service import ObservabilityService
from quentin.runtime.task_queue import TaskQueue, TaskQueueItem

logger = logging.getLogger(__name__)


@dataclass
class Anomaly:
    kind: str
    severity: str
    message: str
    details: Dict[str, Any] | None = None


class AnomalyDetector:
    """
    Lightweight anomaly detector for observability overview snapshots.

    Kept intentionally dependency-free so it can run in unit tests and be used
    by higher-level monitoring components.
    """

    def __init__(
        self,
        *,
        llm_error_rate_threshold: float = 0.3,
        memory_latency_ms_threshold: float = 30_000.0,
        patchflow_blocked_ratio_threshold: float = 0.5,
        denial_rate_threshold: float = 0.3,
        task_success_rate_min: float = 0.5,
        lease_expiring_count_threshold: int = 3,
        lease_contention_events_threshold: int = 4,
        lease_fencing_conflicts_threshold: int = 2,
        dead_letter_growth_ratio_threshold: float = 2.0,
        dead_letter_recent_min: int = 5,
    ) -> None:
        self.llm_error_rate_threshold = float(llm_error_rate_threshold)
        self.memory_latency_ms_threshold = float(memory_latency_ms_threshold)
        self.patchflow_blocked_ratio_threshold = float(patchflow_blocked_ratio_threshold)
        self.denial_rate_threshold = float(denial_rate_threshold)
        self.task_success_rate_min = float(task_success_rate_min)
        self.lease_expiring_count_threshold = int(lease_expiring_count_threshold)
        self.lease_contention_events_threshold = int(lease_contention_events_threshold)
        self.lease_fencing_conflicts_threshold = int(lease_fencing_conflicts_threshold)
        self.dead_letter_growth_ratio_threshold = float(dead_letter_growth_ratio_threshold)
        self.dead_letter_recent_min = int(dead_letter_recent_min)

    def detect(self, overview: Dict[str, Any]) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        overview = overview or {}

        # 1) Task failure spike: domain success rate dipped.
        by_domain_env = (
            (overview.get("domain") or {}).get("task") or {}
        ).get("by_domain_env") or []
        for row in by_domain_env if isinstance(by_domain_env, list) else []:
            try:
                tasks = int(row.get("tasks") or 0)
                success_rate = float(row.get("success_rate", 1.0))
            except Exception:
                continue
            if tasks >= 3 and success_rate <= self.task_success_rate_min:
                anomalies.append(
                    Anomaly(
                        kind="task_failure_spike",
                        severity="high",
                        message=f"Task success rate dropped to {success_rate:.1%}.",
                        details={"row": row},
                    )
                )

        # 2) Policy denial spike: allow_rate dipped on llm_call actions.
        by_domain_env_action = (
            (overview.get("domain") or {}).get("actions") or {}
        ).get("by_domain_env_action") or []
        for row in by_domain_env_action if isinstance(by_domain_env_action, list) else []:
            if str(row.get("action_type") or "") != "llm_call":
                continue
            try:
                requests = int(row.get("requests") or 0)
                allow_rate = float(row.get("allow_rate", 1.0))
            except Exception:
                continue
            if requests >= 5 and (1.0 - allow_rate) > self.denial_rate_threshold:
                anomalies.append(
                    Anomaly(
                        kind="policy_denial_spike",
                        severity="medium",
                        message=f"Policy denial rate rose to {(1.0 - allow_rate):.1%}.",
                        details={"row": row},
                    )
                )

        # 3) Memory latency spike.
        recall = ((overview.get("memory") or {}).get("events") or {}).get("recall") or {}
        try:
            avg_latency_ms = float(recall.get("avg_latency_ms") or 0.0)
        except Exception:
            avg_latency_ms = 0.0
        if avg_latency_ms and avg_latency_ms > self.memory_latency_ms_threshold:
            anomalies.append(
                Anomaly(
                    kind="memory_latency_spike",
                    severity="medium",
                    message=f"Memory recall latency is high ({avg_latency_ms:.0f} ms).",
                    details={"avg_latency_ms": avg_latency_ms, "threshold_ms": self.memory_latency_ms_threshold},
                )
            )

        # 4) Patchflow degraded: too many blocked patches.
        by_status = (overview.get("patches") or {}).get("by_status") or {}
        if isinstance(by_status, dict):
            blocked = int(by_status.get("blocked") or 0)
            applied = int(by_status.get("applied") or 0)
            rejected = int(by_status.get("rejected") or 0)
            total = blocked + applied + rejected
            if total > 0 and (blocked / total) >= self.patchflow_blocked_ratio_threshold:
                anomalies.append(
                    Anomaly(
                        kind="patchflow_health_degraded",
                        severity="medium",
                        message=f"Patchflow blocked ratio is high ({blocked}/{total}).",
                        details={"by_status": by_status, "blocked_ratio": blocked / total},
                    )
                )

        # 5) Lease renew drift: many leases expired or close to expiry.
        leases = (overview.get("communication") or {}).get("leases") or {}
        if isinstance(leases, dict):
            expiring = int(leases.get("expiring_soon_count") or 0)
            expired = int(leases.get("expired_count") or 0)
            if expired > 0 or expiring >= self.lease_expiring_count_threshold:
                anomalies.append(
                    Anomaly(
                        kind="lease_renew_drift",
                        severity="high" if expired > 0 else "medium",
                        message=f"Lease renew pressure detected (expired={expired}, expiring_soon={expiring}).",
                        details={"leases": leases},
                    )
                )
            contention = int(leases.get("contention_events_recent") or 0)
            fencing = int(leases.get("fencing_conflicts_recent") or 0)
            if contention >= self.lease_contention_events_threshold:
                anomalies.append(
                    Anomaly(
                        kind="lease_contention_spike",
                        severity="medium",
                        message=f"Lease contention events spiked ({contention}).",
                        details={"leases": leases},
                    )
                )
            if fencing >= self.lease_fencing_conflicts_threshold:
                anomalies.append(
                    Anomaly(
                        kind="lease_fencing_conflict_spike",
                        severity="high",
                        message=f"Lease fencing conflicts spiked ({fencing}).",
                        details={"leases": leases},
                    )
                )

        # 6) Dead-letter growth trend.
        dead = (overview.get("communication") or {}).get("dead_letters") or {}
        trend = dead.get("trend") if isinstance(dead, dict) else {}
        if isinstance(trend, dict):
            recent = int(trend.get("recent_count") or 0)
            ratio = float(trend.get("growth_ratio") or 0.0)
            prev = int(trend.get("previous_count") or 0)
            if recent >= self.dead_letter_recent_min and ratio >= self.dead_letter_growth_ratio_threshold:
                anomalies.append(
                    Anomaly(
                        kind="dead_letter_growth_trend",
                        severity="medium",
                        message=f"Dead-letter growth trend elevated (recent={recent}, prev={prev}, ratio={ratio:.2f}).",
                        details={"dead_letters": dead},
                    )
                )

        return anomalies


class AnomalyTaskGenerator:
    """
    Analyzes observability metrics and enqueues remediation tasks 
    when anomalies are detected. (Task Sources v2)
    """
    
    def __init__(
        self, 
        obs_service: ObservabilityService, 
        task_queue: TaskQueue,
        thresholds: Optional[Dict[str, float]] = None
    ):
        self.obs = obs_service
        self.queue = task_queue
        # Default thresholds
        self.thresholds = thresholds or {
            "error_rate_max": 0.3,      # 30% error rate triggers a fix task
            "latency_ms_max": 4000,     # 4s avg latency triggers a fix task
            "token_spike_max": 500000   # 500k tokens in one action (safety check)
        }

    async def check_and_generate(self) -> List[str]:
        """
        Scan overview and generate tasks for any triggered thresholds.
        """
        overview = await self.obs.get_overview()
        generated_task_ids = []

        # 0. Structured anomaly detection (task/memory/policy/patchflow)
        detector = AnomalyDetector(
            llm_error_rate_threshold=self.thresholds.get("error_rate_max", 0.3),
            memory_latency_ms_threshold=self.thresholds.get("latency_ms_max", 30000),
            lease_expiring_count_threshold=int(self.thresholds.get("lease_expiring_count_max", 3)),
            lease_contention_events_threshold=int(self.thresholds.get("lease_contention_events_max", 4)),
            lease_fencing_conflicts_threshold=int(self.thresholds.get("lease_fencing_conflicts_max", 2)),
            dead_letter_growth_ratio_threshold=float(self.thresholds.get("dead_letter_growth_ratio_max", 2.0)),
            dead_letter_recent_min=int(self.thresholds.get("dead_letter_recent_min", 5)),
        )
        for anomaly in detector.detect(overview):
            task_id = await self._enqueue_remediation(
                f"Investigate anomaly '{anomaly.kind}': {anomaly.message}",
                domain="core",
                evidence={"details": anomaly.details or {}, "severity": anomaly.severity},
                anomaly_kind=anomaly.kind,
            )
            generated_task_ids.append(task_id)
        
        # 1. Check Tool Anomalies
        tool_data = overview.get("tools", {}).get("by_tool", [])
        for tool in tool_data:
            name = tool.get("tool_name")
            calls = tool.get("calls", 0)
            if calls < 5: continue # Ignore low volume
            
            error_rate = 1.0 - tool.get("success_rate", 1.0)
            if error_rate > self.thresholds["error_rate_max"]:
                task_id = await self._enqueue_remediation(
                    f"Fix tool '{name}': Error rate is high ({error_rate:.1%}).",
                    domain="core", 
                    evidence={"tool": tool, "threshold": "error_rate"},
                    anomaly_kind="tool_error_spike",
                )
                generated_task_ids.append(task_id)

        # 2. Check Domain Performance
        domain_data = overview.get("domain", {}).get("task", {}).get("by_domain_env", [])
        for dom in domain_data:
            name = dom.get("domain")
            success_rate = dom.get("success_rate", 1.0)
            if dom.get("tasks", 0) >= 3 and success_rate <= 0.5:
                task_id = await self._enqueue_remediation(
                    f"Investigate domain '{name}': Success rate dropped to {success_rate:.1%}.",
                    domain=name,
                    evidence={"domain_stats": dom, "threshold": "domain_success"},
                    anomaly_kind="task_failure_spike",
                )
                generated_task_ids.append(task_id)

        return generated_task_ids

    async def _enqueue_remediation(self, text: str, domain: str, evidence: Dict[str, Any], anomaly_kind: str) -> str:
        item = TaskQueueItem.new(
            input_text=text,
            domain=domain,
            priority=8, # High priority for remediation
            metadata={
                "source": "observability_anomaly",
                "kind": "anomaly_remediation",
                "anomaly_kind": str(anomaly_kind or ""),
                "evidence": evidence,
                "task_type": "remediation"
            }
        )
        self.queue.append(item)
        logger.info(f"AnomalyTaskGenerator: Enqueued remediation task: {item.task_id} - {text}")
        return item.task_id

def get_anomaly_generator(repo_root: str | Path = ".") -> AnomalyTaskGenerator:
    repo_root = Path(repo_root).resolve()
    obs = ObservabilityService(repo_root=repo_root)
    queue = TaskQueue(repo_root=repo_root)
    return AnomalyTaskGenerator(obs, queue)
