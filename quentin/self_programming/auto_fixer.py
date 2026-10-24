import logging
import json
from typing import Dict, Any, Optional
from pathlib import Path
import os
import threading

# Connect to the real engine
from meta_agent.self_programming.engine_v2 import SelfProgrammingEngineV2, GapLike

logger = logging.getLogger(__name__)

class AutoFixerLoop:
    def __init__(self, repo_root: str, engine: Optional[SelfProgrammingEngineV2] = None):
        self.repo_root = Path(repo_root)
        self.error_counts = {}
        try:
            self.threshold = int(os.getenv("QUENTIN_AUTO_FIXER_THRESHOLD", "3") or "3")
        except Exception:
            self.threshold = 3
        self._engine = engine

    def on_system_event(self, event_type: str, payload: Dict[str, Any]):
        if event_type not in {"error", "blocked_actions", "capability_gap"}:
            return

        # Use explicit fingerprint if provided, otherwise derive from payload.
        fp = str(payload.get("fingerprint") or "").strip()
        if not fp:
            if event_type == "blocked_actions":
                fp = str(hash(",".join([str(x) for x in (payload.get("forbidden_actions") or [])[:12]])))
            elif event_type == "capability_gap":
                fp = str(hash(str(payload.get("gap_reason") or "")))
            else:
                err = str(payload.get("error", ""))
                fp = str(hash(err))

        self.error_counts[fp] = self.error_counts.get(fp, 0) + 1
        
        if self.error_counts[fp] == self.threshold:
            logger.warning(f"AutoFixer: Error threshold ({self.threshold}) reached for recurring error. Triggering autonomous repair.")
            self._trigger_repair(event_type, payload)

    def _trigger_repair(self, event_type: str, context: Dict[str, Any]):
        summary = str(context.get("error") or context.get("gap_reason") or context.get("forbidden_actions") or "")[:80]
        logger.warning(f"Repair triggered: {event_type} {summary}")
        
        # 1. Record the ticket
        p = self.repo_root / "data" / "tasks" / "repair_tickets.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(
                json.dumps(
                    {"event_type": event_type, "context": context, "status": "triggered"},
                    ensure_ascii=False,
                )
                + "\n"
            )

        # 2. Convert error to a GapLike object
        desc = ""
        if event_type == "blocked_actions":
            desc = f"System detected recurring blocked actions: {context.get('forbidden_actions')}\nContext: {json.dumps(context)}"
        elif event_type == "capability_gap":
            desc = f"System detected recurring capability gap: {context.get('gap_reason')}\nContext: {json.dumps(context)}"
        else:
            desc = f"System detected recurring error: {context.get('error')}\nContext: {json.dumps(context)}"

        gap = GapLike(
            id=f"auto-fix-{hash(event_type + '::' + str(summary)) & 0xFFFFFFFF:x}",
            title="Autonomous fix for recurring signal",
            description=desc,
            category="stability",
            priority=1,
            related_files=context.get("related_files", [])
        )

        # 3. Invoke the engine
        try:
            engine = self._engine
            if engine is None:
                # Lazy init if not injected (not ideal for performance but good for decoupling)
                from quentin.bootstrap.container import Container
                engine = Container(repo_root=self.repo_root).self_programming_engine
            
            # The engine v2 provides run_for_gaps which handles the event loop
            logger.info(f"AutoFixer: Dispatching gap {gap.id} to SelfProgrammingEngineV2.")
            threading.Thread(target=engine.run_for_gaps, args=([gap],), daemon=True).start()
        except Exception as e:
            logger.error(f"AutoFixer: Failed to invoke SelfProgrammingEngine: {e}")
