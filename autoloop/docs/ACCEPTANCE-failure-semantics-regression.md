# ACCEPTANCE - Failure Semantics Regression

## Contract
- 同一个 `failure_type` 在相同输入下必须给出稳定 `recommended_action`。
- 所有 rejected run 必须可在 evidence 中追溯：
  - `first_failure_stage`
  - `failure_type`
  - `failure_signature`
  - `owner_agent`
  - `missing_artifacts`（若适用）

## Pass Criteria
- `ci_gate` 全通过。
- `test_temporal_mock_workflow` 通过。
- 失败样本 run 不出现 `No result file found`。
- `MISSING_*` 相关失败触发 `replan_from_spec`，不再盲重试。
- `acceptance gate` 输出包含 `failure_types`，并与 evidence `failure_type` 对齐。

## Evidence Checks
- `runtime/evidence/**/evidence_*.json` 含新增字段且符合 schema。
- `phase_report.md` 的失败总结可复盘，不依赖人工读 runner 原始 stderr。

## Rollback Rule
- 若新增策略导致 `happy-path` 通过率回退或 workflow 进入不收敛重试：
  - 回滚 `failure_router_policy.json` 新增映射；
  - 保留 evidence 字段扩展（向后兼容）。
