# meta_agent/tools/registry.py
from __future__ import annotations
from quentin.utils.time import now_iso, now_utc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional
import datetime as dt


class ToolLifecycle(str, Enum):
    EXPERIMENTAL = "experimental"
    TRUSTED = "trusted"
    DEPRECATED = "deprecated"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ToolMetrics:
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: int = 0
    last_error: Optional[str] = None
    last_used_at: Optional[str] = None

    @property
    def success_rate(self) -> float:
        if self.call_count == 0:
            return 0.0
        return self.success_count / float(self.call_count)

    @property
    def avg_latency_ms(self) -> Optional[float]:
        if self.call_count == 0:
            return None
        return self.total_latency_ms / float(self.call_count)

    def record_call(self, *, success: bool, latency_ms: Optional[int] = None, error: Optional[str] = None) -> None:
        self.call_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
            if error:
                self.last_error = error
        if latency_ms is not None:
            self.total_latency_ms += max(0, latency_ms)
        self.last_used_at = now_iso()


@dataclass
class ToolGovernance:
    lifecycle: ToolLifecycle = ToolLifecycle.EXPERIMENTAL
    risk_level: RiskLevel = RiskLevel.MEDIUM
    domain_scope: List[str] = field(default_factory=list)
    council_score: Optional[float] = None


@dataclass
class ToolRegistration:
    tool_id: str
    server: str
    description: str
    signature: str
    transport: str = "stdio"
    uri: Optional[str] = None
    auth_token: Optional[str] = None
    examples: List[Dict[str, Any]] = field(default_factory=list)
    governance: ToolGovernance = field(default_factory=ToolGovernance)
    metrics: ToolMetrics = field(default_factory=ToolMetrics)

    def to_summary(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "server": self.server,
            "transport": self.transport,
            "uri": self.uri,
            "description": self.description,
            "signature": self.signature,
            "governance": {
                "lifecycle": self.governance.lifecycle.value,
                "risk_level": self.governance.risk_level.value,
                "domain_scope": list(self.governance.domain_scope),
                "council_score": self.governance.council_score,
            },
            "metrics": {
                "call_count": self.metrics.call_count,
                "success_rate": self.metrics.success_rate,
                "avg_latency_ms": self.metrics.avg_latency_ms,
                "last_used_at": self.metrics.last_used_at,
            },
        }


class ToolRegistry:
    """
    In-memory registry for MCP tools and local skills.

    This layer exposes lifecycle state so Planner/Executor can prefer trusted tools
    while still experimenting with new capabilities.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolRegistration] = {}

    def register(self, registration: ToolRegistration) -> None:
        self._tools[registration.tool_id] = registration

    def get(self, tool_id: str) -> Optional[ToolRegistration]:
        return self._tools.get(tool_id)

    def list(self, *, lifecycle: Optional[ToolLifecycle] = None) -> List[ToolRegistration]:
        if lifecycle is None:
            return list(self._tools.values())
        return [t for t in self._tools.values() if t.governance.lifecycle == lifecycle]

    def update_lifecycle(self, tool_id: str, lifecycle: ToolLifecycle) -> None:
        tool = self._tools.get(tool_id)
        if not tool:
            raise KeyError(f"tool not found: {tool_id}")
        tool.governance.lifecycle = lifecycle

    def record_invocation(
        self,
        tool_id: str,
        *,
        success: bool,
        latency_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        tool = self._tools.get(tool_id)
        if not tool:
            return
        tool.metrics.record_call(success=success, latency_ms=latency_ms, error=error)

    def bootstrap(self, registrations: Iterable[ToolRegistration]) -> None:
        for reg in registrations:
            self.register(reg)
