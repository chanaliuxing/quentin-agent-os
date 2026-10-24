from __future__ import annotations

from typing import List, Optional

from quentin.l3.research.experiments import ExperimentRecord


class PolicyAndGovernance:
    """
    负责实验的策略和治理。

    - 检查实验是否符合“宪法”或其它策略规则。
    - 例如，可以禁止在某些领域（如 'trading'）运行高风险实验。
    """

    def __init__(
        self,
        *,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
    ) -> None:
        self.allowed_domains = set(allowed_domains) if allowed_domains else None
        self.blocked_domains = set(blocked_domains) if blocked_domains else None

    def approve_experiment(self, record: ExperimentRecord) -> bool:
        """
        判断一个实验是否被批准运行。
        """
        domain = record.config.meta.get("domain")

        if domain:
            if self.allowed_domains is not None and domain not in self.allowed_domains:
                return False
            if self.blocked_domains is not None and domain in self.blocked_domains:
                return False

        # Add more complex rules here, e.g., based on experiment tags, estimated cost, etc.

        return True

PolicyEngine = PolicyAndGovernance