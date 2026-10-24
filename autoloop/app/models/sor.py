from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IoRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    schema_ref: str = Field(min_length=1)


class ModuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    inputs: list[IoRef] = Field(default_factory=list)
    outputs: list[IoRef] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class InterfaceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface_id: str = Field(min_length=1)
    producer_module: str = Field(min_length=1)
    consumer_modules: list[str] = Field(default_factory=list)
    schema_ref: str = Field(min_length=1)


class FileOwnershipRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path_glob: str = Field(min_length=1)
    owner_role: str = Field(min_length=1)
    module_id: str = Field(min_length=1)


class GatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_gates: list[str] = Field(default_factory=list)
    module_gates: list[str] = Field(default_factory=list)
    score_threshold: float = Field(ge=0.0, le=1.0)


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)


class WorkflowTopology(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[str] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_edges(self) -> "WorkflowTopology":
        node_set = set(self.nodes)
        if len(node_set) != len(self.nodes):
            raise ValueError("workflow nodes must be unique")
        for edge in self.edges:
            if edge.src not in node_set or edge.dst not in node_set:
                raise ValueError("workflow edges must reference declared nodes")
        return self


class ModuleExecutionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    sor_refs: list[str] = Field(default_factory=list)
    writable_paths: list[str] = Field(default_factory=list)
    input_artifact_refs: list[str] = Field(default_factory=list)
    expected_output_refs: list[str] = Field(default_factory=list)
    gate_expectations: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class PhaseExecutionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_id: str = Field(min_length=1)
    module_views: list[ModuleExecutionView] = Field(default_factory=list)


class ProjectSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    contract_version: str = Field(min_length=1)
    modules: list[ModuleSpec]
    interfaces: list[InterfaceSpec]
    ownership: list[FileOwnershipRule]
    gate_policy: GatePolicy
    workflow_topology: WorkflowTopology

    @model_validator(mode="after")
    def validate_cross_references(self) -> "ProjectSpec":
        module_ids = [module.module_id for module in self.modules]
        module_set = set(module_ids)
        if len(module_ids) != len(module_set):
            raise ValueError("duplicate module_id is not allowed")

        for module in self.modules:
            missing_dependencies = [dependency for dependency in module.depends_on if dependency not in module_set]
            if missing_dependencies:
                raise ValueError(
                    f"module {module.module_id} depends on unknown modules: {', '.join(missing_dependencies)}"
                )

        for interface in self.interfaces:
            if interface.producer_module not in module_set:
                raise ValueError(f"interface {interface.interface_id} has unknown producer module")
            invalid_consumers = [
                consumer for consumer in interface.consumer_modules if consumer not in module_set
            ]
            if invalid_consumers:
                raise ValueError(
                    f"interface {interface.interface_id} has unknown consumer modules: {', '.join(invalid_consumers)}"
                )

        for rule in self.ownership:
            if rule.module_id not in module_set:
                raise ValueError(f"ownership rule {rule.path_glob} references unknown module")

        return self
