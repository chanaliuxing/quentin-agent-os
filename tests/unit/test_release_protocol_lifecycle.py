from pathlib import Path

from quentin.l3.research.release_protocol import (
    FileBackedVariantLifecycleStore,
    canary_request,
    record_canary_result,
    rollback_request,
    shadow_request,
    summarize_lifecycle,
)


def test_variant_lifecycle_transitions(tmp_path: Path) -> None:
    store = FileBackedVariantLifecycleStore(repo_root=tmp_path, path="variant_lifecycle.json")
    variant_id = "patch:abc123"

    shadow = shadow_request(
        store=store,
        variant_id=variant_id,
        environment="sandbox",
        request_id="shadow::1",
        meta={"x": 1},
    )
    assert shadow["ok"] is True

    canary = canary_request(
        store=store,
        variant_id=variant_id,
        environment="sandbox",
        request_id="canary::1",
        fraction=0.1,
        meta={"y": 2},
    )
    assert canary["ok"] is True

    rb = rollback_request(
        store=store,
        variant_id=variant_id,
        environment="sandbox",
        request_id="rollback::1",
        reason="fail",
        meta={"z": 3},
    )
    assert rb["ok"] is True

    summary = summarize_lifecycle(store=store, prefix="patch:")
    assert summary["total"] >= 1
    assert summary["by_status"].get("rolled_back", 0) >= 1


def test_canary_failure_triggers_rollback_and_freeze(tmp_path: Path) -> None:
    store = FileBackedVariantLifecycleStore(repo_root=tmp_path, path="variant_lifecycle.json")
    variant_id = "patch:failcase"

    canary_request(
        store=store,
        variant_id=variant_id,
        environment="staging",
        request_id="canary::x",
        fraction=0.05,
        meta={"domain": "desktop"},
    )

    res = record_canary_result(
        store=store,
        variant_id=variant_id,
        environment="staging",
        ok=False,
        reason="latency_regression",
        metrics={"p95_latency_ms": 9999},
        cooldown_seconds=120,
        meta={"domain": "desktop"},
    )
    assert res["ok"] is True
    assert res["frozen"] is True
    assert res["lifecycle"]["status"] == "rolled_back"
