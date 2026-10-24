# TODO · Auto-Review Default Control Flow

## Scope
- 将 `auto-review` 接入默认主流程（无需手动触发）。
- 将 human-review 回填信息升级为结构化约束并注入任务。
- 增加回放回归测试包，防止策略回退。

## Implementation TODO
- [x] 在配置中新增自动审核开关与置信阈值。
- [x] 在 `run temporal` 流程中检测 `human_review_required` 后自动执行审核决策。
- [x] 自动审核 `approved` 且达到阈值时，自动恢复执行（单次保护，防止无限递归）。
- [x] 自动审核 `rejected` 或低置信时，保留人工处理钩子并输出风险信号。
- [x] 将 resolution 中的 `failure_signature/first_failure_stage/repair_template` 转为 machine-readable 任务约束。
- [x] 任务模板（planner/reviewer/dev/qa）统一注入结构化修复约束块。

## Test Checklist
- [x] 单测：默认流程命中 human-review hook 时自动调用 auto-review。
- [x] 单测：auto-review `approved` + 高置信触发自动 resume；低置信不触发。
- [x] 单测：任务文件包含 `Enforced Repair Constraints` 结构化块。
- [x] 回放测试：历史失败样本（缺测试、合同失败、结构风险）全部稳定判定为 reject。
- [x] 回放测试：干净通过样本稳定判定 approve。
- [x] 全量测试通过。

## Acceptance Criteria
- [x] 用户执行 `run --mode temporal` 时，human-review 场景默认自动决策，不再必须人工命令。
- [x] 自动决策结果可追溯：风险信号、置信度、修复模板均落盘。
- [x] 修复约束以结构化数据注入任务，不依赖自由文本理解。
- [x] 重跑链路可控：同一轮自动恢复最多 1 次，避免死循环。
- [x] 回归包可复现实例并阻止策略退化。
