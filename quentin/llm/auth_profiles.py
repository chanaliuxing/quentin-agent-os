from __future__ import annotations

from dataclasses import dataclass, asdict, field
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional, List, Literal, Any
import logging

logger = logging.getLogger(__name__)

AuthMode = Literal["api_key", "token", "oauth"]

@dataclass
class AuthProfileUsageStats:
    last_used: Optional[float] = None
    error_count: int = 0
    cooldown_until: Optional[float] = None
    disabled_until: Optional[float] = None
    failure_counts: Dict[str, int] = field(default_factory=dict)
    state: Literal["healthy", "degraded", "cooldown", "disabled"] = "healthy"
    health_score: float = 100.0
    consecutive_failures: int = 0
    last_failure_reason: Optional[str] = None

@dataclass
class AuthProfile:
    profile_id: str
    provider: str
    mode: AuthMode = "api_key"
    secret_ref: Optional[str] = None
    label: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    priority: int = 10

@dataclass
class AuthProfileStore:
    profiles: Dict[str, AuthProfile] = field(default_factory=dict)
    usage_stats: Dict[str, AuthProfileUsageStats] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "profiles": {k: asdict(v) for k, v in self.profiles.items()},
            "usage_stats": {k: asdict(v) for k, v in self.usage_stats.items()},
        }

    @classmethod
    def from_dict(cls, raw: Dict) -> "AuthProfileStore":
        profiles = {}
        for k, v in (raw.get("profiles") or {}).items():
            try:
                profiles[k] = AuthProfile(**v)
            except Exception:
                pass
        
        usage_stats = {}
        for k, v in (raw.get("usage_stats") or {}).items():
            try:
                usage_stats[k] = AuthProfileUsageStats(**v)
            except Exception:
                pass
                
        return cls(profiles=profiles, usage_stats=usage_stats)

def _store_path(path: Optional[str] = None) -> Path:
    repo_root = Path(".").resolve()
    base = Path(path) if path else repo_root / "data" / "auth_profiles.json"
    base.parent.mkdir(parents=True, exist_ok=True)
    return base

def load_store(path: Optional[str] = None) -> AuthProfileStore:
    p = _store_path(path)
    if not p.exists():
        return AuthProfileStore()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return AuthProfileStore.from_dict(raw)
    except Exception:
        return AuthProfileStore()

def save_store(store: AuthProfileStore, path: Optional[str] = None) -> None:
    p = _store_path(path)
    try:
        p.write_text(json.dumps(store.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    except: pass

def resolve_api_key(profile: AuthProfile) -> Optional[str]:
    if profile.api_key: return profile.api_key
    if not profile.secret_ref: return None
    return os.getenv(profile.secret_ref)

def _now() -> float:
    return time.time()

def _update_health(stats: AuthProfileUsageStats):
    if stats.disabled_until and stats.disabled_until > _now():
        stats.state = "disabled"
        stats.health_score = 0.0
        return
    if stats.cooldown_until and stats.cooldown_until > _now():
        stats.state = "cooldown"
        stats.health_score = max(10.0, 50.0 - (stats.consecutive_failures * 10))
        return
    base_score = 100.0
    penalty = (stats.consecutive_failures * 15) + (stats.error_count * 0.1)
    stats.health_score = max(0.0, base_score - penalty)
    if stats.health_score < 60.0:
        stats.state = "degraded"
    else:
        stats.state = "healthy"

def resolve_profile_order(
    store: AuthProfileStore,
    *,
    provider: str,
    preferred_profile: Optional[str] = None,
    only_available: bool = False,
) -> List[str]:
    provider_key = provider.strip().lower()
    candidates = [p for p in store.profiles.values() if p.provider.strip().lower() == provider_key]
    
    valid_candidates = []
    for p in candidates:
        stats = store.usage_stats.get(p.profile_id)
        if not stats: 
            valid_candidates.append(p)
            continue
        _update_health(stats)
        if only_available and stats.state in ("disabled", "cooldown"):
            continue
        valid_candidates.append(p)

    def score(p: AuthProfile) -> float:
        stats = store.usage_stats.get(p.profile_id)
        if not stats: return 1000.0 + p.priority
        health = stats.health_score
        priority_boost = p.priority * 5
        
        # P5: OpenClaw Parity - Recency and Observation Penalties
        recency_penalty = 0
        if stats.last_used:
            ago = _now() - stats.last_used
            if ago < 60: recency_penalty = 50.0 / (ago + 1)
            
        # Observation Penalty: If just recovered from cooldown, give it some breathing room
        observation_penalty = 0
        if stats.state == "healthy" and stats.error_count > 0:
            # error_count resets on mark_used, so if it's > 0 here, it likely just came off cooldown
            observation_penalty = 30.0

        final_score = health + priority_boost - recency_penalty - observation_penalty
        if preferred_profile == p.profile_id: final_score += 10000.0
        return final_score

    sorted_candidates = sorted(valid_candidates, key=score, reverse=True)
    return [p.profile_id for p in sorted_candidates]

def list_available_profiles(store: AuthProfileStore, *, provider: str, preferred_profile: Optional[str] = None) -> List[str]:
    return resolve_profile_order(store, provider=provider, preferred_profile=preferred_profile, only_available=True)

def calculate_cooldown_ms(error_count: int, provider: str = "generic") -> float:
    """
    P5: Ported from OpenClaw's calculateAuthProfileCooldownMs.
    Exponential backoff: 1min, 5min, 25min, max 1 hour.
    """
    normalized = max(1, error_count)
    
    # Provider-specific base adjustments (OpenClaw Parity)
    if provider.lower() == "ollama":
        # Local models recover faster
        return min(300 * 1000, 10 * 1000 * (3 ** min(normalized - 1, 3)))
        
    return min(
        60 * 60 * 1000, # 1 hour max
        60 * 1000 * (5 ** min(normalized - 1, 3))
    )

def mark_used(store: AuthProfileStore, profile_id: str) -> None:
    stats = store.usage_stats.get(profile_id) or AuthProfileUsageStats()
    stats.last_used = _now()
    stats.consecutive_failures = 0
    stats.error_count = 0 # Reset overall error count on success
    stats.state = "healthy"
    stats.health_score = min(100.0, stats.health_score + 5.0)
    stats.cooldown_until = None
    stats.disabled_until = None
    store.usage_stats[profile_id] = stats

def mark_failure(store: AuthProfileStore, profile_id: str, reason: str, explicit_cooldown_s: Optional[float] = None) -> None:
    stats = store.usage_stats.get(profile_id) or AuthProfileUsageStats()
    profile = store.profiles.get(profile_id)
    provider = profile.provider if profile else "generic"
    
    stats.error_count += 1
    stats.consecutive_failures += 1
    stats.last_failure_reason = reason
    stats.failure_counts[reason] = stats.failure_counts.get(reason, 0) + 1
    
    now = _now()
    
    # P5: Surgery Fifty-six - Explicit Header-based Cooldown (OpenClaw Parity)
    if explicit_cooldown_s is not None and explicit_cooldown_s > 0:
        logger.warning(f"AuthProfiles: Profile {profile_id} received EXPLICIT cooldown of {explicit_cooldown_s}s")
        stats.cooldown_until = now + explicit_cooldown_s
        stats.state = "cooldown"
    # P5: Surgery Seventeen - Micro-Cooldown Logic
    elif reason in ("billing", "auth", "401", "403"):
        # Hard failure: Disable for a long time (exponential: 1h, 2h, 4h...)
        disable_duration = min(24 * 3600.0, (2 ** stats.consecutive_failures) * 3600.0)
        stats.disabled_until = now + disable_duration
        stats.state = "disabled"
        logger.error(f"AuthProfiles: Profile {profile_id} HARD DISABLED for {disable_duration}s due to {reason}")
    else:
        # Soft failure (429, timeout): Micro-cooldown
        cooldown_ms = calculate_cooldown_ms(stats.consecutive_failures, provider)
        stats.cooldown_until = now + (cooldown_ms / 1000.0)
        stats.state = "cooldown"
        logger.warning(f"AuthProfiles: Profile {profile_id} entered COOLDOWN for {cooldown_ms}ms due to {reason}")
        
    _update_health(stats)
    store.usage_stats[profile_id] = stats

class AuthProfileManager:
    def __init__(self, store_path: Optional[str] = None):
        self.store_path = store_path
        self._store = load_store(self.store_path)
        self._maybe_bootstrap_from_env()

    def _maybe_bootstrap_from_env(self):
        if not self._store.profiles:
            ollama_base = os.getenv("LLM_BASE_URL") or "http://localhost:11434"
            ollama_base = ollama_base.split("/api")[0].rstrip("/")
            self.add_profile(AuthProfile(
                profile_id="env_default_ollama",
                provider="ollama",
                base_url=ollama_base,
                secret_ref="LLM_API_KEY"
            ))

    def add_profile(self, profile: AuthProfile):
        self._store.profiles[profile.profile_id] = profile
        save_store(self._store, self.store_path)

    def get_best_profile(self, provider: str) -> Optional[AuthProfile]:
        available = list_available_profiles(self._store, provider=provider)
        if not available:
            return AuthProfile(
                profile_id="direct_env",
                provider=provider,
                base_url=os.getenv("LLM_BASE_URL")
            )
        return self._store.profiles[available[0]]

    def report_result(self, profile_id: str, success: bool, error_code: Optional[Any] = None, explicit_cooldown_s: Optional[float] = None):
        if success:
            mark_used(self._store, profile_id)
        else:
            reason = str(error_code) if error_code else "unknown"
            mark_failure(self._store, profile_id, reason, explicit_cooldown_s=explicit_cooldown_s)
        save_store(self._store, self.store_path)
        if success:
            mark_used(self._store, profile_id)
        else:
            reason = str(error_code) if error_code else "unknown"
            mark_failure(self._store, profile_id, reason)
        save_store(self._store, self.store_path)

_MANAGER_INSTANCE = None
def get_auth_manager() -> AuthProfileManager:
    global _MANAGER_INSTANCE
    if _MANAGER_INSTANCE is None:
        _MANAGER_INSTANCE = AuthProfileManager()
    return _MANAGER_INSTANCE
