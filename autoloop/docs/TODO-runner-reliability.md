# TODO · Runner Reliability Hardening

- [x] 增加 Codex 前置探针（检测 `state db` 退化）。
- [x] 增加执行降级链：`resume -> standard -> ephemeral`。
- [x] 默认切换为 `ephemeral-first`，仅在健康时尝试 resume。
- [x] 默认关闭 probe，避免 probe 本身引入额外会话不稳定。
- [x] Codex 默认重试次数降为 0，优先快速失败并进入治理恢复。
- [x] 探针失败或退化信号触发 runner 健康指标累积。
- [x] 子进程超时升级为进程组级 kill。
- [x] 每次 codex 调用应用硬超时预算（防止单次长卡死）。
- [x] 增加 agent 总执行预算（含重试）上限，避免长时间卡在单 agent。
- [x] 契约门禁新增 `state_db` 退化检测并拒绝通过。
- [x] 增加 runner 健康指标持久化（`runtime/metrics/runner_health.json`）。
- [x] 系统指标报告聚合 runner 健康状态。
- [x] 增加单元测试覆盖探针降级、门禁拒绝、指标写入。
