from __future__ import annotations

import logging
import asyncio
import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from quentin.skills.miner import SkillMiner
from quentin.skills.candidate_pipeline import (
    SkillCandidate,
    SkillCandidateStore,
    SkillCandidateInstaller,
    SandboxPytestRunner,
    CandidateTestReport
)
from quentin.skills.registry import FileBackedSkillRegistry
from quentin.l3.research.eval_harness import EvalHarness, EvalCase, ExperimentVariant
from quentin.traces.core import JsonlTraceRecorder, TraceEventType, new_trace_event
from quentin.cognitive.loop import CognitiveTask, CognitiveResult
from quentin.infra.storage.kv_store import KVStore
from quentin.infra.logging import Tracer

logger = logging.getLogger(__name__)

class AutomatedSkillEvolution:
    """
    Closure for Skill & Code Evolution loop (Gap 3).
    Ties together Miner -> Store -> Test -> Eval -> Promotion.
    """

    def __init__(
        self,
        repo_root: str | Path = ".",
        registry_path: str = "data/skills.json",
        candidate_store_path: str = "data/skills/candidates.jsonl",
    ):
        self.repo_root = Path(repo_root).resolve()
        self.registry = FileBackedSkillRegistry(path=self.repo_root / registry_path)
        self.candidate_store = SkillCandidateStore(path=self.repo_root / candidate_store_path)
        self.installer = SkillCandidateInstaller(repo_root=self.repo_root)
        self.test_runner = SandboxPytestRunner(repo_root=self.repo_root)
        self.trace_recorder = JsonlTraceRecorder(repo_root=str(self.repo_root))
        
        # Eval Harness dependencies
        self.kv = KVStore() # Assuming it's initialized correctly in bootstrap
        self.tracer = Tracer()
        self.eval_harness = EvalHarness(kv=self.kv, tracer=self.tracer)
        
        self.miner = SkillMiner(
            registry=self.registry,
            candidate_store=self.candidate_store
        )

    async def run_cycle(self, domain: str = "core") -> Dict[str, Any]:
        """
        Run one full cycle: Mine -> Test -> Eval -> Promote.
        """
        trace_id = f"skill-evo-cycle-{uuid.uuid4().hex[:8]}"
        self._trace("cycle_start", {"domain": domain}, trace_id)
        
        # 1. Mine candidates from successful traces
        # (This is a simplified version of finding successful traces)
        mined_candidates = await self._mine_candidates(domain)
        self._trace("mining_done", {"count": len(mined_candidates)}, trace_id)
        
        results = []
        for cand in mined_candidates:
            # 2. Test in sandbox
            report: CandidateTestReport = self.test_runner.run(cand)
            self._trace("candidate_tested", {
                "candidate_id": cand.candidate_id,
                "ok": report.ok,
                "exit_code": report.exit_code
            }, trace_id)
            
            if not report.ok:
                results.append({"id": cand.candidate_id, "status": "failed_tests", "error": report.stderr})
                continue
                
            # 3. Evaluate (Offline A/B or keyword check)
            # For v1, we use the built-in skill evaluator in EvalHarness
            variant = ExperimentVariant(
                variant_id=f"cand_{cand.candidate_id[:8]}",
                name=cand.name,
                target_type="skill",
                params={"module_path": self._install_temp(cand), "callable": "run_skill"}
            )
            
            # Simple eval case: check if it returns 'ok'
            eval_case = EvalCase(
                case_id=f"smoke_{cand.candidate_id[:8]}",
                description=cand.scope.get("description", "smoke test"),
                input_payload={},
                expected_keywords=["ok"]
            )
            
            eval_res = await self.eval_harness.run_suite(
                experiment_id="skill_evo",
                variant=variant,
                cases=[eval_case],
                target_type="skill"
            )
            
            score = eval_res.metrics.get("success_rate", 0.0)
            self._trace("candidate_evaluated", {
                "candidate_id": cand.candidate_id,
                "score": score
            }, trace_id)
            
            if score < 0.8:
                results.append({"id": cand.candidate_id, "status": "low_eval_score", "score": score})
                continue
                
            # 4. Promote/Land
            install_info = self.installer.install(cand)
            # Actually register in the main registry
            # (Note: SkillRegistry.register expects a SkillSpec, we might need to convert)
            from quentin.skills.schema import SkillSpec, SkillStatus
            spec = SkillSpec(
                id=cand.candidate_id,
                name=cand.name,
                domain=cand.domain,
                short_description=cand.scope.get("description", "")[:100],
                detailed_description=cand.scope.get("description", ""),
                status=SkillStatus.ACTIVE,
                implementation_module=f"quentin.skills.generated.{Path(install_info['module_path']).stem}",
                implementation_symbol="run_skill",
                parameters=cand.scope.get("parameters", {}),
                meta=cand.meta
            )
            self.registry.register(spec)
            
            results.append({"id": cand.candidate_id, "status": "promoted", "module": install_info["module_path"]})
            self._trace("candidate_promoted", {"skill_id": spec.id, "name": spec.name}, trace_id)

        self._trace("cycle_done", {"results": results}, trace_id)
        return {"trace_id": trace_id, "results": results}

    async def _mine_candidates(self, domain: str) -> List[SkillCandidate]:
        """
        Real trace mining: 
        1. Read events.jsonl
        2. Group by trace_id
        3. Identify successful tasks in the target domain
        4. Use SkillMiner to generate candidates
        """
        events_path = self.repo_root / "data" / "traces" / "events.jsonl"
        if not events_path.exists():
            return []
            
        # Group events by trace_id to reconstruct episodes
        episodes: Dict[str, List[Dict[str, Any]]] = {}
        try:
            with events_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        evt = json.loads(line)
                        tid = evt.get("trace_id")
                        if tid:
                            if tid not in episodes: episodes[tid] = []
                            episodes[tid].append(evt)
                    except: continue
        except Exception as e:
            logger.error(f"Failed to read events for mining: {e}")
            return []

        candidates = []
        for tid, evts in episodes.items():
            # Check if this episode was successful and matches domain
            is_success = any(e.get("event_type") == "execution" and e.get("payload", {}).get("raw", {}).get("success") is True for e in evts)
            task_evt = next((e for e in evts if e.get("event_type") == "task_received"), None)
            
            if is_success and task_evt:
                payload = task_evt.get("payload", {}).get("task", {})
                if payload.get("domain") == domain:
                    # Reconstruct CognitiveTask/Result objects for the miner
                    from quentin.cognitive.loop import CognitiveTask, CognitiveResult
                    task = CognitiveTask(**payload)
                    # Find the final execution result
                    exec_evt = [e for e in evts if e.get("event_type") == "execution"][-1]
                    raw_res = exec_evt.get("payload", {}).get("raw", {})
                    
                    # Convert events to TraceEvent objects
                    from quentin.traces.core import TraceEvent
                    trace_objs = [TraceEvent(**e) for e in evts]
                    
                    # Call the miner (synchronous method in SkillMiner)
                    # We wrap in run_in_executor if it were slow, but here it's likely fine
                    cand = self.miner.mine_from_task(
                        task=task,
                        result=None, # Miner handles if None
                        trace_events=trace_objs
                    )
                    if cand:
                        candidates.append(cand)
                        if len(candidates) >= 3: break # Limit per cycle
                        
        return candidates

    def _install_temp(self, cand: SkillCandidate) -> str:
        """
        Helper to install to a temporary location for eval.
        """
        import tempfile
        td = tempfile.gettempdir()
        path = Path(td) / f"temp_skill_{cand.candidate_id}.py"
        path.write_text(cand.implementation_code, encoding="utf-8")
        return str(path)

    def _trace(self, action: str, payload: Dict[str, Any], trace_id: str):
        self.trace_recorder.record_event(new_trace_event(
            trace_id=trace_id,
            event_type=TraceEventType.SKILL_EVOLUTION,
            payload={"action": action, **payload}
        ))

if __name__ == "__main__":
    # Smoke test
    evo = AutomatedSkillEvolution()
    asyncio.run(evo.run_cycle())
