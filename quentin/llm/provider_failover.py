from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, List, Any, Dict

from quentin.llm.auth_profiles import (
    load_store,
    save_store,
    list_available_profiles,
    resolve_api_key,
    mark_failure,
    mark_used,
)
from quentin.llm.failover import coerce_failover_error, FailoverError


@dataclass
class AuthProfileAttempt:
    profile_id: Optional[str]
    ok: bool
    failover_reason: Optional[str] = None
    failover_status: Optional[int] = None
    error: Optional[str] = None


@dataclass
class AuthProfileCallResult:
    text: str
    selected_profile_id: Optional[str]
    attempts: List[AuthProfileAttempt]

    @property
    def retry_count(self) -> int:
        return max(0, len(self.attempts) - 1)

    def to_trace_dict(self) -> Dict[str, Any]:
        return {
            "selected_profile_id": self.selected_profile_id,
            "retry_count": self.retry_count,
            "attempts": [
                {
                    "profile_id": a.profile_id,
                    "ok": a.ok,
                    "failover_reason": a.failover_reason,
                    "failover_status": a.failover_status,
                    "error": a.error,
                }
                for a in self.attempts
            ],
        }


def call_with_auth_profiles(
    *,
    provider: str,
    model: str,
    call_fn: Callable[[Optional[str]], str],
    store_path: Optional[str] = None,
    preferred_profile: Optional[str] = None,
) -> str:
    return call_with_auth_profiles_detailed(
        provider=provider,
        model=model,
        call_fn=call_fn,
        store_path=store_path,
        preferred_profile=preferred_profile,
    ).text


def call_with_auth_profiles_detailed(
    *,
    provider: str,
    model: str,
    call_fn: Callable[[Optional[str]], str],
    store_path: Optional[str] = None,
    preferred_profile: Optional[str] = None,
    cancel_token: Any = None,
) -> AuthProfileCallResult:
    # Phase 5.4: Unified Abort Signal
    if cancel_token is not None and hasattr(cancel_token, "raise_if_cancelled"):
        cancel_token.raise_if_cancelled()

    store = load_store(store_path)
    order = list_available_profiles(store, provider=provider, preferred_profile=preferred_profile)
    if not order:
        # No profiles configured or none currently available; call with no auth.
        text = call_fn(None)
        return AuthProfileCallResult(
            text=text,
            selected_profile_id=None,
            attempts=[AuthProfileAttempt(profile_id=None, ok=True)],
        )

    last_error: Optional[Exception] = None
    attempts: List[AuthProfileAttempt] = []
    for profile_id in order:
        profile = store.profiles.get(profile_id)
        if not profile:
            continue
        api_key = resolve_api_key(profile)
        if not api_key:
            mark_failure(store, profile_id, "auth")
            save_store(store, store_path)
            attempts.append(
                AuthProfileAttempt(
                    profile_id=profile_id,
                    ok=False,
                    failover_reason="auth",
                    failover_status=401,
                    error="missing_api_key",
                )
            )
            continue
        try:
            text = call_fn(api_key)
            mark_used(store, profile_id)
            save_store(store, store_path)
            attempts.append(AuthProfileAttempt(profile_id=profile_id, ok=True))
            return AuthProfileCallResult(text=text, selected_profile_id=profile_id, attempts=attempts)
        except Exception as err:  # noqa: BLE001
            last_error = err
            failover = coerce_failover_error(
                err, provider=provider, model=model, profile_id=profile_id
            )
            if failover:
                mark_failure(store, profile_id, failover.reason)
                save_store(store, store_path)
                attempts.append(
                    AuthProfileAttempt(
                        profile_id=profile_id,
                        ok=False,
                        failover_reason=failover.reason,
                        failover_status=failover.status,
                        error=str(err),
                    )
                )
                continue
            raise

    if isinstance(last_error, FailoverError):
        raise last_error
    if last_error:
        raise last_error
    raise RuntimeError("no available auth profiles")
