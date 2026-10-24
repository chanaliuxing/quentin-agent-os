from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from quentin.runtime.session_write_lock import acquire_session_write_lock


VariantLifecycleStatus = Literal[
    "created",
    "tested",
    "approved",
    "deployed",
    "rolled_back",
]


@dataclass
class VariantLifecycleRecord:
    variant_id: str
    environment: str
    status: VariantLifecycleStatus = "created"
    updated_at: float = field(default_factory=lambda: time.time())
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "VariantLifecycleRecord":
        return cls(
            variant_id=str(raw.get("variant_id") or ""),
            environment=str(raw.get("environment") or "sandbox"),
            status=raw.get("status") or "created",
            updated_at=float(raw.get("updated_at") or time.time()),
            meta=dict(raw.get("meta") or {}),
        )


class FileBackedVariantLifecycleStore:
    """
    Minimal lifecycle store used by both experiments and patches.

    Persisted under `data/research/variant_lifecycle.json`.
    """

    def __init__(self, *, repo_root: str | Path = ".", path: str | Path = "data/research/variant_lifecycle.json"):
        self.repo_root = Path(repo_root).resolve()
        self.path = (self.repo_root / path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except Exception:
            return {}

    def _save(self, obj: Dict[str, Any]) -> None:
        lock = acquire_session_write_lock(session_file=self.path)
        try:
            self.path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            lock["release"]()

    def get(self, *, variant_id: str, environment: str) -> Optional[VariantLifecycleRecord]:
        key = f"{environment}:{variant_id}"
        data = self._load()
        raw = data.get(key)
        if not isinstance(raw, dict):
            return None
        return VariantLifecycleRecord.from_dict(raw)

    def upsert(self, rec: VariantLifecycleRecord) -> None:
        key = f"{rec.environment}:{rec.variant_id}"
        data = self._load()
        rec.updated_at = time.time()
        data[key] = rec.to_dict()
        self._save(data)

    def transition(
        self,
        *,
        variant_id: str,
        environment: str,
        status: VariantLifecycleStatus,
        meta: Optional[Dict[str, Any]] = None,
    ) -> VariantLifecycleRecord:
        existing = self.get(variant_id=variant_id, environment=environment)
        rec = existing or VariantLifecycleRecord(variant_id=variant_id, environment=environment)
        rec.status = status
        if meta:
            rec.meta.update(meta)
        self.upsert(rec)
        return rec


def shadow_request(
    *,
    store: FileBackedVariantLifecycleStore,
    variant_id: str,
    environment: str,
    request_id: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rec = store.transition(
        variant_id=variant_id,
        environment=environment,
        status="tested",
        meta={"shadow_request_id": request_id, **(meta or {})},
    )
    return {"ok": True, "request_id": request_id, "lifecycle": rec.to_dict()}


def canary_request(
    *,
    store: FileBackedVariantLifecycleStore,
    variant_id: str,
    environment: str,
    request_id: str,
    fraction: float,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rec = store.transition(
        variant_id=variant_id,
        environment=environment,
        status="deployed",
        meta={"canary_request_id": request_id, "fraction": float(fraction), **(meta or {})},
    )
    return {"ok": True, "request_id": request_id, "fraction": float(fraction), "lifecycle": rec.to_dict()}


def rollback_request(
    *,
    store: FileBackedVariantLifecycleStore,
    variant_id: str,
    environment: str,
    request_id: str,
    reason: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rec = store.transition(
        variant_id=variant_id,
        environment=environment,
        status="rolled_back",
        meta={"rollback_request_id": request_id, "reason": reason, **(meta or {})},
    )
    return {"ok": True, "request_id": request_id, "lifecycle": rec.to_dict()}


def record_canary_result(
    *,
    store: FileBackedVariantLifecycleStore,
    variant_id: str,
    environment: str,
    ok: bool,
    reason: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    cooldown_seconds: int = 6 * 60 * 60,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Record canary outcome and enforce the blueprint gate:
    - If canary failed: rollback + freeze candidate + emit an ImmuneCase (best-effort).
    """
    metrics = dict(metrics or {})
    meta_in = dict(meta or {})

    outcome = {
        "ok": bool(ok),
        "reason": str(reason or ""),
        "metrics": metrics,
        "recorded_at": time.time(),
    }

    # Always persist the outcome on the lifecycle record.
    rec = store.transition(
        variant_id=variant_id,
        environment=environment,
        status="deployed",
        meta={"canary_result": outcome, **meta_in},
    )

    if ok:
        return {"ok": True, "lifecycle": rec.to_dict(), "rolled_back": None, "frozen": False}

    # Failure path: rollback + freeze.
    disabled_until = time.time() + max(60, int(cooldown_seconds or 0))
    rb = rollback_request(
        store=store,
        variant_id=variant_id,
        environment=environment,
        request_id=f"rollback::{uuid.uuid4().hex}",
        reason=str(reason or "canary_failed"),
        meta={
            "disabled_until": disabled_until,
            "disabled_reason": str(reason or "canary_failed"),
            "canary_result": outcome,
            **meta_in,
        },
    )

    # Best-effort: create an ImmuneCase so the system can investigate/regress.
    _emit_immune_case_best_effort(
        repo_root=store.repo_root,
        variant_id=variant_id,
        environment=environment,
        reason=str(reason or "canary_failed"),
        metrics=metrics,
        meta=meta_in,
    )
    return {"ok": True, "lifecycle": rb.get("lifecycle"), "rolled_back": rb, "frozen": True}


def _emit_immune_case_best_effort(
    *,
    repo_root: str | Path,
    variant_id: str,
    environment: str,
    reason: str,
    metrics: Dict[str, Any],
    meta: Dict[str, Any],
) -> None:
    try:
        from quentin.immune.anomaly import AnomalySignal
        from quentin.immune.store import ImmuneCaseStore
    except Exception:
        return

    try:
        store = ImmuneCaseStore(repo_root=repo_root)
        signal = AnomalySignal(
            anomaly_type="canary_failed",
            severity="high",
            reason=f"Canary failed for variant_id={variant_id} env={environment}: {reason}",
            suggested_actions=["rollback_candidate", "freeze_candidate", "run_regression_eval"],
            metrics={
                "variant_id": variant_id,
                "environment": environment,
                "reason": reason,
                "metrics": metrics,
                "meta": meta,
            },
        )
        store.append_case(
            goal={
                "domain": str(meta.get("domain") or "core"),
                "component": "release_protocol",
                "variant_id": variant_id,
                "environment": environment,
            },
            anomaly=signal,
            metrics={"release_protocol": "canary_failed"},
            recent_traces=[],
        )
    except Exception:
        return


def summarize_lifecycle(
    *,
    store: FileBackedVariantLifecycleStore,
    prefix: str = "",
) -> Dict[str, Any]:
    """
    Best-effort summary of lifecycle records.
    """
    data = store._load()  # intentionally internal: single source of truth is the json file
    by_status: Dict[str, int] = {}
    by_environment: Dict[str, int] = {}
    by_prefix: Dict[str, int] = {}
    total = 0
    for key, raw in (data or {}).items():
        if not isinstance(raw, dict):
            continue
        env = str(raw.get("environment") or (key.split(":", 1)[0] if ":" in key else "unknown"))
        variant_id = str(raw.get("variant_id") or "")
        if prefix and not variant_id.startswith(prefix):
            continue
        status = str(raw.get("status") or "unknown")
        total += 1
        by_status[status] = by_status.get(status, 0) + 1
        by_environment[env] = by_environment.get(env, 0) + 1
        pref = variant_id.split(":", 1)[0] if ":" in variant_id else "unknown"
        by_prefix[pref] = by_prefix.get(pref, 0) + 1
    return {
        "total": total,
        "by_status": by_status,
        "by_environment": by_environment,
        "by_prefix": by_prefix,
        "source": str(store.path),
    }
