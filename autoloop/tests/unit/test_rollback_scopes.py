from app.rollback.scopes import derive_module_context, resolve_scope_modules, select_modules_for_repair


def test_resolve_scope_modules_supports_multiple_ref_types():
    resolved = resolve_scope_modules(
        module_names=["planner", "executor", "memory"],
        rollback_scope=["module:planner", "interface:planner_to_executor", "app/memory/store.py"],
        affected_modules=[],
    )
    assert resolved == ["planner", "executor", "memory"]


def test_select_modules_for_implementation_prefers_failed():
    modules = [{"name": "planner"}, {"name": "executor"}]
    failed_modules = [{"name": "executor"}]
    selected = select_modules_for_repair(
        modules=modules,
        failed_modules=failed_modules,
        rollback_target_layer="implementation",
        rollback_scope=[],
        affected_modules=[],
    )
    assert selected == failed_modules


def test_select_modules_for_contract_uses_scope():
    modules = [{"name": "planner"}, {"name": "executor"}, {"name": "memory"}]
    selected = select_modules_for_repair(
        modules=modules,
        failed_modules=[],
        rollback_target_layer="contract",
        rollback_scope=["module:planner", "app/memory/store.py"],
        affected_modules=[],
    )
    assert selected == [{"name": "planner"}, {"name": "memory"}]


def test_derive_module_context_prefers_failed_then_first():
    assert (
        derive_module_context(
            modules=[{"name": "planner"}, {"name": "executor"}],
            failed_modules=[{"name": "executor"}],
            phase_id="phase_01",
        )
        == "executor"
    )
    assert (
        derive_module_context(
            modules=[{"name": "planner"}, {"name": "executor"}],
            failed_modules=[],
            phase_id="phase_01",
        )
        == "planner"
    )
