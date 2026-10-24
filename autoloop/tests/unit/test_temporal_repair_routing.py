from app.models import RepairDecision, RollbackTargetLayer
from app.rollback.scopes import derive_module_context, resolve_scope_modules
from app.temporal.workflow import (
    _execute_temporal_repair,
    _select_modules_for_repair,
    _should_stop_on_halt,
)


def build_repair_decision(
    *,
    target: RollbackTargetLayer,
    scope: list[str],
) -> RepairDecision:
    return RepairDecision(
        run_id="run_01",
        phase_id="phase_01",
        failure_class="implementation_bug",
        rollback_target_layer=target,
        rollback_scope=scope,
        affected_modules=scope,
        required_agents=["dev", "qa"],
        repair_strategy="rerun affected modules",
        confidence=0.8,
    )


def test_select_modules_for_implementation_prefers_failed_modules():
    modules = [{"name": "a"}, {"name": "b"}]
    failed = [{"name": "b"}]
    decision = build_repair_decision(
        target=RollbackTargetLayer.IMPLEMENTATION,
        scope=["a", "b"],
    )
    selected = _select_modules_for_repair(
        run_id="run_01",
        modules=modules,
        failed_modules=failed,
        repair_decision=decision,
    )
    assert selected == failed


def test_select_modules_for_contract_uses_scope_subset():
    modules = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    decision = build_repair_decision(
        target=RollbackTargetLayer.CONTRACT,
        scope=["a", "c"],
    )
    selected = _select_modules_for_repair(
        run_id="run_01",
        modules=modules,
        failed_modules=[],
        repair_decision=decision,
    )
    assert selected == [{"name": "a"}, {"name": "c"}]


def test_select_modules_falls_back_to_all_on_empty_scope_match():
    modules = [{"name": "a"}, {"name": "b"}]
    decision = build_repair_decision(
        target=RollbackTargetLayer.SPEC,
        scope=["x"],
    )
    selected = _select_modules_for_repair(
        run_id="run_01",
        modules=modules,
        failed_modules=[],
        repair_decision=decision,
    )
    assert selected == modules


def test_execute_temporal_repair_records_checkpoint_for_implementation():
    modules = [{"name": "a"}, {"name": "b"}]
    failed = [{"name": "b"}]
    decision = build_repair_decision(
        target=RollbackTargetLayer.IMPLEMENTATION,
        scope=["b"],
    )
    pending_modules, execution = _execute_temporal_repair(
        project_id="run_01",
        phase_id="phase_01",
        modules=modules,
        failed_modules=failed,
        repair_decision=decision,
    )
    assert pending_modules == failed
    assert execution["next_action"] == "dispatch_dev"
    assert "phase_01_checkpoint" in execution["artifacts"]
    assert execution["execution"]["execution_status"] == "executed"


def test_execute_temporal_repair_routes_spec_to_replan():
    modules = [{"name": "a"}, {"name": "b"}]
    decision = build_repair_decision(
        target=RollbackTargetLayer.SPEC,
        scope=["a"],
    )
    pending_modules, execution = _execute_temporal_repair(
        project_id="run_01",
        phase_id="phase_01",
        modules=modules,
        failed_modules=[],
        repair_decision=decision,
    )
    assert pending_modules == modules
    assert execution["next_action"] == "lead_plan"


def test_should_stop_on_halt_for_implementation_repairs():
    decision = build_repair_decision(
        target=RollbackTargetLayer.IMPLEMENTATION,
        scope=["a"],
    )
    assert _should_stop_on_halt(decision) is True


def test_should_continue_on_halt_for_spec_contract_task_repairs():
    for target in [RollbackTargetLayer.SPEC, RollbackTargetLayer.CONTRACT, RollbackTargetLayer.TASK]:
        decision = build_repair_decision(target=target, scope=["a"])
        assert _should_stop_on_halt(decision) is False


def test_resolve_scope_modules_from_module_interface_and_path_refs():
    resolved = resolve_scope_modules(
        module_names=["planner", "executor", "memory"],
        rollback_scope=[
            "module:planner",
            "interface:planner_to_executor",
            "app/memory/store.py",
            "unknown",
        ],
        affected_modules=[],
    )
    assert resolved == ["planner", "executor", "memory"]


def test_select_modules_for_contract_uses_resolved_scope_refs():
    modules = [{"name": "planner"}, {"name": "executor"}, {"name": "memory"}]
    decision = build_repair_decision(
        target=RollbackTargetLayer.CONTRACT,
        scope=["interface:planner_to_executor", "app/memory/store.py"],
    )
    selected = _select_modules_for_repair(
        run_id="run_01",
        modules=modules,
        failed_modules=[],
        repair_decision=decision,
    )
    assert selected == [{"name": "planner"}, {"name": "executor"}, {"name": "memory"}]


def test_derive_module_context_prefers_failed_modules_then_first_module():
    module_id = derive_module_context(
        modules=[{"name": "planner"}, {"name": "executor"}],
        failed_modules=[{"name": "executor"}],
        phase_id="phase_01",
    )
    assert module_id == "executor"

    module_id = derive_module_context(
        modules=[{"name": "planner"}, {"name": "executor"}],
        failed_modules=[],
        phase_id="phase_01",
    )
    assert module_id == "planner"
