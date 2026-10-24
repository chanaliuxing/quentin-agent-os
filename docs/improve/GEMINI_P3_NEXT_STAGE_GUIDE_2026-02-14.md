# Gemini P3 Next Stage Guide

进入 P3 阶段。你（Gemini）现在要做的是“生产化收口与治理闭环”，不是继续加功能点。重点是可运营、可回滚、可观测、可审计。

阶段目标：
1. 把 P0/P1/P2 串成稳定发布路径（sandbox -> staging -> prod）
2. 建立统一指标与告警
3. 建立安全审计与故障演练
4. 输出可执行 Runbook

硬约束：
- 所有新逻辑必须可通过 feature flag 一键关闭。
- 不允许删除 legacy path。
- 任何高风险改动必须带集成测试和回滚说明。
- 每完成一个子项都要给“证据文件 + 测试输出摘要”。

================================
P3-A 发布编排与回滚闭环
================================

实现项：
1) 发布编排器
- 新建 `quentin/runtime/release_orchestrator.py`
- 能力：
  - `promote_to_staging(feature_set)`
  - `promote_to_prod(feature_set, domain_scope)`
  - `rollback(feature_set, reason)`
- 只做 flag + 配置级发布，不做代码热替换。

2) 回滚快照
- 新建 `quentin/runtime/release_snapshot.py`
- 每次发布前保存：
  - 当前 flags
  - 关键配置 hash
  - 版本标识（git sha/时间戳）
- 回滚时从 snapshot 恢复。

3) 接入脚本
- 新建 `scripts/release_promote.py`
- 新建 `scripts/release_rollback.py`
- 参数化执行，支持 dry-run。

测试：
- `tests/integration/test_release_orchestrator_flow.py`
- 覆盖：promote -> verify -> rollback 全链路。

================================
P3-B 统一观测面（Metrics + Health + Alert）
================================

实现项：
1) 指标聚合器
- 新建 `quentin/observability/p3_metrics.py`
- 输出核心指标：
  - lane_queue_wait_ms_p95
  - lane_timeout_count
  - context_compaction_rate
  - provider_failover_success_rate
  - provider_cooldown_active_profiles
  - tool_call_block_rate
  - gateway_message_latency_p95
  - memory_recall_hit_rate_topk

2) 健康检查端点
- 在 `meta_agent/api/server.py` 增加 `/health/p3`
- 返回：
  - status(ok/warn/critical)
  - degraded_components[]
  - recent_failures[]

3) 告警规则文件
- 新建 `config/alerts_p3.yaml`
- 定义阈值与动作（仅日志告警即可，后续接外部系统）。

测试：
- `tests/unit/test_p3_metrics_aggregation.py`
- `tests/integration/test_p3_health_endpoint.py`

================================
P3-C 安全审计与故障演练
================================

实现项：
1) 审计日志标准化
- 新建 `quentin/security/audit_schema.py`
- 统一字段：
  - event_id, ts, actor, action, resource, decision, reason, trace_id, session_id
- 让 SafetyKernel / ToolManager / SelfProgramming 写同一 schema。

2) 安全回放工具
- 新建 `scripts/audit_replay.py`
- 输入时间窗口，输出：
  - blocked actions
  - high-risk actions
  - policy override events

3) 故障演练脚本
- 新建 `scripts/run_chaos_p3.py`
- 演练项：
  - provider 429 连续失败
  - lane 拥塞
  - gateway 消息洪泛
  - memory store degrade
- 输出演练报告到 `logs/chaos/`.

测试：
- `tests/integration/test_security_audit_pipeline.py`
- `tests/integration/test_chaos_failover_recovery.py`

================================
P3-D 文档与运行手册（必须）
================================

新增文档：
1) `docs/runbooks/P3_RELEASE_RUNBOOK.md`
- 发布前检查、发布步骤、回滚步骤、验收门槛。

2) `docs/runbooks/P3_INCIDENT_RUNBOOK.md`
- 常见故障处理：
  - failover storm
  - lane deadlock/timeout surge
  - gateway backlog
  - self-programming safety blocks spike

3) `docs/improve/P3_ACCEPTANCE_CHECKLIST_2026-02-14.md`
- 逐项 checklist + 对应证据路径。

================================
Feature Flags（必须新增）
================================

更新 `quentin/config/feature_flags.py`：
- `release_orchestrator_v1` (default false)
- `p3_metrics_v1` (default false)
- `p3_audit_v1` (default false)
- `chaos_drill_v1` (default false)

并在 `config/openclaw_parity.yaml` 补齐默认值（全 false）。

================================
验收门槛（必须满足）
================================

1) 所有新增单测/集成测试通过
2) 至少 1 次 dry-run 发布 + 回滚演示成功
3) 至少 1 份 chaos 演练报告生成
4) `/health/p3` 能返回结构化状态
5) 所有新能力可通过 flags 关闭并回到 legacy 行为

================================
交付格式（严格）
================================

按以下结构输出：
1) Completed
2) Modified Files
3) Test Commands + Results
4) Remaining Risks
5) Rollback Plan
6) Evidence Paths
