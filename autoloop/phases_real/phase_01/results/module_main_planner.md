{
  "contract_version": "1.0",
  "generated_at": "2026-03-07T08:35:31Z",
  "module_name": "module_main",
  "plan_summary": "Implement phase_01 module_main around the v3.1 dual-track architecture: route capability gaps to MCP tools first, fall back to self-programming when tools are unavailable or unfit, and ship a testable core loop with observability and safety constraints.",
  "tasks": [
    "Define module_main architecture boundaries for task intake, planner/executor loop, tool-learning layer, and self-programming entry points.",
    "Implement dual-track decision policy that evaluates each capability gap and selects MCP tool path vs self-programming path with explicit scoring and fallback rules.",
    "Build MCP integration flow: tool discovery metadata ingestion, capability normalization, invocation adapter, and internal tool registry updates.",
    "Implement self-programming fallback orchestration that triggers only when MCP path is unavailable, low-confidence, or policy-blocked.",
    "Add execution logging and trace fields for decisions, chosen path, tool outcomes, and fallback reasons to support replay and review.",
    "Add safety and guardrails: path allowlists, forbidden path checks, rollback handling, and failure propagation compatible with phase contracts.",
    "Create/extend unit tests for decision policy, MCP adapter behavior, fallback transitions, and guardrail enforcement.",
    "Create/extend integration tests covering end-to-end module_main flow for MCP-success and MCP-to-self-programming fallback scenarios.",
    "Produce artifact output for phase_01 module_main result and ensure contract-validator compatibility."
  ],
  "acceptance_criteria": [
    "Dual-track policy deterministically selects MCP-first when suitable tools exist and self-programming fallback when suitability thresholds are not met.",
    "MCP discovery and invocation complete successfully with normalized capability records and stable adapter interfaces.",
    "Fallback to self-programming is automatically triggered with explicit reason codes and no silent path switching.",
    "Structured execution logs contain task id, decision inputs, selected track, outcome status, and rollback markers when failures occur.",
    "All file operations and runtime actions respect allowed/forbidden path constraints and fail closed on violations.",
    "Required unit and integration test suites pass for module_main changes.",
    "Required artifact `artifact_phase_01_module_main_result` is generated and passes contract validation.",
    "Failure conditions activate rollback behavior as defined by acceptance spec without leaving partial unsafe state."
  ]
}
