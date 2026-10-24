from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def _kv_init(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.commit()


def _kv_set(db_path: Path, key: str, value) -> None:
    raw = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO kv(key, value_json, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            (key, raw, 123.0),
        )
        conn.commit()


def test_blueprint_tracker_detects_kv_backed_experiments(tmp_path: Path, monkeypatch) -> None:
    # Create a minimal spec with one item that requires experiment evidence.
    spec = {
        "version": "v3-test",
        "items": [
            {
                "id": "kernel.model_router",
                "name": "ModelRouter",
                "layer": "L0_infra_kernel",
                "phase": "phase0_kernel_trace",
                "category": "routing",
                "description": "test",
                "required_capabilities": [],
                "hints": {
                    "modules": ["quentin/routing/model_router.py"],
                    "trace_capability_id": "model_router",
                    "experiment_capability": "model_router",
                },
            }
        ],
    }
    spec_path = tmp_path / "blueprint" / "spec_v3.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    # Create KVStore sqlite file with exp:index:all + exp:record:<id>.
    kv_path = tmp_path / "data" / "kv_store.sqlite3"
    _kv_init(kv_path)
    _kv_set(kv_path, "exp:index:all", ["exp_test_1"])
    _kv_set(
        kv_path,
        "exp:record:exp_test_1",
        {
            "experiment_id": "exp_test_1",
            "name": "x",
            "description": "x",
            "config": {"target_module": "model_router", "metrics": ["success_rate"]},
            "variants": [],
            "created_at": "2026-02-07T00:00:00Z",
            "updated_at": "2026-02-07T00:00:00Z",
        },
    )

    monkeypatch.setenv("QUENTIN_KVSTORE_PATH", str(kv_path))

    from quentin.blueprint.tracker import BlueprintGapTracker

    tracker = BlueprintGapTracker(repo_root=tmp_path, spec_path=spec_path)
    report = tracker.scan()
    assert report.total_items == 1
    assert report.items[0].has_experiments is True

