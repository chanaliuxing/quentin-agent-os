# AutoLoop Docs

本目录收敛 AutoLoop 下一阶段的实施文档，目标是把系统从“会话驱动脚本”升级为“可恢复 workflow + 可验证代码变更流水线”。

## Document Map

- `RFC-001-convergence-control.md`
  - 收敛控制系统总 RFC
  - 定义分层架构、状态机、数据契约、证据链、反作弊策略
- `PLAN-convergence-rollout.md`
  - 分阶段实施计划
  - 定义每个 phase 的目标、输入、输出、依赖、风险
- `TODO-convergence-rollout.md`
  - 可分配给 agent 的执行清单
  - 每项任务都绑定目标模块、输出物、完成定义
- `TEST-convergence-gates.md`
  - 测试策略与用例矩阵
  - 覆盖 unit / integration / replay / anti-gaming / acceptance
- `ACCEPTANCE-convergence-gates.md`
  - 验收标准
  - 定义每个 phase 进入下一阶段的硬门禁

## Usage

推荐按以下顺序使用：

1. 先读 `RFC-001-convergence-control.md`
2. 再按 `PLAN-convergence-rollout.md` 确认 phase
3. 用 `TODO-convergence-rollout.md` 派发模块任务
4. 按 `TEST-convergence-gates.md` 实施验证
5. 用 `ACCEPTANCE-convergence-gates.md` 做 phase gate
