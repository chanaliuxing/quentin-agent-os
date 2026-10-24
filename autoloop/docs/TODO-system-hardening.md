# TODO · System Hardening Execution

## A. Policy & Control
- [x] 固化 `policy_version` 到所有 auto-review resolution。
- [x] 默认 `run temporal` 自动触发 auto-review 决策。
- [x] auto-resume 设置全局上限，防止递归重跑。
- [x] 同签名失败熔断升级到 `replan_from_spec`。
- [x] 引入 governance-review agent 自动处理 human-review hook（可自动恢复）。

## B. Contract Governance
- [x] reviewer `needs_revision` 强制 `finding_codes`（已启用，需持续回归）。
- [x] `required_tests` 与 gate 成功状态映射可配置化（policy 驱动）。
- [x] contract validator 失败信息结构化（role + field + reason）。

## C. Recovery Injection
- [x] resolution 包含 `failure_signature`、`first_failure_stage`、`repair_template`。
- [x] task 模板统一注入 `Enforced Repair Constraints` JSON。
- [x] agent 输出中回写“约束已消费”标记（可审计）。

## D. Observability
- [x] dashboard 增加 failure owner/signature 趋势。
- [x] doctor 输出最近 3 次失败签名聚合。
- [x] hook/resolution/evidence 全链路 trace_id 关联。

## E. Replay & CI
- [x] `tests/replay` 样本扩展并持续维护（结构风险、评测失败、契约失败、恢复成功）。
- [x] 将 replay pack 加入 CI 必跑门禁（`scripts/ci_gate.sh`）。
- [x] 记录基线指标并输出周对比（`system-metrics-report` + `delta_vs_previous`）。

## Definition of Done
- [x] 全量测试 + replay pack 全绿。
- [x] 真实 run 至少 2 轮，自动审决策与 evidence 可追溯。
- [x] 不出现同签名无限 retry。
