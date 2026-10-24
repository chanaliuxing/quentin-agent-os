from __future__ import annotations

from typing import Literal

ActionType = Literal[
    "llm_call",
    "tool_call",
    "code_patch",
    "experiment_run",
    "deploy",
    "storage_write",
    "none",
]

Environment = Literal["sandbox", "staging", "prod"]
Domain = Literal["core", "desktop", "legal", "trading", "cross"]
RiskLevel = Literal["low", "medium", "high", "critical"]

ACTION_LLM_CALL: ActionType = "llm_call"
ACTION_TOOL_CALL: ActionType = "tool_call"
ACTION_CODE_PATCH: ActionType = "code_patch"
ACTION_EXPERIMENT_RUN: ActionType = "experiment_run"
ACTION_DEPLOY: ActionType = "deploy"
ACTION_STORAGE_WRITE: ActionType = "storage_write"
ACTION_NONE: ActionType = "none"

ENV_SANDBOX: Environment = "sandbox"
ENV_STAGING: Environment = "staging"
ENV_PROD: Environment = "prod"

DOMAIN_CORE: Domain = "core"
DOMAIN_DESKTOP: Domain = "desktop"
DOMAIN_LEGAL: Domain = "legal"
DOMAIN_TRADING: Domain = "trading"
DOMAIN_CROSS: Domain = "cross"

RISK_LOW: RiskLevel = "low"
RISK_MEDIUM: RiskLevel = "medium"
RISK_HIGH: RiskLevel = "high"
RISK_CRITICAL: RiskLevel = "critical"

