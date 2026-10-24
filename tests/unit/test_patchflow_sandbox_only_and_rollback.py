from dataclasses import dataclass
from typing import Any
from dataclasses import field


@dataclass
class _FakeApplyResult:
    allow_apply: bool = True
    requires_human_review: bool = False
    reasons: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


class _FakeSafeApplier:
    def __init__(self):
        self.applied = 0
        self.rolled_back = 0

    def apply_patch(self, patch: Any):
        self.applied += 1
        # Simulate backup presence for rollback.
        patch.metadata.setdefault("backups", {"dummy": "dummy.bak"})
        return _FakeApplyResult(reasons=[], meta={})

    def rollback(self, patch: Any) -> bool:
        self.rolled_back += 1
        return True


def test_patchflow_auto_apply_forced_off_outside_sandbox(tmp_path, monkeypatch):
    from meta_agent.patchflow.orchestrator import PatchFlowOrchestrator, PatchFlowConfig
    from meta_agent.patchflow.queue import PatchQueue
    from meta_agent.patchflow.models import PatchProposal

    q = PatchQueue(path=tmp_path / "q.jsonl")
    prop = PatchProposal.new(
        source="unit",
        kind="code",
        patch_format="unified_diff",
        targets=["quentin/mutable/patchflow_test.txt"],
        body={"diff": ""},  # keep diff empty; safety checker uses path allowlist
        intent="noop",
        reason="test",
        blueprint_context="",
    )
    q.append(prop)

    orch = PatchFlowOrchestrator(
        queue=q,
        safe_applier=_FakeSafeApplier(),
        config=PatchFlowConfig(auto_apply=True, run_tests=False, environment="prod"),
    )
    out = orch.run_cycle()
    assert out["processed"] == 1
    saved = q.load_all()
    assert saved[0].status in ("approved", "needs_review")
    assert saved[0].metadata.get("policy", {}).get("auto_apply_forced_off") is True


def test_patchflow_rollback_on_test_failure_in_sandbox(tmp_path):
    from meta_agent.patchflow.orchestrator import PatchFlowOrchestrator, PatchFlowConfig
    from meta_agent.patchflow.queue import PatchQueue
    from meta_agent.patchflow.models import PatchProposal

    class _Orch(PatchFlowOrchestrator):
        def _run_tests(self):
            return {"ok": False, "returncode": 1, "cmd": "fake"}

    q = PatchQueue(path=tmp_path / "q.jsonl")
    prop = PatchProposal.new(
        source="unit",
        kind="code",
        patch_format="unified_diff",
        targets=["quentin/mutable/patchflow_test.txt"],
        body={"diff": ""},  # no apply happens to filesystem; safe applier is fake
        intent="noop",
        reason="test",
        blueprint_context="",
    )
    q.append(prop)

    fake = _FakeSafeApplier()
    orch = _Orch(
        queue=q,
        safe_applier=fake,
        config=PatchFlowConfig(auto_apply=True, run_tests=False, environment="sandbox"),
    )
    out = orch.run_cycle()
    assert out["processed"] == 1
    saved = q.load_all()
    assert saved[0].status == "rolled_back"
    assert fake.applied == 1
    assert fake.rolled_back == 1
