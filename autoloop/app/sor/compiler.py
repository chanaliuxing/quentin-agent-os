from __future__ import annotations

from app.models import ModuleExecutionView, PhaseExecutionView, ProjectSpec


class SorCompiler:
    def compile_module_view(self, spec: ProjectSpec, module_id: str) -> ModuleExecutionView:
        modules = {module.module_id: module for module in spec.modules}
        if module_id not in modules:
            raise ValueError(f"unknown module_id: {module_id}")

        module = modules[module_id]
        writable_paths = [
            rule.path_glob
            for rule in spec.ownership
            if rule.module_id == module_id
        ]
        sor_refs = [
            f"project:{spec.project_id}",
            f"module:{module.module_id}",
            *[f"interface:{interface.interface_id}" for interface in spec.interfaces if interface.producer_module == module_id or module_id in interface.consumer_modules],
        ]
        input_artifact_refs = [f"input:{item.name}" for item in module.inputs]
        expected_output_refs = [f"output:{item.name}" for item in module.outputs]
        gate_expectations = [*spec.gate_policy.phase_gates, *spec.gate_policy.module_gates]
        return ModuleExecutionView(
            module_id=module.module_id,
            summary=module.summary,
            depends_on=module.depends_on,
            sor_refs=sor_refs,
            writable_paths=writable_paths,
            input_artifact_refs=input_artifact_refs,
            expected_output_refs=expected_output_refs,
            gate_expectations=gate_expectations,
            acceptance_criteria=module.acceptance_criteria,
        )

    def compile_phase_view(self, spec: ProjectSpec, phase_id: str) -> PhaseExecutionView:
        return PhaseExecutionView(
            phase_id=phase_id,
            module_views=[
                self.compile_module_view(spec, module.module_id)
                for module in spec.modules
            ],
        )
