{
  "contract_version": "1.0",
  "generated_at": "2026-03-07T08:36:52Z",
  "module_name": "module_main",
  "verdict": "needs_revision",
  "findings": [
    "The planner output does not define a concrete write target/mechanism for required artifact `artifact_phase_01_module_main_result`; this must be explicit and remain outside forbidden `phases/**` paths.",
    "Implementation tasks remain architecture-level and do not map to concrete target files/modules under allowed paths (`app/module_main/**`, `app/**/*.py`), which weakens execution clarity for dev handoff."
  ]
}
