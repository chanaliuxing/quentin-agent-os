from quentin.llm.router_deprecated import ModelRouter  # compatibility shim
from quentin.models.router import ModelInfo
from quentin.llm.failover import FailoverError, classify_failover_reason
from quentin.llm.auth_profiles import (
    AuthProfile,
    AuthProfileStore,
    AuthProfileUsageStats,
    load_store as load_auth_profile_store,
    save_store as save_auth_profile_store,
)
from quentin.llm.provider_failover import call_with_auth_profiles
from quentin.llm.context_budget import (
    ContextWindowInfo,
    ContextWindowGuardResult,
    estimate_tokens,
    resolve_context_window_info,
    evaluate_context_window_guard,
    apply_context_budget,
)
from quentin.llm.compaction import CompactionResult, compact_text, prune_history_texts

__all__ = [
    "ModelRouter",
    "ModelInfo",
    "FailoverError",
    "classify_failover_reason",
    "AuthProfile",
    "AuthProfileStore",
    "AuthProfileUsageStats",
    "load_auth_profile_store",
    "save_auth_profile_store",
    "call_with_auth_profiles",
    "ContextWindowInfo",
    "ContextWindowGuardResult",
    "estimate_tokens",
    "resolve_context_window_info",
    "evaluate_context_window_guard",
    "apply_context_budget",
    "CompactionResult",
    "compact_text",
    "prune_history_texts",
]
