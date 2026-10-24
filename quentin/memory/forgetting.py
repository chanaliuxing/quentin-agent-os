from __future__ import annotations

import hashlib
import uuid
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from quentin.utils.time import now_utc


@dataclass(frozen=True)
class SafeForgettingConfig:
    sts_scan_limit: int = 2000
    mts_scan_limit: int = 2000
    sts_max_age_hours: int = 72
    # Intelligent Forgetting params (Blueprint v3)
    retention_threshold: float = 0.1  # Scores below this are decayed
    decay_constant: float = 0.05      # Controls how fast memories fade
    mts_dedup_exact: bool = True


def calculate_retention_score(rec: Any, now: datetime, decay_constant: float) -> float:
    """
    Blueprint v3: Multi-dimensional retention score.
    Formula: Score = Importance * (1 + log1p(AccessCount)) / (1 + HoursElapsed^DecayConstant)
    """
    importance_raw = getattr(rec, "importance", 0.5)
    if importance_raw is None:
        importance_raw = 0.5
    importance = float(importance_raw)

    access_raw = getattr(rec, "access_count", 0)
    if access_raw is None:
        access_raw = 0
    access_count = int(access_raw)
    
    created_at = getattr(rec, "created_at", now)
    if not isinstance(created_at, datetime):
        created_at = now
        
    delta_hours = (now - created_at).total_seconds() / 3600.0
    
    # 1. Base importance weight
    # 2. Usage boost (logarithmic)
    usage_boost = 1.0 + math.log1p(access_count)
    
    # 3. Ebbinghaus-style time decay
    time_factor = 1.0 + math.pow(max(0.0, delta_hours), decay_constant)
    
    return (importance * usage_boost) / time_factor


def run_safe_forgetting(*, fabric: Any, config: Optional[SafeForgettingConfig] = None) -> Dict[str, Any]:
    """
    Safe forgetting v2:
    - Multi-dimensional STS cleanup using Ebbinghaus decay + Usage boost
    - MTS compaction: exact-content dedup; mark older duplicates as decayed
    """
    cfg = config or SafeForgettingConfig()
    started_at = now_utc()

    try:
        from quentin.memory.models import MemoryTier

        sts = fabric.get_records_for_processing(tier=MemoryTier.STS, limit=cfg.sts_scan_limit)
        mts = fabric.get_records_for_processing(tier=MemoryTier.MTS, limit=cfg.mts_scan_limit)
    except Exception:
        sts = fabric.get_sts_for_consolidation(limit=cfg.sts_scan_limit)
        mts = fabric.get_records_for_processing(tier="mid_term", limit=cfg.mts_scan_limit)  # type: ignore[arg-type]

    # 1. Intelligent STS Forgetting
    sts_to_decay: List[str] = []
    sts_scores: List[float] = []
    
    for rec in sts:
        score = calculate_retention_score(rec, started_at, cfg.decay_constant)
        if score < cfg.retention_threshold:
            sts_to_decay.append(rec.id)
        sts_scores.append(score)

    if sts_to_decay:
        fabric.decay_records(sts_to_decay)

    avg_sts_score = sum(sts_scores) / len(sts_scores) if sts_scores else 0.0

    # 2. MTS Compaction (Dedup)
    mts_deduped = 0
    mts_decayed = 0
    if cfg.mts_dedup_exact and mts:
        by_hash: Dict[str, List[Any]] = {}
        for rec in mts:
            h = hashlib.sha256((rec.content or "").encode("utf-8", "ignore")).hexdigest()
            by_hash.setdefault(h, []).append(rec)

        for _h, recs in by_hash.items():
            if len(recs) <= 1:
                continue
            # Keep newest
            recs.sort(key=lambda r: getattr(r, "created_at", started_at), reverse=True)
            keeper = recs[0]
            dupes = recs[1:]
            # Update keeper supersedes list
            try:
                keeper.supersedes_ids = list(set(list(getattr(keeper, "supersedes_ids", []) or []) + [d.id for d in dupes]))
                fabric.store.update(keeper)
                mts_deduped += 1
            except Exception:
                pass
            for d in dupes:
                try:
                    fabric.store.mark_decayed(d.id)
                    mts_decayed += 1
                except Exception:
                    continue

    finished_at = now_utc()
    report = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "sts_scanned": len(sts),
        "sts_decayed": len(sts_to_decay),
        "avg_sts_retention_score": float(round(avg_sts_score, 4)),
        "mts_scanned": len(mts),
        "mts_dedup_groups": mts_deduped,
        "mts_decayed": mts_decayed,
    }

    # Best-effort audit
    try:
        from quentin.kernel.audit import AuditEvent, default_audit_logger

        default_audit_logger().append(
            AuditEvent(
                action_id=f"memory_forgetting::{uuid.uuid4().hex}",
                event_type="memory_forgetting",
                phase="success",
                actor="memory_fabric",
                payload=report,
            )
        )
    except Exception:
        pass

    return report
