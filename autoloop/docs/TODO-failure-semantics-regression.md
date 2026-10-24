# TODO - Failure Semantics Regression

## Scope
- 固化 failure_type -> recovery_action 的路由契约，避免同类错误在不同 run 漂移。
- 将 Dev/QA 缺产物、契约无效、runner 降级等失败统一进入 evidence 可统计字段。

## Implementation Checklist
- [x] 在 `run_agent_activity` 增加 Dev/QA `required_artifacts` presence gate。
- [x] 在 agent 失败返回中增加 `failure_type` / `failure_severity` / `missing_artifacts`。
- [x] 在 acceptance gate 输出增加 `failure_types` 聚合字段。
- [x] 在 `contract_validator` 明确产出结构化 `failure_type` 标签。
- [x] 在 workflow 失败诊断中优先吸收 acceptance `failure_types`。
- [x] 在 evidence schema/record 增加 `failure_type` 与 `missing_artifacts`。
- [x] 在 failure router policy 增加 `failure_type_actions` 与 `non_retryable_failure_types`。
- [x] 在 mock runner 补齐 required artifacts，避免 mock 集成误报。

## Remaining Work
- [x] 构建 failure taxonomy dashboard（按 failure_type/agent/phase 聚合）。
- [x] 将 recovery policy 暴露为只读诊断接口（便于 run 后解释）。
- [x] 增加 replay 数据集（固定失败样本）。
- [ ] 将 replay 数据集接入 nightly。
