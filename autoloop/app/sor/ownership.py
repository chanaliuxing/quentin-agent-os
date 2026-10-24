from __future__ import annotations

from pathlib import Path

from app.models import ProjectSpec


def module_ids_from_scope_tokens(*, spec: ProjectSpec, scope_tokens: list[str]) -> list[str]:
    known_modules = {module.module_id for module in spec.modules}
    resolved: list[str] = []

    def append_if_known(module_id: str) -> None:
        if module_id in known_modules and module_id not in resolved:
            resolved.append(module_id)

    for token in scope_tokens:
        value = str(token).strip()
        if not value:
            continue
        append_if_known(value)
        if value.startswith("module:"):
            append_if_known(value.split(":", 1)[1])
            continue
        if value.startswith("interface:"):
            interface_id = value.split(":", 1)[1]
            for interface in spec.interfaces:
                if interface.interface_id != interface_id:
                    continue
                append_if_known(interface.producer_module)
                for consumer in interface.consumer_modules:
                    append_if_known(consumer)
            continue
        if value.startswith("app/"):
            for rule in spec.ownership:
                root = rule.path_glob.split("*", 1)[0]
                if root and Path(value).as_posix().startswith(root):
                    append_if_known(rule.module_id)
    return resolved
