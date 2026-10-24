# meta_agent/research/api.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from quentin.traces.core import JsonlTraceRecorder, TraceEventType, new_trace_event
from quentin.l3.research.interface import ResearchInterfaceV3


trace = JsonlTraceRecorder(repo_root=".")


class ResearchAPI:
    """
    Canonical Research API (meta_agent surface), backed by Quentin's ResearchInterfaceV3.

    This removes the old placeholder in-memory backend while keeping a small, stable API:
    - create_experiment(config) -> returns experiment record dict
    - get_experiment(experiment_id) -> returns experiment record dict (or None)
    - run_experiment_async(experiment_id) -> runs and returns run result dict (sync execution)
    - get_experiment_summary(experiment_id) -> export dict with experiment + runs
    """

    def __init__(self, impl: Optional[ResearchInterfaceV3] = None) -> None:
        self.impl = impl or ResearchInterfaceV3(repo_root=".")

    def create_experiment(self, config: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.impl.create_experiment(config)
        trace.record_event(
            new_trace_event(
                trace_id=str(rec.get("experiment_id") or rec.get("id") or "research"),
                event_type=TraceEventType.DECISION,
                payload={"action": "research_experiment_created", "config": config, "record": rec},
            )
        )
        return rec

    def get_experiment(self, exp_id: str) -> Optional[Dict[str, Any]]:
        exported = self.impl.export_results(exp_id)
        exp = exported.get("experiment")
        return exp if isinstance(exp, dict) else None

    def run_experiment_async(self, exp_id: str, *, cases: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        run = self.impl.run_experiment(exp_id, cases=cases)
        trace.record_event(
            new_trace_event(
                trace_id=str(exp_id),
                event_type=TraceEventType.DECISION,
                payload={"action": "research_experiment_run", "run": run},
            )
        )
        return run

    def get_experiment_summary(self, exp_id: str) -> Dict[str, Any]:
        exported = self.impl.export_results(exp_id)
        trace.record_event(
            new_trace_event(
                trace_id=str(exp_id),
                event_type=TraceEventType.DECISION,
                payload={"action": "research_experiment_exported", "exported": exported},
            )
        )
        return exported
