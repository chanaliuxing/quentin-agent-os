from __future__ import annotations


def derive_module_context(*, modules: list[dict], failed_modules: list[dict], phase_id: str) -> str:
    if failed_modules:
        return str(failed_modules[0]["name"])
    if modules:
        return str(modules[0]["name"])
    return phase_id


def resolve_scope_modules(
    *,
    module_names: list[str],
    rollback_scope: list[str],
    affected_modules: list[str],
) -> list[str]:
    known = set(module_names)
    resolved: list[str] = []

    def append_if_known(name: str) -> None:
        if name in known and name not in resolved:
            resolved.append(name)

    for token in [*affected_modules, *rollback_scope]:
        value = str(token).strip()
        if not value:
            continue
        append_if_known(value)
        if value.startswith("module:"):
            append_if_known(value.split(":", 1)[1])
            continue
        if value.startswith("interface:"):
            interface_name = value.split(":", 1)[1]
            if "_to_" in interface_name:
                src, dst = interface_name.split("_to_", 1)
                append_if_known(src)
                append_if_known(dst)
            continue
        if value.startswith("app/"):
            parts = value.split("/")
            if len(parts) > 1:
                append_if_known(parts[1])
    return resolved


def select_modules_for_repair(
    *,
    modules: list[dict],
    failed_modules: list[dict],
    rollback_target_layer: str,
    rollback_scope: list[str],
    affected_modules: list[str],
) -> list[dict]:
    module_names = [module["name"] for module in modules]
    failed_names = [module["name"] for module in failed_modules]
    scoped_names = resolve_scope_modules(
        module_names=module_names,
        rollback_scope=rollback_scope,
        affected_modules=affected_modules,
    )
    if rollback_target_layer == "implementation":
        if failed_names:
            target_names = set(failed_names)
        elif scoped_names:
            target_names = set(scoped_names)
        else:
            target_names = set(module_names)
    else:
        target_names = set(scoped_names) if scoped_names else set(module_names)
    return [module for module in modules if module["name"] in target_names]
