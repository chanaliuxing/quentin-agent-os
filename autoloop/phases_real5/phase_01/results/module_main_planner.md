{
  "contract_version": "1.0",
  "generated_at": "2026-03-07T11:20:41.545254",
  "module_name": "module_main",
  "plan_summary": "Implement module_main as the phase_01 dual-track orchestration core: decompose incoming tasks into executable steps, prefer qualified MCP tools by capability and reliability, fall back to self-programming on tool miss/failure, and emit structured memory/reflection outputs for next-loop investment decisions.",
  "tasks": [
    "Define and validate core domain models for track selection and execution outputs (AcquisitionTrack, ToolCapability, ExecutionStep, StepResult, ModuleMainResult) with strict schema constraints.",
    "Implement deterministic task decomposition that converts free-form task text into ordered execution steps with inferred required capabilities.",
    "Implement MCP tool selection logic using capability normalization and minimum reliability threshold, with deterministic tie-breaking for equally qualified tools.",
    "Implement orchestrator run flow that executes MCP first when eligible, falls back to self-programming on selection miss/tool failure/tool non-success, and normalizes executor outputs.",
    "Generate memory update entries, reflection summary, and next investment area recommendation from step-level execution outcomes.",
    "Expose module_main public API through package exports for integration with graph/temporal pipeline callers.",
    "Add and pass targeted unit and integration tests for dual-track routing, fallback/error handling, deterministic selection behavior, and result contract integrity."
  ],
  "acceptance_criteria": [
    "Given non-empty task input, module_main returns a valid ModuleMainResult with non-empty task, steps, step_results, reflection, and next_investment_area fields.",
    "For a step with matching MCP capability and reliability >= threshold, orchestrator executes MCP first and records track as mcp_tool when MCP succeeds.",
    "When MCP tool is unavailable, below threshold, raises exception, or returns success=false, orchestrator falls back to self-programming and records track as self_programming.",
    "If both executors fail for a step, orchestrator returns a non-crashing StepResult with success=false and machine-readable failure output.",
    "Tool selection is deterministic for identical candidates and respects normalized capability matching and reliability ordering.",
    "Reflection and next investment recommendation are derived from aggregated step outcomes and correctly distinguish tool-learning vs self-programming investment signals.",
    "Contract validation for planner/dev/qa outputs remains compatible with contract_version 1.0 and module_main artifacts.",
    "Test suite includes both unit and integration coverage for module_main and passes required checks for the phase acceptance gate."
  ]
}
