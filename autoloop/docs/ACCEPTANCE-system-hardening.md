# Acceptance & Test Gates · System Hardening

## Gate 1: Contract Integrity
- Command: `pytest tests/unit/test_output_contracts.py -q`
- Pass rule:
  - reviewer `needs_revision` without `finding_codes` must fail validation.

## Gate 2: Default Auto-Review Flow
- Command: `pytest tests/unit/test_auto_review_default_flow.py -q`
- Pass rule:
  - approved + high confidence -> auto-resume path called.
  - rejected/low confidence -> no auto-resume.

## Gate 3: Recovery Injection
- Command: `pytest tests/unit/test_generate_phase_tasks_contracts.py tests/unit/test_human_review_queue.py -q`
- Pass rule:
  - planner/dev/reviewer/qa tasks contain `Enforced Repair Constraints` block when resolution exists.

## Gate 4: Replay Regression
- Command: `pytest tests/replay/test_auto_review_replay_pack.py -q`
- Pass rule:
  - known failure patterns remain `rejected`.
  - clean pass pattern remains `approved`.

## Gate 5: Policy Calibration & Router
- Command: `pytest tests/unit/test_policy_calibration.py tests/unit/test_failure_router.py -q`
- Pass rule:
  - calibration 产出 `policy_tuning_dataset.json` 与 `auto_review_policy.calibrated.json`。
  - failure router 对结构风险与重复失败执行正确路由。

## Gate 6: Full Regression
- Command: `pytest -q`
- Pass rule:
  - no historical test regression.

## Runtime Acceptance
- Command:
  - `python -m app.main run ./blueprint.md --mode temporal --profile dev`
- Pass rule:
  - failure path must produce `human_review_required` + evidence diagnostics.
  - default auto-review must execute and log decision/risk signals.

## Exit Criteria
- 全部 Gate 通过 + 至少 1 次真实 runtime 验证通过。
