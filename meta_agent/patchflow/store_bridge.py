from __future__ import annotations
from quentin.utils.time import now_iso, now_utc

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import os

from meta_agent.patches.store import PatchStore
from meta_agent.patches.models import PatchProposal as CodePatchProposal
from meta_agent.patchflow.queue import PatchQueue
from meta_agent.patchflow.models import PatchProposal as QueuePatchProposal


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sync_patch_store_to_patch_queue(
    *,
    patch_store: Optional[PatchStore] = None,
    patch_queue: Optional[PatchQueue] = None,
    max_to_enqueue: int = 20,
) -> Dict[str, Any]:
    """
    Bridge Code PatchStore (meta_agent/patches/store.py) -> PatchFlow queue (meta_agent/patchflow/queue.py).

    Intended use:
    - SelfProgrammingEngineV2 (or blueprint-autopatch) writes PatchProposal entries to PatchStore.
    - PatchFlow consumes PatchQueue (JSONL) items.
    - This bridge makes PatchFlow "see" self-programming patches without changing the self-prog engine.

    Safety:
    - Does not apply patches, only enqueues them for PatchFlow evaluation.
    - Dedupe uses `patch.metadata.patchflow.enqueued == True`.
    """
    patch_store = patch_store or PatchStore(path=os.environ.get("META_AGENT_PATCH_STORE_PATH", "data/patches.json"))
    patch_queue = patch_queue or PatchQueue()

    # PatchStore.list_patches() is best-effort; we still guard every patch.
    patches: List[CodePatchProposal] = patch_store.list_patches(limit=2000)

    enqueued: List[str] = []
    skipped: List[str] = []

    for p in patches:
        if len(enqueued) >= int(max_to_enqueue):
            break
        pid = str(getattr(p, "id", "") or "")
        if not pid:
            continue

        meta = dict(getattr(p, "metadata", {}) or {})
        pf = dict(meta.get("patchflow") or {}) if isinstance(meta.get("patchflow"), dict) else {}
        if bool(pf.get("enqueued")):
            skipped.append(pid)
            continue

        status = str(getattr(p, "status", "") or "").strip().lower()
        if status not in ("proposed", "approved", "ready", "queued", ""):
            skipped.append(pid)
            continue
        if status == "queued":
            skipped.append(pid)
            continue

        diff = str(getattr(p, "diff", "") or "")
        if not diff.strip():
            skipped.append(pid)
            continue

        targets = list(getattr(p, "target_files", []) or [])
        intent = str(getattr(p, "intent", "") or "selfprog patch proposal")
        gap_id = str(meta.get("gap_id") or "")

        proposal = QueuePatchProposal.new(
            source="patch_store",
            kind="code",
            patch_format="unified_diff",
            targets=targets,
            body={"diff": diff, "raw": diff},
            intent=intent,
            reason=f"bridge_from_patch_store gap_id={gap_id}".strip(),
            blueprint_context=gap_id,
            metadata={"patch_store_id": pid, "patch_status": status},
        )
        patch_queue.append(proposal)

        # Mark as enqueued (best-effort).
        pf_update = {
            "enqueued": True,
            "patchflow_id": proposal.id,
            "enqueued_at": _now_iso(),
        }
        meta["patchflow"] = pf_update
        try:
            p.metadata = meta  # type: ignore[assignment]
            p.status = "queued"  # type: ignore[assignment]
        except Exception:
            # PatchProposal is a dataclass; assignment should work, but keep best-effort.
            pass
        try:
            patch_store.save_patch(p)
        except Exception:
            pass

        enqueued.append(pid)

    return {"enqueued": len(enqueued), "skipped": len(skipped), "enqueued_ids": enqueued}

