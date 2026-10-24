from __future__ import annotations

import os
import time
from pathlib import Path

from quentin.llm.auth_profiles import (
    AuthProfile,
    AuthProfileStore,
    AuthProfileUsageStats,
    save_store,
    load_store,
)
from quentin.llm.provider_failover import call_with_auth_profiles_detailed


def test_auth_profiles_rotate_on_rate_limit(tmp_path: Path, monkeypatch) -> None:
    store_path = tmp_path / "auth_profiles.json"

    monkeypatch.setenv("KEY1", "k1")
    monkeypatch.setenv("KEY2", "k2")

    store = AuthProfileStore(
        profiles={
            "p1": AuthProfile(profile_id="p1", provider="openai", secret_ref="KEY1"),
            "p2": AuthProfile(profile_id="p2", provider="openai", secret_ref="KEY2"),
        }
    )
    save_store(store, str(store_path))

    def call_fn(api_key: str | None) -> str:
        assert api_key is not None
        if api_key == os.environ["KEY1"]:
            raise RuntimeError("429 rate limit")
        return "ok"

    res = call_with_auth_profiles_detailed(
        provider="openai",
        model="gpt-test",
        call_fn=call_fn,
        store_path=str(store_path),
    )
    assert res.text == "ok"
    assert res.selected_profile_id == "p2"
    assert res.retry_count == 1
    assert len(res.attempts) == 2
    assert res.attempts[0].profile_id == "p1"
    assert res.attempts[0].failover_reason == "rate_limit"
    assert res.attempts[1].profile_id == "p2"
    assert res.attempts[1].ok is True

    updated = load_store(str(store_path))
    s1 = updated.usage_stats.get("p1")
    assert s1 is not None
    assert s1.failure_counts.get("rate_limit", 0) == 1
    assert s1.cooldown_until is not None
    assert s1.cooldown_until > time.time()

    s2 = updated.usage_stats.get("p2")
    assert s2 is not None
    assert s2.last_used is not None


def test_auth_profiles_skip_cooldown_profiles(tmp_path: Path, monkeypatch) -> None:
    store_path = tmp_path / "auth_profiles.json"

    monkeypatch.setenv("KEY1", "k1")
    monkeypatch.setenv("KEY2", "k2")

    store = AuthProfileStore(
        profiles={
            "p1": AuthProfile(profile_id="p1", provider="openai", secret_ref="KEY1"),
            "p2": AuthProfile(profile_id="p2", provider="openai", secret_ref="KEY2"),
        },
        usage_stats={
            "p1": AuthProfileUsageStats(
                cooldown_until=time.time() + 3600,
                error_count=1,
                failure_counts={"rate_limit": 1},
            )
        },
    )
    save_store(store, str(store_path))

    def call_fn(api_key: str | None) -> str:
        assert api_key is not None
        # p1 should be skipped due to cooldown; we should only see KEY2.
        assert api_key == os.environ["KEY2"]
        return "ok"

    res = call_with_auth_profiles_detailed(
        provider="openai",
        model="gpt-test",
        call_fn=call_fn,
        store_path=str(store_path),
    )
    assert res.text == "ok"
    assert res.selected_profile_id == "p2"
