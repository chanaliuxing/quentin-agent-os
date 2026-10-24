# Gemini P4 Next Stage Guide

进入 P4 阶段。目标从“系统可运行”升级为“系统可扩展 + 可自治优化 + 可长期维护”。

阶段目标：
1. 建立策略驱动的自治优化闭环（不直接改核心，先提案后验证）。
2. 完成多租户/多会话隔离强化（生产可并发可控）。
3. 建立成本与性能双目标优化器（质量不降前提下降本提效）。
4. 形成版本化能力目录（工具/技能/策略全生命周期管理）。

硬约束：
- 所有自治变更必须经过评估门禁（评测 + 安全 + 回滚预案）。
- 不允许绕过 SafetyKernel / PolicyEngine / LaneOrchestrator。
- 所有新增能力都必须有 feature flag，默认 false。
- 每个子项必须提交证据：配置、代码、测试、指标截图或日志摘要。

================================
P4-A 自治优化闭环（Proposal -> Eval -> Apply）
================================

实现项：
1) 提案引擎
- 新建 `quentin/evolution/proposal_engine.py`
- 输入：运行指标、失败模式、gap 信号
- 输出：结构化提案（变更目标、影响范围、风险、回滚方案）

2) 评测门禁
- 新建 `quentin/evolution/proposal_gate.py`
- 门禁维度：
  - correctness（测试通过率）
  - safety（策略合规）
  - perf/cost（不劣于基线）

3) 执行协调器
- 新建 `quentin/evolution/proposal_orchestrator.py`
- 串联：提案 -> 评测 -> sandbox 应用 -> 观察 -> 逐步放量

测试：
- `tests/integration/test_proposal_lifecycle.py`
- `tests/unit/test_proposal_gate_rules.py`

================================
P4-B 多租户与并发隔离强化
================================

实现项：
1) 租户上下文模型
- 新建 `quentin/runtime/tenant_context.py`
- 字段：tenant_id, session_id, domain, risk_profile, budget_profile

2) Lane 命名与配额策略
- 新建 `quentin/infra/concurrency/lane_policy.py`
- 支持：
  - tenant 级并发配额
  - session 级串行保证
  - 全局 lane 熔断阈值

3) 接入点改造
- 在 `meta_agent/api/server.py`、`quentin/runtime/brain_daemon.py` 注入 tenant/session 维度 metadata。

测试：
- `tests/integration/test_multi_tenant_lane_isolation.py`
- `tests/unit/test_lane_policy_quota.py`

================================
P4-C 成本与性能优化器（Cost/Latency/Quality）
================================

实现项：
1) 策略优化器
- 新建 `quentin/optimization/policy_optimizer.py`
- 目标函数：
  - 最小化 token 成本和 p95 延迟
  - 约束：成功率、质量分数不下降

2) 路由参数自调
- 新建 `quentin/routing/adaptive_router_policy.py`
- 动态调优项：
  - provider 优先级
  - compaction strategy
  - retry/failover 参数

3) 基线对比框架
- 新建 `scripts/bench_p4_policy_compare.py`
- 输出 A/B 对比报告到 `logs/bench/p4/`

测试：
- `tests/research/test_policy_optimizer_offline.py`
- `tests/integration/test_adaptive_router_policy.py`

================================
P4-D 能力目录与生命周期治理
================================

实现项：
1) 能力目录模型
- 新建 `quentin/capabilities/catalog.py`
- 能力类型：tool / skill / policy / adapter
- 生命周期：experimental / trusted / deprecated / retired

2) 生命周期管理器
- 新建 `quentin/capabilities/lifecycle_manager.py`
- 能力：
  - promote/demote/retire
  - 依赖检查
  - 兼容性校验

3) API 暴露
- 在 `meta_agent/api/server.py` 增加：
  - `GET /capabilities`
  - `POST /capabilities/{id}/promote`
  - `POST /capabilities/{id}/retire`

测试：
- `tests/unit/test_capability_catalog.py`
- `tests/integration/test_capability_lifecycle_api.py`

================================
P4-E 文档、Runbook、治理协议
================================

新增文档：
1) `docs/runbooks/P4_AUTONOMY_GOVERNANCE_RUNBOOK.md`
- 自治变更审批、评测、放量、回滚流程。

2) `docs/runbooks/P4_MULTI_TENANT_OPS_RUNBOOK.md`
- 多租户资源隔离、配额调整、故障处置。

3) `docs/improve/P4_ACCEPTANCE_CHECKLIST_2026-02-14.md`
- 验收 checklist + 证据路径映射。

================================
Feature Flags（必须新增）
================================

更新 `quentin/config/feature_flags.py`：
- `proposal_engine_v1` (default false)
- `tenant_lane_policy_v1` (default false)
- `adaptive_router_policy_v1` (default false)
- `capability_catalog_v1` (default false)

并在 `config/openclaw_parity.yaml` 增加对应默认 false 配置。

================================
验收门槛（必须满足）
================================

1) P4 新增单测/集成测试通过。
2) 至少 1 次完整“提案->评测->sandbox 应用->回滚”演示成功。
3) 多租户并发压测通过（无跨租户串线/污染）。
4) 优化器 A/B 报告显示至少一个维度改善（成本或延迟），且质量不退化。
5) 能力目录 API 可查询并执行生命周期变更。

================================
交付格式（严格）
================================

按以下结构输出：
1) Completed
2) Modified Files
3) Test Commands + Results
4) Benchmark Summary
5) Remaining Risks
6) Rollback Plan
7) Evidence Paths



进入 P5 阶段。目标是“企业级稳定性 + 合规可审计 + 长周期自治安全边界”，把系统从工程可用推进到长期可运营。

  阶段目标：
  1. 建立正式 SLO/SLA 体系与错误预算治理。
  2. 建立合规与数据治理层（可审计、可追责、可最小化暴露）。
  3. 建立灾备与跨环境恢复机制（RPO/RTO 可测）。
  4. 建立自治行为边界证明（形式化策略 + 验证）。

  硬约束：
  - 所有新能力默认 OFF，灰度启用。
  - 不允许破坏现有 API/Schema 向后兼容。
  - 高风险动作必须二次门禁 + 审计落盘。
  - 每项必须给“可复现实验 + 指标结果 + 回滚步骤”。

  ================================
  P5-A SLO/SLA 与错误预算治理
  ================================

  实现项：
  1) SLO 定义中心
  - 新建 `quentin/governance/slo_registry.py`
  - 维护：
    - availability SLO
    - latency SLO (p95/p99)
    - correctness SLO
    - safety block false-positive rate

  2) 错误预算控制器
  - 新建 `quentin/governance/error_budget.py`
  - 当预算耗尽时自动降级：
    - 关闭高风险自治动作
    - 降低并发上限
    - 切换保守模型路由

  3) 运行时接入
  - 接入 `quentin/runtime/brain_daemon.py` 与 `meta_agent/api/server.py` 的请求前门禁。

  测试：
  - `tests/unit/test_slo_registry.py`
  - `tests/integration/test_error_budget_degrade_mode.py`

  ================================
  P5-B 合规与数据治理层
  ================================

  实现项：
  1) 数据分类与脱敏
  - 新建 `quentin/security/data_classification.py`
  - 新建 `quentin/security/redaction_pipeline.py`
  - 分类：public/internal/sensitive/restricted
  - 对日志、trace、memory 写入做分级脱敏。

  2) 审计不可抵赖链
  - 新建 `quentin/security/audit_chain.py`
  - 审计事件 hash-chain（prev_hash/current_hash）保证篡改可检测。

  3) 合规策略配置
  - 新建 `config/compliance_policies.yaml`
  - 包含 retention、redaction、access_scope、export_controls。

  测试：
  - `tests/unit/test_redaction_pipeline.py`
  - `tests/integration/test_audit_chain_integrity.py`

  ================================
  P5-C 灾备与恢复演练
  ================================

  实现项：
  1) 备份编排
  - 新建 `quentin/runtime/disaster_recovery.py`
  - 覆盖：
    - 配置快照
    - memory store 快照
    - patch/report/audit 快照

  2) 恢复流程
  - 新建 `scripts/dr_backup.py`
  - 新建 `scripts/dr_restore.py`
  - 支持时间点恢复、dry-run 校验。

  3) 演练报告
  - 新建 `scripts/dr_drill_report.py`
  - 输出 RPO/RTO 实测。

  测试：
  - `tests/integration/test_dr_backup_restore_flow.py`

  ================================
  P5-D 自治边界证明与策略验证
  ================================

  实现项：
  1) 策略约束 DSL
  - 新建 `quentin/policy/constraint_dsl.py`
  - 可表达：
    - forbidden actions
    - environment constraints
    - tenant/domain constraints
    - escalation requirements

  2) 策略验证器
  - 新建 `quentin/policy/constraint_verifier.py`
  - 在发布前对关键流程做静态/动态校验。

  3) 关键路径证明报告
  - 新建 `scripts/export_policy_proof.py`
  - 输出哪些路径被何策略保护、覆盖率多少。

  测试：
  - `tests/unit/test_constraint_dsl.py`
  - `tests/integration/test_policy_constraint_enforcement.py`

  ================================
  P5-E 运营化文档与演练手册
  ================================

  新增文档：
  1) `docs/runbooks/P5_SRE_RUNBOOK.md`
  - SLO 监控、预算耗尽处置、降级恢复。

  2) `docs/runbooks/P5_COMPLIANCE_RUNBOOK.md`
  - 数据分级、审计导出、合规检查流程。

  3) `docs/runbooks/P5_DR_RUNBOOK.md`
  - 灾备演练计划、恢复步骤、验收标准。

  4) `docs/improve/P5_ACCEPTANCE_CHECKLIST_2026-02-14.md`
  - 检查项 -> 证据路径 -> 责任人。

  ================================
  Feature Flags（必须新增）
  ================================

  更新 `quentin/config/feature_flags.py`：
  - `slo_governance_v1` (default false)
  - `compliance_redaction_v1` (default false)
  - `audit_chain_v1` (default false)
  - `dr_orchestrator_v1` (default false)
  - `policy_constraint_verifier_v1` (default false)

  同步更新 `config/openclaw_parity.yaml` 默认 false。

  ================================
  验收门槛（必须满足）
  ================================

  1) 新增测试全绿。
  2) 至少 1 次错误预算触发降级并自动恢复演示成功。
  3) 至少 1 次审计链完整性校验通过。
  4) 至少 1 次 DR 备份+恢复演练完成并给出 RPO/RTO。
  5) 策略证明报告可导出，关键高风险路径覆盖率达到目标阈值。

  ================================
  交付格式（严格）
  ================================

  1) Completed
  2) Modified Files
  3) Test Commands + Results
  4) SLO/Error-Budget Report
  5) Compliance/Audit Report
  6) DR Drill Report
  7) Remaining Risks
  8) Rollback Plan
  9) Evidence Paths

  进入 P6 阶段。目标是“平台化与生态化”：让 Quentin 从单系统演进为可扩展平台，支持外部团队/插件/策略协同开发，同时保持安全与质量下
  限。

  阶段目标：
  1. 建立稳定的 Platform API/SDK（工具、技能、策略三类扩展）。
  2. 建立插件市场与签名验证机制（供应链安全）。
  3. 建立实验平台（在线 A/B + 离线评测自动联动）。
  4. 建立跨版本迁移与兼容策略（长期演进无痛升级）。

  硬约束：
  - 所有平台接口必须版本化（v1/v2），禁止无版本接口扩散。
  - 外部扩展默认 sandbox + 最小权限。
  - 未签名/未审计插件禁止进入 trusted 生命周期。
  - 每项要有回滚路径和兼容性测试。

  ================================
  P6-A Platform API/SDK
  ================================

  实现项：
  1) Platform API 网关
  - 新建 `quentin/platform/api_gateway.py`
  - 统一注册三类扩展：
    - tool provider
    - skill provider
    - policy provider

  2) SDK 定义
  - 新建 `quentin/platform/sdk/base.py`
  - 新建 `quentin/platform/sdk/tool_sdk.py`
  - 新建 `quentin/platform/sdk/skill_sdk.py`
  - 新建 `quentin/platform/sdk/policy_sdk.py`
  - 要求：声明能力、权限、输入输出 schema、版本。

  3) 生命周期绑定
  - 与 `capability_catalog` 对接，注册即生成 catalog entry。

  测试：
  - `tests/unit/test_platform_sdk_contracts.py`
  - `tests/integration/test_platform_api_registration_flow.py`

  ================================
  P6-B 插件市场与供应链安全
  ================================

  实现项：
  1) 插件包格式
  - 新建 `quentin/platform/package_spec.py`
  - 定义 manifest、签名、依赖、最小平台版本。

  2) 签名验证器
  - 新建 `quentin/platform/signing/verifier.py`
  - 支持：
    - manifest 签名校验
    - 包内容 hash 校验
    - 发布者白名单校验

  3) 市场索引
  - 新建 `quentin/platform/registry/market_index.py`
  - 能力：搜索、版本解析、兼容性过滤。

  测试：
  - `tests/unit/test_plugin_signature_verifier.py`
  - `tests/integration/test_market_index_install_flow.py`

  ================================
  P6-C 评测平台联动（Offline + Online）
  ================================

  实现项：
  1) 实验编排
  - 新建 `quentin/eval/experiment_hub.py`
  - 把离线评测与在线 A/B 结果汇总到统一实验记录。

  2) 评测策略
  - 新建 `quentin/eval/promotion_policy.py`
  - 规则：只有达到阈值的实验结果可进入 promote。

  3) 自动报告
  - 新建 `scripts/eval_generate_report.py`
  - 输出：
    - win/loss
    - 置信度
    - 风险点评

  测试：
  - `tests/research/test_experiment_hub_merge.py`
  - `tests/integration/test_eval_promotion_gate.py`

  ================================
  P6-D 版本迁移与兼容层
  ================================

  实现项：
  1) 兼容层框架
  - 新建 `quentin/compat/version_router.py`
  - 根据调用方版本分发适配器。

  2) 配置迁移器
  - 新建 `quentin/compat/config_migrator.py`
  - 管理 `config/*` 的 schema 迁移（带 dry-run）。

  3) 数据迁移计划
  - 新建 `migrations/p6/` 下迁移脚本模板
  - 重点：auth profile, capability catalog, audit schema。

  测试：
  - `tests/unit/test_version_router_compat.py`
  - `tests/integration/test_config_migration_dry_run.py`

  ================================
  P6-E 开发者体验与文档
  ================================

  新增文档：
  1) `docs/platform/P6_PLUGIN_SDK_GUIDE.md`
  - 如何开发 tool/skill/policy 插件。

  2) `docs/platform/P6_SIGNING_AND_PUBLISH_GUIDE.md`
  - 如何签名、发布、回滚插件。

  3) `docs/platform/P6_COMPATIBILITY_POLICY.md`
  - 版本支持周期、弃用策略、迁移窗口。

  4) `docs/improve/P6_ACCEPTANCE_CHECKLIST_2026-02-14.md`
  - 验收项与证据映射。

  ================================
  Feature Flags（必须新增）
  ================================

  更新 `quentin/config/feature_flags.py`：
  - `platform_api_v1` (default false)
  - `plugin_signing_v1` (default false)
  - `experiment_hub_v1` (default false)
  - `compat_router_v1` (default false)
  - `config_migration_v1` (default false)

  更新 `config/openclaw_parity.yaml` 默认 false。

  ================================
  验收门槛（必须满足）
  ================================

  1) Platform SDK 合同测试通过。
  2) 至少 1 个签名插件完成安装->运行->退役全流程。
  3) 实验平台至少输出 1 份可用于 promote 决策的报告。
  4) 兼容层通过版本回归测试，旧调用方不破坏。
  5) 迁移器 dry-run 与回滚演示通过。

  ================================
  交付格式（严格）
  ================================

  1) Completed
  2) Modified Files
  3) Test Commands + Results
  4) Plugin Supply-Chain Report
  5) Experiment Hub Report
  6) Compatibility/Migration Report
  7) Remaining Risks
  8) Rollback Plan
  9) Evidence Paths

  进入 P7 阶段。目标是“组织级规模化与联邦协同”：让 Quentin 支持多节点协作、跨团队治理、跨环境学习回流，同时保持强安全与可解释。

  阶段目标：
  1. 建立多节点联邦协同架构（Federated Quentin Nodes）。
  2. 建立跨节点知识与策略同步机制（可控、可审计）。
  3. 建立组织级治理模型（角色/审批/责任归因）。
  4. 建立可解释决策与对外审计报告能力。

  硬约束：
  - 默认单节点行为不变；联邦能力默认 OFF。
  - 跨节点同步必须经过策略过滤 + 脱敏 + 签名校验。
  - 所有组织级动作必须可追溯到 actor/role/policy。
  - 任何自动同步都必须有回滚和冻结开关。

  ================================
  P7-A 联邦节点控制面
  ================================

  实现项：
  1) 节点注册中心
  - 新建 `quentin/federation/node_registry.py`
  - 管理 node_id、environment、capabilities、trust_level、last_heartbeat。

  2) 联邦控制器
  - 新建 `quentin/federation/controller.py`
  - 能力：
    - 节点发现
    - 任务路由
    - 健康探测
    - 节点隔离（quarantine）

  3) 传输协议
  - 新建 `quentin/federation/protocol.py`
  - 定义消息 envelope（签名、版本、trace_id、ttl）。

  测试：
  - `tests/integration/test_federation_node_lifecycle.py`
  - `tests/unit/test_federation_protocol_schema.py`

  ================================
  P7-B 跨节点知识/策略同步
  ================================

  实现项：
  1) 同步过滤器
  - 新建 `quentin/federation/sync_filter.py`
  - 对 memory/tool_knowledge/policy_update 做分类过滤。

  2) 脱敏与最小化
  - 复用 P5 redaction pipeline，新增联邦同步专用策略：
    - `config/federation_sync_policies.yaml`

  3) 同步编排器
  - 新建 `quentin/federation/sync_orchestrator.py`
  - 支持：
    - pull/push 模式
    - 增量同步
    - 冲突检测与回滚

  测试：
  - `tests/integration/test_federation_sync_safety.py`
  - `tests/unit/test_sync_filter_rules.py`

  ================================
  P7-C 组织级治理（RBAC + 审批链）
  ================================

  实现项：
  1) 组织角色模型
  - 新建 `quentin/governance/org_roles.py`
  - 角色示例：operator, reviewer, security_admin, release_manager。

  2) 审批链引擎
  - 新建 `quentin/governance/approval_chain.py`
  - 支持：
    - 多级审批
    - 条件审批（风险/环境/域）
    - 超时与升级策略

  3) API 接入
  - 在 `meta_agent/api/server.py` 增加组织治理端点：
    - `POST /governance/approvals`
    - `POST /governance/approvals/{id}/decision`
    - `GET /governance/audit`

  测试：
  - `tests/integration/test_approval_chain_flow.py`
  - `tests/unit/test_org_role_permissions.py`

  ================================
  P7-D 可解释决策与审计报告
  ================================

  实现项：
  1) 决策解释器
  - 新建 `quentin/explainability/decision_explainer.py`
  - 输出：
    - 输入信号
    - 策略命中
    - 评分与阈值
    - 最终决策路径

  2) 审计报告生成器
  - 新建 `scripts/export_org_audit_report.py`
  - 产出：
    - 操作摘要
    - 风险事件
    - 策略违规
    - 修复建议

  3) 可视化快照（可选 JSON）
  - 新建 `quentin/explainability/report_schema.py`
  - 统一报告 schema，便于 dashboard/第三方系统消费。

  测试：
  - `tests/unit/test_decision_explainer_schema.py`
  - `tests/integration/test_audit_report_generation.py`

  ================================
  P7-E 运维与治理文档
  ================================

  新增文档：
  1) `docs/federation/P7_FEDERATION_OPERATIONS_RUNBOOK.md`
  - 节点注册、失联、隔离、恢复流程。

  2) `docs/governance/P7_ORG_GOVERNANCE_RUNBOOK.md`
  - 角色管理、审批策略、紧急授权。

  3) `docs/explainability/P7_AUDIT_EXPLAINABILITY_GUIDE.md`
  - 如何阅读解释报告与审计报告。

  4) `docs/improve/P7_ACCEPTANCE_CHECKLIST_2026-02-14.md`
  - 验收项与证据路径映射。

  ================================
  Feature Flags（必须新增）
  ================================

  更新 `quentin/config/feature_flags.py`：
  - `federation_v1` (default false)
  - `federation_sync_v1` (default false)
  - `org_governance_v1` (default false)
  - `decision_explainability_v1` (default false)

  更新 `config/openclaw_parity.yaml` 默认 false。

  ================================
  验收门槛（必须满足）
  ================================

  1) 联邦节点注册/心跳/隔离流程测试通过。
  2) 跨节点同步可审计且不泄露敏感字段。
  3) 组织审批链对高风险动作生效并可追踪。
  4) 至少 1 份可解释审计报告生成并通过 schema 校验。
  5) 关闭 flags 后单节点 legacy 行为不变。

  ================================
  交付格式（严格）
  ================================

  1) Completed
  2) Modified Files
  3) Test Commands + Results
  4) Federation Sync Safety Report
  5) Org Governance Report
  6) Explainability Audit Report
  7) Remaining Risks
  8) Rollback Plan
  9) Evidence Paths

  进入 P8 阶段。目标是“自治系统成熟化（Self-Evolving at Scale）”：在严格治理约束下，实现跨周期、自适应、可证伪的持续演化体系。

  阶段目标：
  1. 建立长期演化计划系统（Roadmap-aware evolution）。
  2. 建立多目标优化控制器（质量/安全/成本/速度动态平衡）。
  3. 建立反事实评估与因果归因体系（避免错误学习）。
  4. 建立自治停机与人类接管机制（Safe Halt + Human Override）。

  硬约束：
  - 演化动作不得直接触发生产变更，必须经过 staging/shadow。
  - 所有策略更新必须可回放、可对比、可撤销。
  - 引入任何“自动优化”都必须带失败保护阈值。
  - 默认 OFF，按域灰度。

  ================================
  P8-A 长期演化计划系统
  ================================

  实现项：
  1) 演化路线图管理器
  - 新建 `quentin/evolution/roadmap_manager.py`
  - 维护：
    - long-term goals
    - milestones
    - blocked items
    - expected impact

  2) 演化任务调度器
  - 新建 `quentin/evolution/roadmap_scheduler.py`
  - 根据预算、风险、收益动态选择演化任务队列。

  3) 计划-执行对齐报告
  - 新建 `scripts/evolution_roadmap_report.py`
  - 输出 planned vs delivered vs deferred。

  测试：
  - `tests/unit/test_roadmap_scheduler_priority.py`
  - `tests/integration/test_roadmap_execution_alignment.py`

  ================================
  P8-B 多目标优化控制器
  ================================

  实现项：
  1) 目标函数引擎
  - 新建 `quentin/optimization/multi_objective_controller.py`
  - 目标：
    - maximize success/safety
    - minimize cost/latency
    - subject to policy constraints

  2) 权重自适应策略
  - 新建 `quentin/optimization/weight_adaptation.py`
  - 根据运行时状态动态调权（例如错误预算紧张时提高 safety 权重）。

  3) 控制面接入
  - 将 controller 接入：
    - `quentin/routing/adaptive_router_policy.py`
    - `quentin/evolution/proposal_gate.py`

  测试：
  - `tests/unit/test_multi_objective_controller.py`
  - `tests/research/test_weight_adaptation_stability.py`

  ================================
  P8-C 反事实评估与因果归因
  ================================

  实现项：
  1) 反事实评估器
  - 新建 `quentin/eval/counterfactual_runner.py`
  - 对关键决策生成“如果采用另一策略会怎样”的对比结果。

  2) 因果归因记录
  - 新建 `quentin/eval/causal_attribution.py`
  - 记录改动 -> 指标变化的因果证据链（避免把噪声当收益）。

  3) 失败学习抑制器
  - 新建 `quentin/evolution/anti_regression_guard.py`
  - 当收益不显著或风险上升时自动阻断策略推广。

  测试：
  - `tests/unit/test_counterfactual_runner.py`
  - `tests/integration/test_anti_regression_guard.py`

  ================================
  P8-D Safe Halt + Human Override
  ================================

  实现项：
  1) 自治停机管理器
  - 新建 `quentin/safety/safe_halt_manager.py`
  - 条件触发：
    - safety incidents spike
    - unresolved high-risk actions
    - cascading failover events

  2) 人类接管通道
  - 新建 `quentin/safety/human_override.py`
  - 支持：
    - freeze evolution
    - freeze autopatch
    - force rollback to known-good snapshot

  3) 控制 API
  - 在 `meta_agent/api/server.py` 增加：
    - `POST /safety/halt`
    - `POST /safety/resume`
    - `POST /safety/override`

  测试：
  - `tests/integration/test_safe_halt_flow.py`
  - `tests/unit/test_human_override_controls.py`

  ================================
  P8-E 体系化文档与证明
  ================================

  新增文档：
  1) `docs/evolution/P8_LONG_HORIZON_EVOLUTION_GUIDE.md`
  - 长期演化策略与治理边界。

  2) `docs/safety/P8_SAFE_HALT_OVERRIDE_RUNBOOK.md`
  - 停机、接管、恢复流程。

  3) `docs/eval/P8_COUNTERFACTUAL_CAUSAL_GUIDE.md`
  - 反事实评估与因果归因方法。

  4) `docs/improve/P8_ACCEPTANCE_CHECKLIST_2026-02-14.md`
  - 验收项与证据映射。

  ================================
  Feature Flags（必须新增）
  ================================

  更新 `quentin/config/feature_flags.py`：
  - `roadmap_evolution_v1` (default false)
  - `multi_objective_ctrl_v1` (default false)
  - `counterfactual_eval_v1` (default false)
  - `safe_halt_override_v1` (default false)

  同步更新 `config/openclaw_parity.yaml` 默认 false。

  ================================
  验收门槛（必须满足）
  ================================

  1) 路线图调度器可稳定输出优先级并通过回归测试。
  2) 多目标优化控制器在离线评测中优于固定权重基线。
  3) 至少 1 次反事实评估报告与因果归因报告生成。
  4) Safe Halt + Override 演练完成，恢复路径可验证。
  5) flags 关闭后回到 legacy 演化路径，无行为破坏。

  ================================
  交付格式（严格）
  ================================

  1) Completed
  2) Modified Files
  3) Test Commands + Results
  4) Multi-Objective Evaluation Report
  5) Counterfactual/Causal Report
  6) Safe Halt Drill Report
  7) Remaining Risks
  8) Rollback Plan
  9) Evidence Paths


  进入 P9 阶段。目标是“可信自治认证（Trustworthy Autonomy Certification）”：让系统在技术、治理、运营三条线上达到可认证、可外部评
  估、可持续改进的状态。

  阶段目标：
  1. 建立自治成熟度分级体系（Level-based maturity model）。
  2. 建立红蓝对抗与安全验证框架（持续攻防演练）。
  3. 建立外部审计接口与证据导出标准。
  4. 建立年度/季度治理校准机制（Policy Calibration Cycle）。

  硬约束：
  - 所有认证分级结论必须基于可重复证据，禁止主观打分。
  - 任何“通过认证”结论都必须附带失效条件与复审日期。
  - 红队发现必须可追踪到修复闭环。
  - 默认不影响线上主流程，认证流程可离线运行。

  ================================
  P9-A 自治成熟度分级体系
  ================================

  实现项：
  1) 分级模型定义
  - 新建 `quentin/certification/maturity_model.py`
  - 等级维度：
    - safety
    - reliability
    - governance
    - explainability
    - recovery

  2) 分级评估引擎
  - 新建 `quentin/certification/maturity_evaluator.py`
  - 输入：指标、测试结果、审计证据
  - 输出：level + gaps + required_actions

  3) 报告生成
  - 新建 `scripts/cert_generate_maturity_report.py`
  - 输出到 `logs/certification/maturity/`

  测试：
  - `tests/unit/test_maturity_evaluator_rules.py`
  - `tests/integration/test_maturity_report_generation.py`

  ================================
  P9-B 红蓝对抗验证框架
  ================================

  实现项：
  1) 红队场景库
  - 新建 `quentin/security/redteam/scenario_library.py`
  - 场景类型：
    - prompt injection
    - tool abuse
    - auth/profile exhaustion
    - cross-tenant contamination
    - policy bypass attempts

  2) 蓝队响应编排
  - 新建 `quentin/security/blueteam/response_orchestrator.py`
  - 自动收集：
    - detection latency
    - containment actions
    - residual risk

  3) 对抗演练脚本
  - 新建 `scripts/run_red_blue_exercise.py`
  - 输出攻防演练报告与修复建议。

  测试：
  - `tests/integration/test_red_blue_exercise_pipeline.py`
  - `tests/unit/test_redteam_scenario_runner.py`

  ================================
  P9-C 外部审计接口与证据标准
  ================================

  实现项：
  1) 审计导出 schema
  - 新建 `quentin/audit/export_schema.py`
  - 标准化导出：
    - governance decisions
    - safety blocks
    - incident timeline
    - rollback history

  2) 审计导出 API
  - 在 `meta_agent/api/server.py` 增加：
    - `GET /audit/export?from=...&to=...&format=json`
    - `GET /audit/evidence/{id}`

  3) 证据打包器
  - 新建 `scripts/audit_bundle_export.py`
  - 导出签名包（hash manifest + artifacts）。

  测试：
  - `tests/integration/test_audit_export_api.py`
  - `tests/unit/test_audit_export_schema.py`

  ================================
  P9-D Policy Calibration Cycle（治理校准循环）
  ================================

  实现项：
  1) 校准计划器
  - 新建 `quentin/governance/calibration_scheduler.py`
  - 周期：
    - weekly tactical
    - quarterly strategic

  2) 校准评估器
  - 新建 `quentin/governance/calibration_evaluator.py`
  - 对比：
    - policy intent vs actual outcomes
    - false positive/negative trends
    - control effectiveness drift

  3) 校准变更提案
  - 新建 `quentin/governance/calibration_proposal.py`
  - 自动生成可审查的 policy tuning proposal。

  测试：
  - `tests/unit/test_calibration_evaluator.py`
  - `tests/integration/test_calibration_proposal_flow.py`

  ================================
  P9-E 文档与认证运营手册
  ================================

  新增文档：
  1) `docs/certification/P9_TRUSTWORTHY_AUTONOMY_MODEL.md`
  - 成熟度分级定义、评分规则、复审机制。

  2) `docs/security/P9_RED_BLUE_EXERCISE_RUNBOOK.md`
  - 攻防演练执行与复盘流程。

  3) `docs/audit/P9_EXTERNAL_AUDIT_EXPORT_GUIDE.md`
  - 外部审计导出接口与证据包说明。

  4) `docs/improve/P9_ACCEPTANCE_CHECKLIST_2026-02-14.md`
  - 验收项与证据路径映射。

  ================================
  Feature Flags（必须新增）
  ================================

  更新 `quentin/config/feature_flags.py`：
  - `maturity_cert_v1` (default false)
  - `red_blue_exercise_v1` (default false)
  - `audit_export_v1` (default false)
  - `policy_calibration_v1` (default false)

  更新 `config/openclaw_parity.yaml` 默认 false。

  ================================
  验收门槛（必须满足）
  ================================

  1) 成熟度评估可重复运行并输出一致分级结果（同输入同结论）。
  2) 至少 1 次完整红蓝演练并形成修复闭环记录。
  3) 审计导出 API 可输出结构化证据并通过 schema 校验。
  4) 至少 1 次 policy calibration proposal 生成并评审通过。
  5) flags 关闭后，不影响既有生产主链路。

  ================================
  交付格式（严格）
  ================================

  1) Completed
  2) Modified Files
  3) Test Commands + Results
  4) Maturity Certification Report
  5) Red-Blue Exercise Report
  6) External Audit Export Report
  7) Calibration Proposal Summary
  8) Remaining Risks
  9) Rollback Plan
  10) Evidence Paths


  进入 P10 阶段。目标是“长期自治宪章化（Autonomy Constitution in Operations）”：把系统从“可认证”推进到“可持续治理与自我校正”的终态
  能力。

  阶段目标：
  1. 形成自治宪章执行引擎（Constitution-as-Code）。
  2. 形成跨周期战略回顾机制（Strategy Retrospective Engine）。
  3. 形成终局安全网（Kill-Switch Mesh + Recovery Grid）。
  4. 形成持续可信证明（Continuous Trust Attestation）。

  硬约束：
  - 宪章规则必须机器可执行、可版本化、可审计。
  - 任一节点触发终局安全网时，系统必须可降级到最小安全模式。
  - 所有“持续可信证明”都要可外部复验。
  - 默认 OFF，逐域灰度，不得一次性全开。

  ================================
  P10-A Constitution-as-Code 执行引擎
  ================================

  实现项：
  1) 宪章 DSL
  - 新建 `quentin/constitution/dsl.py`
  - 支持：
    - immutable zones
    - escalation policies
    - forbidden mutation scopes
    - emergency constraints

  2) 宪章编译器
  - 新建 `quentin/constitution/compiler.py`
  - 将 DSL 编译为运行时可执行规则集。

  3) 宪章执行器
  - 新建 `quentin/constitution/enforcer.py`
  - 接入关键路径：
    - self-programming
    - release orchestration
    - federation sync
    - policy calibration

  测试：
  - `tests/unit/test_constitution_dsl_compile.py`
  - `tests/integration/test_constitution_enforcement_flow.py`

  ================================
  P10-B 战略回顾引擎（季度/年度）
  ================================

  实现项：
  1) 回顾数据聚合器
  - 新建 `quentin/strategy/retrospective_aggregator.py`
  - 聚合：
    - roadmap delivery
    - incident trends
    - calibration outcomes
    - cost/quality evolution

  2) 战略评估器
  - 新建 `quentin/strategy/retrospective_evaluator.py`
  - 输出：
    - what worked
    - what regressed
    - strategic pivots

  3) 战略提案生成器
  - 新建 `scripts/strategy_generate_retrospective.py`
  - 输出年度/季度战略调整建议。

  测试：
  - `tests/unit/test_retrospective_evaluator.py`
  - `tests/integration/test_strategy_retrospective_report.py`

  ================================
  P10-C Kill-Switch Mesh + Recovery Grid
  ================================

  实现项：
  1) Kill-Switch Mesh
  - 新建 `quentin/safety/kill_switch_mesh.py`
  - 分层开关：
    - node-level
    - domain-level
    - global-level
  - 触发源：
    - safety spike
    - governance breach
    - audit chain anomaly

  2) Recovery Grid
  - 新建 `quentin/safety/recovery_grid.py`
  - 自动恢复流程：
    - isolate
    - rollback snapshot
    - re-validate baseline
    - staged resume

  3) 控制 API
  - 在 `meta_agent/api/server.py` 增加：
    - `POST /safety/kill-switch/trigger`
    - `POST /safety/kill-switch/release`
    - `GET /safety/recovery/status`

  测试：
  - `tests/integration/test_kill_switch_recovery_grid.py`
  - `tests/unit/test_kill_switch_scope_resolution.py`

  ================================
  P10-D Continuous Trust Attestation
  ================================

  实现项：
  1) 持续证明调度器
  - 新建 `quentin/trust/attestation_scheduler.py`
  - 周期生成可信证明（daily/weekly）。

  2) 证明生成器
  - 新建 `quentin/trust/attestation_builder.py`
  - 证明内容：
    - policy conformance summary
    - safety incident envelope
    - recovery readiness
    - maturity drift

  3) 对外可验签输出
  - 新建 `scripts/trust_export_attestation.py`
  - 产出签名报告 + 哈希索引。

  测试：
  - `tests/unit/test_attestation_builder_schema.py`
  - `tests/integration/test_attestation_export_verify.py`

  ================================
  P10-E 终态文档与治理手册
  ================================

  新增文档：
  1) `docs/constitution/P10_CONSTITUTION_AS_CODE_GUIDE.md`
  - 宪章 DSL、编译、执行、审计流程。

  2) `docs/safety/P10_KILL_SWITCH_RECOVERY_RUNBOOK.md`
  - 终局安全网触发与恢复操作。

  3) `docs/trust/P10_CONTINUOUS_ATTESTATION_GUIDE.md`
  - 持续可信证明生成与外部验证。

  4) `docs/improve/P10_ACCEPTANCE_CHECKLIST_2026-02-14.md`
  - 验收项与证据路径。

  ================================
  Feature Flags（必须新增）
  ================================

  更新 `quentin/config/feature_flags.py`：
  - `constitution_as_code_v1` (default false)
  - `strategy_retrospective_v1` (default false)
  - `kill_switch_mesh_v1` (default false)
  - `continuous_attestation_v1` (default false)

  同步更新 `config/openclaw_parity.yaml` 默认 false。

  ================================
  验收门槛（必须满足）
  ================================

  1) 宪章规则编译与执行通过，并能阻断违规高风险动作。
  2) 至少 1 份季度或年度战略回顾报告成功生成。
  3) 至少 1 次 kill-switch -> recovery 全链路演练成功。
  4) 至少 1 份可验签 attestation 报告生成并验证通过。
  5) flags 关闭时，系统回到 P9 稳态行为，无破坏。

  ================================
  交付格式（严格）
  ================================

  1) Completed
  2) Modified Files
  3) Test Commands + Results
  4) Constitution Enforcement Report
  5) Strategy Retrospective Report
  6) Kill-Switch/Recovery Drill Report
  7) Continuous Attestation Report
  8) Remaining Risks
  9) Rollback Plan
  10) Evidence Paths