from __future__ import annotations
from quentin.utils.time import now_iso, now_utc

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import os
import subprocess
import time
from pathlib import Path

from meta_agent.patchflow.models import PatchProposal as QueuePatchProposal
from meta_agent.patchflow.queue import PatchQueue
from meta_agent.patches.models import PatchProposal as CodePatchProposal
from meta_agent.patches.safe_applier import SafePatchApplier
from meta_agent.patches.store import PatchStore
from meta_agent.safety.checker import PatchSafetyChecker
from meta_agent.safety.result import SafetyCheckResult
from meta_agent.patches.diff_stats import compute_unified_diff_stats
from quentin.traces.core import JsonlTraceRecorder, TraceEventType, new_trace_event

from meta_agent.patchflow.store_bridge import sync_patch_store_to_patch_queue


trace = JsonlTraceRecorder(repo_root=".")


@dataclass(frozen=True)
class PatchFlowConfig:
    max_patches_per_cycle: int = 20
    auto_apply: bool = False
    run_tests: bool = False
    test_cmd: str = "pytest -q"
    test_timeout_sec: int = 300
    run_bench: bool = False
    bench_cmd: str = ""
    bench_timeout_sec: int = 600
    environment: str = "sandbox"
    patch_store_path: str = "data/patches.json"


class PatchFlowOrchestrator:
    """
    Minimal working PatchFlow pipeline:
    - enqueue patches from external tools (unified diff or raw)
    - evaluate with SafetyChecker (+ optional tests)
    - optional SafePatchApplier apply (feature-flag)
    - persist status updates back to PatchQueue
    """

    def __init__(
        self,
        *,
        queue: Optional[PatchQueue] = None,
        safety_checker: Optional[PatchSafetyChecker] = None,
        safe_applier: Optional[SafePatchApplier] = None,
        config: Optional[PatchFlowConfig] = None,
    ) -> None:
        self.queue = queue or PatchQueue()
        self.safety_checker = safety_checker or PatchSafetyChecker()
        self.safe_applier = safe_applier or SafePatchApplier(repo_root=".")
        self.patch_store = PatchStore(path=os.environ.get("META_AGENT_PATCH_STORE_PATH", "data/patches.json"))
        self.config = config or PatchFlowConfig(
            auto_apply=os.environ.get("META_AGENT_PATCHFLOW_AUTO_APPLY", "").strip().lower() in ("1", "true", "yes", "on"),
            run_tests=os.environ.get("META_AGENT_PATCHFLOW_RUN_TESTS", "").strip().lower() in ("1", "true", "yes", "on"),
            test_cmd=os.environ.get("META_AGENT_PATCHFLOW_TEST_CMD", "pytest -q"),
            test_timeout_sec=int(os.environ.get("META_AGENT_PATCHFLOW_TEST_TIMEOUT_SEC", "300")),
            run_bench=os.environ.get("META_AGENT_PATCHFLOW_RUN_BENCH", "").strip().lower() in ("1", "true", "yes", "on"),
            bench_cmd=os.environ.get("META_AGENT_PATCHFLOW_BENCH_CMD", ""),
            bench_timeout_sec=int(os.environ.get("META_AGENT_PATCHFLOW_BENCH_TIMEOUT_SEC", "600")),
            environment=os.environ.get("QUENTIN_ENV", os.environ.get("META_AGENT_ENV", "sandbox")),
            patch_store_path=os.environ.get("META_AGENT_PATCH_STORE_PATH", "data/patches.json"),
        )

    def enqueue_external_cli_patch(
        self,
        cli_result: Dict[str, Any],
        *,
        source: str,
        intent: str,
        reason: str,
        blueprint_context: str,
        targets: List[str],
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> QueuePatchProposal:
        fmt = str(cli_result.get("format") or "raw_text")
        diff = str(cli_result.get("diff") or "")
        raw = str(cli_result.get("raw") or "")
        body = {"diff": diff, "raw": raw} if fmt == "unified_diff" else {"raw": raw}

        proposal = QueuePatchProposal.new(
            source=source,
            kind="code",
            patch_format=fmt,
            targets=list(targets or []),
            body=body,
            intent=intent,
            reason=reason,
            blueprint_context=blueprint_context,
            metadata=dict(extra_meta or {}),
        )
        self.queue.append(proposal)
        trace.record_event(
            new_trace_event(
                trace_id=proposal.id,
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "patch_cli_enqueued", "proposal": proposal.to_dict()},
            )
        )
        return proposal

    def run_cycle(self, snapshot: Any = None, research_plan: Any = None) -> Dict[str, Any]:
        if os.environ.get("META_AGENT_PATCHFLOW_SYNC_STORE", "").strip().lower() in ("1", "true", "yes", "on"):
            try:
                sync_patch_store_to_patch_queue(
                    patch_store=self.patch_store,
                    patch_queue=self.queue,
                    max_to_enqueue=int(os.environ.get("META_AGENT_PATCHFLOW_SYNC_STORE_MAX", "20") or "20"),
                )
            except Exception:
                pass
        proposals = self.queue.load_all()
        processed: List[str] = []
        applied: List[str] = []
        blocked: List[str] = []
        rejected: List[str] = []

        pending = [p for p in proposals if p.status == "pending"][: self.config.max_patches_per_cycle]
        for proposal in pending:
            processed.append(proposal.id)
            outcome = self._process_single(proposal)
            if outcome == "applied":
                applied.append(proposal.id)
            elif outcome == "blocked":
                blocked.append(proposal.id)
            elif outcome == "rejected":
                rejected.append(proposal.id)

        # Persist updated statuses.
        self.queue.save_all(proposals)

        out = {
            "processed": len(processed),
            "applied": len(applied),
            "blocked": len(blocked),
            "rejected": len(rejected),
            "processed_ids": processed,
        }
        trace.record_event(
            new_trace_event(
                trace_id="patchflow",
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "patchflow_cycle_done", "result": out},
            )
        )
        return out

    def run_experiment_for_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Minimal hook for L3/L2 to request a benchmark/eval around a patch proposal.
        This implementation returns a structured config that can be fed into ResearchInterfaceV3.
        """
        exp = {
            "name": str(payload.get("name") or "patchflow_experiment"),
            "description": str(payload.get("description") or "PatchFlow experiment"),
            "target_type": str(payload.get("target_type") or "patch_test"),
            "metrics": list(payload.get("metrics") or ["score", "tests_passed_ratio", "risk_score"]),
            "variants": list(payload.get("variants") or []),
        }
        trace.record_event(
            new_trace_event(
                trace_id="patchflow-experiment",
                event_type=TraceEventType.DECISION,
                payload={"action": "patchflow_experiment_requested", "experiment": exp},
            )
        )
        return exp

    # --------------------------------------------------------------------- internals
    def _process_single(self, proposal: QueuePatchProposal) -> str:
        patch = self._to_code_patch(proposal)
        proposal.metadata["diff_stats"] = getattr(patch, "diff_stats", {})
        
        safety = self.safety_checker.check(patch)
        proposal.metadata["safety"] = {
            "allow_apply": safety.allow_apply,
            "requires_human_review": safety.requires_human_review,
            "reasons": list(safety.reasons or []),
            "meta": dict(safety.meta or {}),
        }

        trace.record_event(
            new_trace_event(
                trace_id=proposal.id,
                event_type=TraceEventType.SELF_PROGRAMMING,
                payload={"action": "patch_safety_checked", "proposal_id": proposal.id, "safety": proposal.metadata["safety"]},
            )
        )

        if self.config.run_tests:
            proposal.metadata["tests"] = self._run_tests()
            
        if self.config.run_bench:
            # We run bench BEFORE apply if we can (e.g. shadow mode or pure logic bench)
            # but usually bench runs in sandbox after apply. 
            # For now, let's run it if tests passed.
            if not self.config.run_tests or proposal.metadata.get("tests", {}).get("ok"):
                proposal.metadata["bench"] = self._run_bench()

        if not safety.allow_apply:
            proposal.status = "blocked"
            self._persist_report(proposal)
            return "blocked"

        # Enforce sandbox-only auto-apply.
        env = str(self.config.environment or "sandbox")
        requested_auto_apply = bool(self.config.auto_apply)
        auto_apply = requested_auto_apply and env == "sandbox"
        if requested_auto_apply and not auto_apply:
            proposal.metadata.setdefault("policy", {})
            proposal.metadata["policy"]["auto_apply_forced_off"] = True
            proposal.metadata["policy"]["reason"] = f"auto_apply is sandbox-only; environment={env}"

        if not auto_apply:
            proposal.status = "needs_review" if safety.requires_human_review else "approved"
            self._persist_report(proposal)
            return proposal.status

        # Auto-apply path: ALWAYS run tests after apply and rollback on failure.
        apply_result = self.safe_applier.apply_patch(patch)
        proposal.metadata["apply"] = {
            "allow_apply": apply_result.allow_apply,
            "requires_human_review": apply_result.requires_human_review,
            "reasons": list(apply_result.reasons or []),
            "meta": dict(apply_result.meta or {}),
        }

        if apply_result.allow_apply:
            # Persist applied patch for later inspection/rollback.
            try:
                self.patch_store.save_patch(patch)
            except Exception:
                pass
            tests = self._run_tests()
            proposal.metadata["tests_after_apply"] = tests
            
            if bool(tests.get("ok")) and self.config.run_bench:
                proposal.metadata["bench"] = self._run_bench()

            if not bool(tests.get("ok")):
                ok_rb = False
                try:
                    ok_rb = bool(self.safe_applier.rollback(patch))
                except Exception:
                    ok_rb = False
                proposal.metadata["rollback"] = {"attempted": True, "ok": ok_rb}
                proposal.status = "rolled_back" if ok_rb else "blocked"
                trace.record_event(
                    new_trace_event(
                        trace_id=proposal.id,
                        event_type=TraceEventType.SELF_PROGRAMMING,
                        payload={
                            "action": "patch_tests_failed_rollback",
                            "proposal_id": proposal.id,
                            "rollback_ok": ok_rb,
                        },
                    )
                )
                self._persist_report(proposal)
                return proposal.status

            proposal.status = "applied"
            self._persist_report(proposal)
            return "applied"

        proposal.status = "blocked"
        self._persist_report(proposal)
        return "blocked"

    def _run_bench(self) -> Dict[str, Any]:
        if not self.config.bench_cmd:
            return {"ok": True, "skipped": True}
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                self.config.bench_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.config.bench_timeout_sec,
                check=False,
            )
            dur = time.perf_counter() - start
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "duration_sec": dur,
                "stdout_preview": proc.stdout.decode("utf-8", errors="ignore")[:4000],
                "stderr_preview": proc.stderr.decode("utf-8", errors="ignore")[:4000],
                "cmd": self.config.bench_cmd,
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": repr(e), "cmd": self.config.bench_cmd}

    def _persist_report(self, proposal: QueuePatchProposal) -> None:
        import json
        from datetime import datetime
        repo_root = Path(".").resolve()
        out_dir = repo_root / "data" / "patchflow_reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{proposal.id}.json"

        # Extract structured metrics from metadata
        report = {
            "patchflow_id": proposal.id,
            "status": proposal.status,
            "targets": list(proposal.targets or []),
            "safety": proposal.metadata.get("safety"),
            "tests": proposal.metadata.get("tests") or proposal.metadata.get("tests_after_apply"),
            "bench": proposal.metadata.get("bench"),
            "apply": proposal.metadata.get("apply"),
            "rollback": proposal.metadata.get("rollback"),
            "policy": proposal.metadata.get("policy"),
            "created_at": proposal.created_at,
            "processed_at": now_iso(),
        }
        
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _to_code_patch(proposal: QueuePatchProposal) -> CodePatchProposal:
        diff = ""
        if proposal.patch_format == "unified_diff":
            diff = str((proposal.body or {}).get("diff") or "")
        
        meta = dict(proposal.metadata or {})

        # P2: Robust diff stats calculation (handle non-unified diffs/raw text)
        diff_stats = {}
        if diff.strip():
            diff_stats = compute_unified_diff_stats(diff, targets=list(proposal.targets or []))
        
        # Fallback: if we have raw content but no diff stats, estimate from line count
        if not diff_stats and proposal.targets:
            raw = str((proposal.body or {}).get("raw") or "")
            if raw.strip():
                line_count = len(raw.splitlines())
                # Assume all lines are added if it's a raw file replacement
                diff_stats = {t: {"added": line_count, "removed": 0} for t in proposal.targets}

        return CodePatchProposal(
            id=proposal.id,
            target_files=list(proposal.targets or []),
            diff=diff,
            intent=str(proposal.intent or ""),
            status=str(proposal.status or "pending"),
            metadata=meta,
            eval_metrics={},
            diff_stats=diff_stats,
        )

    def _run_tests(self) -> Dict[str, Any]:
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                self.config.test_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.config.test_timeout_sec,
                check=False,
            )
            dur = time.perf_counter() - start
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "duration_sec": dur,
                "stdout_preview": proc.stdout.decode("utf-8", errors="ignore")[:4000],
                "stderr_preview": proc.stderr.decode("utf-8", errors="ignore")[:4000],
                "cmd": self.config.test_cmd,
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": repr(e), "cmd": self.config.test_cmd}
