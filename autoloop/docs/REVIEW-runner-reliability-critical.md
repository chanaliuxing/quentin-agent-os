# Review + Critical · Runner Reliability (Codex)

## Observed Reality
- Codex runner 在真实执行中出现 `state db ... migration ... falling_back`，不是噪声，已导致主循环挂起风险。
- 当前门禁能拦截 `contract_validator` 失败，但无法把 `state_db` 退化显式上报到 runner 维度指标。
- 现有执行链缺少标准化降级路径（resume -> stateless -> ephemeral）和前置探针。

## Critical Gaps
1. **Resume 健康探针缺失**：无启动前降级判断，坏 session 会直接进入主路径。
2. **降级执行链不完整**：单模式执行失败时，无法自动切换更稳模式。
3. **超时治理不够硬**：需要进程组级杀死，防止孤儿进程阻塞下一轮。
4. **门禁缺“state_db_clean”**：`falling_back` 未纳入契约失败判定。
5. **可观测缺口**：缺 `state_db_fallback_count/session_degraded_count/timeout_count`。

## Remediation Principle
- 先保收敛：优先让循环可终止、可降级、可追溯。
- 再提效果：在稳定执行面基础上优化业务产出质量。
- 避免“探针本身造成不稳定”：默认 `ephemeral-first`，probe 仅用于专项诊断。
