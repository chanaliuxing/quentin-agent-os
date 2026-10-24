# Blueprint v3（`blueprint.md`）落地：超详细可勾选 TODO Checklist

Date: 2026-02-05  
Reference:
- Gap analysis: `docs/BLUEPRINT_GAP_ANALYSIS_V3.md`
- Blueprint (source of truth): `blueprint.md`
- YAML blueprint (needs reconciliation): `blueprint/meta_agent_v3.yaml`
- OpenClaw takeaways (engineering patterns to port): `docs/improve/openclaw_takeaways_for_quentin.md`
- Memory engineering TODOs (extracted): `docs/TODO_MEMORY_MODULE_ENGINEERING_ENHANCEMENTS.md`
- Placeholder/gap report: `docs/BLUEPRINT_V3_CODEBASE_GAP_AND_PLACEHOLDER_REPORT.md`
- Placeholder burn-down TODOs: `docs/TODO_BLUEPRINT_V3_PLACEHOLDER_BACKLOG.md`
- Next-phase TODOs (post checklist): `docs/TODO_BLUEPRINT_V3_NEXT_PHASE.md`

> 说明：本清单按“可打勾、可验收”为目标拆到工程颗粒度。  
> 约定：每条 TODO 尽量包含 **落点文件/模块** 与 **验收标准**（DoD）。

---

## P0（阻塞级）：先把“主路径 + 安全边界”做成不可绕过

### P0.1 收敛主路径（去碎片化，明确 canonical 实现）

- [x] 盘点并列出重复实现清单（输出到 `docs/ARCHITECTURE.md` 或本文件附录）
  - [x] `CognitiveLoop` 重复点：`quentin/cognitive/loop.py`、`quentin/runtime/cognitive_loop.py`、`meta_agent/evolution/cognitive_loop.py`（`quentin/core/*` 已移除）
  - [x] `SleepLoop` 重复点：`quentin/memory/sleep_loop.py`、`quentin/sleep/loop.py`、`quentin/loops/sleep_loop.py`、`quentin/runtime/sleep_loop.py`、`meta_agent/evolution/sleep_loop.py`
  - [x] `ImmuneLoop` 重复点：`quentin/immune/loop.py`、`quentin/runtime/immune_loop.py`、`quentin/loops/immune_loop.py`、`meta_agent/evolution/blueprint_loop.py`（`quentin/core/*` 已移除）
  - [x] `ExperimentOrchestrator` 重复点：`quentin/l3/research/experiment_orchestrator.py`、`quentin/l3/research/orchestrator.py`、`quentin/l3/research/experiments.py`、`quentin/experiments/orchestrator.py`
  - [x] `EvalHarness` 重复点：`quentin/l3/research/eval_harness.py`、`quentin/eval/harness.py`、`quentin/evaluation/harness.py`
  - [x] `SelfImprovementManager` 重复点：`quentin/self_improvement/manager.py`、`quentin/meta/self_improvement.py`
  - [x] `SelfProgrammingEngine` 重复点：`meta_agent/self_programming/engine_v2.py`、`quentin/self_programming/legacy_selfprog/engine.py`、`quentin/self_programming/engine.py`
  - [x] DoD：清单包含每个实现的“是否被 runtime 真实调用”、“是否占位”、“建议保留/废弃”。

- [x] 为每个“重复组件”做一次**主路径决策**（确定 canonical 模块）
  - [x] 选定 canonical `CognitiveLoop`（以 `quentin/cognitive/loop_impl.py` 为准；`quentin/core/*` 已移除）
  - [x] 选定 canonical `SleepLoop`（稳定入口：`quentin/sleep/loop.py`；实现：`quentin/sleep/loop_impl.py`；旧路径仅作为 compat wrapper）
  - [x] 选定 canonical `ImmuneLoop`（建议以 `quentin/immune/loop.py` 为准）
  - [x] 选定 canonical `ExperimentOrchestrator`（以 `quentin/l3/research/experiment_orchestrator.py` 为准）
  - [x] 选定 canonical `EvalHarness`（以 `quentin/l3/research/eval_harness.py` 为准）
  - [x] 选定 canonical `SelfProgrammingEngine`（以 `meta_agent/self_programming/engine_v2.py:SelfProgrammingEngineV2` 为主；`quentin/self_programming/*` 为 legacy/compat）
  - [x] DoD：在 `docs/ARCHITECTURE.md` 写明 canonical 路径 + “不再使用的实现”的迁移/弃用策略。

- [x] 将 runtime/container/CLI 统一指向 canonical 组件
  - [x] `quentin/bootstrap/container.py` 统一注入 canonical 的 loop/manager/orchestrator
  - [x] `quentin/runtime/system.py`（或最终运行时入口）确保只构造/调用 canonical loop
  - [x] `quentin/cli/qctl.py`（如有相关命令）确保调用 canonical 实现
  - [x] DoD：一条端到端演示（例如 `python -m quentin.cli.qctl run-task ...`）不会走到占位/废弃实现。

- [x] 为废弃实现加显式 deprecation
  - [x] 在废弃类/模块顶部抛出 `DeprecationWarning`（或在初始化时 log warning）
  - [x] 保留短期兼容层（import alias）但必须在日志中提示迁移目标
  - [x] DoD：grep “DEPRECATED” 能找到所有废弃入口；且运行时日志能看到提示。

### P0.2 安全内核 SafetyKernel：从“存在”到“不可绕过”

> 目标：所有高影响动作（LLM 调用、工具调用、代码 patch、实验运行、部署/切换环境）必须先走 `SafetyKernel.guard_action`。

- [x] 定义“重要动作”的统一 taxonomy（枚举/常量）
  - [x] action_type 最小集合：`llm_call`、`tool_call`、`code_patch`、`experiment_run`、`deploy`、`storage_write`
  - [x] environment 统一：`sandbox`、`staging`、`prod`
  - [x] domain 统一：`core`、`desktop`、`legal`、`trading`、`cross`
  - [x] risk_level 统一：`low`、`medium`、`high`、`critical`
  - [x] 落点：`quentin/kernel/policy.py:ActionRequest`（或单独 `quentin/kernel/schemas.py`）
  - [x] DoD：全仓库不再出现“各模块自己发明的 action_type 字符串集合”。

- [x] LLM 调用强制 guard
  - [x] 在 `quentin/llm/client.py:call_llm` 前置构造 `ActionRequest(action_type="llm_call")`
  - [x] policy/budget 不通过时：返回可解释错误（并记录 trace）
  - [x] 记录 LLM 使用：tokens/latency/cost（允许先估算/占位，但字段要固定）
  - [x] DoD：任意 LLM 调用都会在 `data/policy_decisions.jsonl`（或统一审计日志）里出现记录。

- [x] Tool 调用强制 guard（即使 ToolManager 先是占位也要把“守门口”打通）
  - [x] 为 `ToolManager` 增加统一调用入口（例如 `invoke(name, args, ctx)`），内部 guard
  - [x] Tool 调用必须写 trace：`TraceEventType.TOOL_CALL`
  - [x] DoD：任何工具执行都能追溯到 trace + policy/budget decision。

- [x] 实验运行强制 guard
  - [x] 在 canonical `ExperimentOrchestrator.run_experiment/dispatch_run` 前置 guard `action_type="experiment_run"`
  - [x] 对 `prod/staging` 设置更保守 policy（默认只允许 sandbox）
  - [x] DoD：实验在非 sandbox 环境运行会被拒绝或自动降级。

- [x] 自编程 patch 全流程 guard + 路径白名单
  - [x] patch 目标文件在 guard 前先经 `PathGuard.ensure_allowed_path`
  - [x] 政策：禁止修改 `quentin/kernel/*`、schema 定义、以及 legal/trading 核心逻辑（按 blueprint）
  - [x] DoD：尝试 patch kernel 文件会被拒绝，且有明确 reason。

- [x] 审计与回滚统一化（最小闭环）
  - [x] 统一审计日志：policy 决策、预算决策、实际执行结果（success/fail）必须关联同一 `action_id`
  - [x] 回滚语义最小版：对 code_patch 支持 `revert(action_id)`（Git 分支或备份文件二选一，但要统一入口）
  - [x] DoD：可以从审计日志定位一次 patch 并一键回滚到上个稳定点（哪怕只是 sandbox）。

### P0.3 三环境（sandbox/staging/prod）与发布门禁（shadow/canary 雏形）

- [x] 定义环境切换/发布的最小协议（结构化对象）
  - [x] variant 运行在 sandbox → staging → prod 的状态机（至少：`created`、`tested`、`approved`、`deployed`、`rolled_back`）
  - [x] DoD：实验/patch 都能引用同一套环境状态字段，不再各自实现。

- [x] 增加 canary/shadow 的占位实现（研究友好接口）
  - [x] `shadow_request`：在不影响主结果的情况下运行候选 variant 并记录指标
  - [x] `canary_request`：按百分比路由到候选 variant（可先仅支持离线模拟）
  - [x] DoD：Research API 至少暴露 `create_experiment/run_experiment/compare_variants/export_results` 的统一入口（哪怕 shadow/canary 是 stub，但 schema 固定）。

### P0.4 持久化存储：替换 in-memory KVStore（否则长期运行不可用）

- [x] 选择 KV 持久化实现（SQLite / JSONL / TinyDB / DuckDB 任选其一）
  - [x] DoD：重启后 eval/experiment/index/task 不丢失。

- [x] 让 `EvalHarness`、`ExperimentOrchestrator`、`Blueprint registry`、`SelfImprovement tasks` 统一使用持久化 KV
  - [x] `quentin/infra/storage/kv_store.py` 变为 file-backed（或新增 `FileKVStore` 并在 container 注入）
  - [x] DoD：`data/` 下存在清晰的持久化文件/DB，且能在文档中说明格式。

### P0.5 运行时韧性（OpenClaw 对标）：Lanes 并发控制 + Abort 取消 + 会话一致性

> 目标：系统进入“多会话/长任务/多工具”后仍然稳定、可取消、可追溯，不出现同会话乱序与资源泄漏。

- [x] 实现 LaneQueue（车道队列）基础设施
  - [x] 落点：`quentin/infra/concurrency/lanes.py`（或 `quentin/runtime/lanes.py`）
  - [x] 能力：`enqueue(lane, coro_fn)` + `set_concurrency(lane, n)` + `get_queue_size(lane)`
  - [x] 约定 lane 命名：`main`、`session:{session_id}`、`subagent`、`cron`
  - [x] DoD：同一 `session_id` 的任务严格串行；不同 session 在 `main` 并发上限内并行。

- [x] 在对外入口强制使用 `session lane`（避免状态竞争）
  - [x] API 入口：`meta_agent/api/server.py`（或未来的 quentin API）按 `session_id` 排队
  - [x] CLI 入口：`quentin/cli/qctl.py`（如带 session 参数）按 `session_id` 排队
  - [x] DoD：对同一 session 并发触发 10 次请求，Trace/Memory 写入不会乱序或互相覆盖。

- [x] 引入“可传播取消语义”（Abort/Cancellation）
  - [x] 落点：`quentin/infra/concurrency/cancellation.py`（或并入 `lanes.py`）
  - [x] 约定：每个 `trace_id/run_id` 绑定一个 cancellation token；Executor/Tools/LLM 调用必须接入
  - [x] DoD：取消一个长任务会停止 LLM 请求、终止正在运行的 subprocess，并写入 trace “aborted”。

- [x] 会话状态写锁（Session write lock）
  - [x] 落点：`quentin/runtime/session_write_lock.py`（文件锁）或使用 SQLite transactional lock
  - [x] 适用范围：任何 session transcript / session-state / run cache 文件（如果存在）
  - [x] DoD：并发写同一 session 文件时不会出现损坏/部分写入；超时可报可解释错误。

### P0.6 工具治理（OpenClaw 对标）：Policy stacking + BeforeToolCallHook + Schema/参数适配

> 目标：工具调用不是“能跑就行”，而是“最小权限、可审计、跨模型稳定、可紧急停机”。

- [x] 定义工具调用的统一入口 + hook 链
  - [x] 落点（择一作为 canonical）：`meta_agent/tools/registry.py` + 执行器层、或 `quentin/tools/manager.py`
  - [x] 最少 hook：`before_tool_call(tool_name, params, ctx)`（可阻断/可改参/可审计）
  - [x] DoD：任意工具执行前都能被 hook 拦截；拒绝理由可追溯到 trace。

- [x] 工具策略叠加（Policy stacking）v1
  - [x] 策略层级：global → agent-role → provider/model → environment(sandbox/staging/prod) → session/group → subagent → sandbox(ro/rw)
  - [x] 策略形式：`allow` / `deny`（支持 `*` 与前缀匹配）+ tool profile（`safe`/`code`/`research`/`admin`）
  - [x] DoD：同一工具在 sandbox 可用、在 prod 默认禁用；subagent 默认 deny 高危工具。

- [x] Schema/参数适配层（跨模型工具调用稳定性）
  - [x] 落点：`quentin/tools/schema_transformer.py`（或 `meta_agent/tools/*`）
  - [x] 最少兼容：根级 `anyOf/oneOf` 合并为 object；清理 Gemini 不支持关键词；兼容 Claude 的参数分组风格
  - [x] DoD：同一组工具 schema 在至少 2 类 provider（本地/远程）下可被 LLM 成功调用（以 mock 测试验证）。

- [x] Tool 执行接入取消语义（Abort）
  - [x] exec/subprocess：取消时必须 terminate/kill，并清理资源（临时文件、后台进程）
  - [x] DoD：取消后系统无僵尸进程；工具 registry 记录 aborted 次数与错误分类。

### P0.7 LLM 韧性（OpenClaw 对标）：Auth Profiles 轮询/冷却 + FailoverReason 分类器

> 目标：把“外部 provider 不稳定/限流/欠费/鉴权失败”从随机故障变成可控系统行为（可观测、可回滚、可自愈）。

- [x] FailoverReason 分类器 v1（错误分桶）
  - [x] 落点：`quentin/llm/failover.py`
  - [x] 覆盖最小集合：`rate_limit(429)` / `billing(402)` / `auth(401/403)` / `timeout(408)` / `format(400)` / `context_overflow(413/too long)`
  - [x] 输出：`reason` + `status` + `provider` + `model` + `profile_id`（可选）+ 原始错误指纹（脱敏）
  - [x] DoD：对一组模拟错误输入（文本/异常对象）能稳定分类，并在 trace 中记录结构化结果。

- [x] AuthProfileStore v1（同模型多 Key/Token 的治理层）
  - [x] 落点：`quentin/llm/auth_profiles.py`
  - [x] 存储：`data/auth_profiles.json`（或 SQLite；但 schema 必须固定）
  - [x] 字段：provider、mode(api_key/token/oauth)、secret_ref（不直接落明文）、label、usage_stats(last_used/cooldown_until/disabled_until/failure_counts)
  - [x] DoD：支持配置 ≥2 个 profile，并能按 provider 读出可用候选列表（过滤过期/被禁用/在 cooldown 的）。

- [x] Profile 选择策略 v1（轮询 + 冷却 + 禁用）
  - [x] 轮询：least-recently-used/round-robin（按 `last_used`）
  - [x] 冷却：`rate_limit/timeout` 等触发短期 cooldown
  - [x] 禁用：`billing/auth` 等触发更长 disabled backoff
  - [x] DoD：连续触发 429/timeout 时 profile 会轮转；触发 402/401 时 profile 会被禁用并跳过。

- [x] LLM client 接入 AuthProfile + Failover（强制走统一入口）
  - [x] 落点：`quentin/llm/client.py`（或 canonical provider client 层）
  - [x] 逻辑：一次请求 =（选 profile）→（调用）→（失败分类）→（mark_failure/cooldown/disable）→（换 profile 重试/上抛触发模型 fallback）
  - [x] DoD：在“远程 provider mock”下可演示：同一模型自动换 key；无法换 key 时能上抛 failover 事件供上层换模型。

- [x] 可观测性与审计：profile 轮转必须可追溯
  - [x] trace 字段：`selected_profile_id`、`failover_reason`、`cooldown_applied_ms`、`retry_count`
  - [x] DoD：可以从审计日志回放一次“限流→轮转→成功”的完整链路。

### P0.8 L3→L2→L1 演化闭环（必须可跑 + 有 benchmark）

> 目标：研究层不仅能“创建实验”，还能“运行实验→做决策→应用到运行时”，并用脚本/指标验证。

- [x] 落地可运行的闭环演示脚本（本地可跑，无外部 LLM 依赖）
  - [x] 文件：`scripts/run_evolution_feedback_loop.py`
  - [x] 覆盖链路：`ResearchInterfaceV3.create_experiment` → `run_experiment` → `decide_and_promote_variant` → `ModelRouter` 规则落盘 → 运行时行为变化验证
  - [x] DoD：`python scripts/run_evolution_feedback_loop.py` 退出码为 0；且能验证 routed model/规则生效（脚本内自检）。

- [x] Meta-Agent 侧 ResearchAPI 去掉 placeholder 存储（直接复用 canonical 研究接口）
  - [x] 文件：`meta_agent/research/api.py`
  - [x] 说明：保持最小稳定 API（create/get/run/export），底层委托 `quentin/l3/research/interface.py:ResearchInterfaceV3`
  - [x] DoD：`scripts/run_meta_research_cycle.py` 可运行（默认不阻塞在 LLM）。

- [x] PatchFlow 从 placeholder 变为可评估/可审计/可选自动 apply 的最小可用流水线
  - [x] 文件：`meta_agent/patchflow/orchestrator.py`
  - [x] 行为：SafetyCheck →（可选）测试 →（可选）SafePatchApplier.apply
  - [x] 默认：`META_AGENT_PATCHFLOW_AUTO_APPLY=0`（只评估/不落盘改代码）
  - [x] DoD：队列中存在 `pending` patch 时，`PatchFlowOrchestrator.run_cycle()` 不 crash，并能把状态写回队列。

- [x] 落地第二条闭环：MemoryFabric recall 策略 A/B → promotion → L1 生效（离线可跑）
  - [x] 文件：`scripts/run_memory_recall_feedback_loop.py`
  - [x] 评测：`EvalHarness` 新增 `memory_fabric` evaluator（deterministic embeddings）
  - [x] promotion：写入 `config/memory_recall_config.json`（默认 gitignore）或由 `QUENTIN_MEMORY_RECALL_DEFAULTS_PATH` 覆盖
  - [x] DoD：脚本退出码为 0；并能证明 `MemoryQuery(mode=auto)` 按 promoted defaults 生效（trace 可见）。

- [x] benchmark：Memory recall micro-benchmark 可跑通并输出 JSONL（hit@k + latency）
  - [x] 文件：`scripts/bench_memory_recall.py`
  - [x] DoD：支持小数据量 `--n 200` 运行，不因 case id 越界崩溃。

### P0.9 Blueprint Radar Spec（`blueprint/spec_v3.json`）覆盖扩展 + 离线证据（可全绿）

> 目标：将 `blueprint.md` 的关键工程原语映射进可扫描的 spec，并用离线 evidence 保证 CI/本地可复现。

- [x] 扩展 `blueprint/spec_v3.json` 覆盖 blueprint.md 关键原语
  - [x] L0：`lanes`/`abort`/`session_write_lock`/`context_budget_compaction`/`auth_profiles_failover`
  - [x] L1：`planner`/`executor`/`tool_governance`/`memory_recall_promotion`
  - [x] L2：`eval_harness`/`observability_overview`/`council_manager`
  - [x] L3：`evolution_strategy_manager`/`budget_controller`
  - [x] DoD：`python -m quentin.cli.qctl blueprint-scan --blueprint-path blueprint/spec_v3.json --emit-evidence` 显示所有 items `score=1.00`。

- [x] 离线证据发射器（traces + baseline experiments）
  - [x] 文件：`scripts/emit_blueprint_spec_v3_evidence.py`
  - [x] CLI：`python -m quentin.cli.qctl blueprint-scan --emit-evidence`
  - [x] 测试：`tests/integration/test_blueprint_scan_can_be_made_green.py`

---

## P1（高优先级）：把 L1/L2 的“占位能力”升级为可实验可评测

### P1.1 Planner：从 EchoPlanner 到 HierarchicalPlanner v1

- [x] 定义 Planner 接口与数据结构（层级计划）
  - [x] Plan schema：goal → milestones → steps（含依赖、回滚点、预估成本）
  - [x] 计划输出必须可序列化并写入 trace（`TraceEventType.PLANNING`）
  - [x] DoD：plan 可以被 executor 逐步执行并逐步写 trace。

- [x] 实现 `HierarchicalPlanner v1`（可先 rule-based/LLM 混合）
  - [x] 支持短期（当前任务）+ 中期（项目级）目标拆分
  - [x] 支持 hard_constraints 与 success_criteria 的显式检查
  - [x] DoD：对同一任务，planner 可作为实验 variant（baseline vs new）。

- [x] 将 planner 接入实验框架（offline eval）
  - [x] 增加 `planner` target_type evaluator（或 runner）
  - [x] DoD：可以 A/B 两个 planner 策略并输出 success/latency/cost 指标对比。

### P1.2 Critic & Self-Correction：从占位到可闭环

- [x] 定义 critic 输出 schema（必须包含：评分、失败原因类别、可执行建议、信心）
- [x] 实现 `Reflexion/Retry` 策略 v1
  - [x] 一次失败后生成修正 plan（或约束/提示）
  - [x] 失败次数阈值后触发 `ImmuneLoop.after_attempt`
  - [x] DoD：同类错误在 2~3 次内可显著改善成功率（以 toy eval 为准）。

### P1.3 Tool & Skill Manager：工具生命周期与安全治理（v1）

- [x] Tool schema（工具元数据、参数、风险级别、domain、版本、owner）
- [x] Tool 注册/启用/禁用/降级策略
  - [x] 被 `ImmuneLoop` 标记异常后可自动 disable（需要 policy 允许）
  - [x] DoD：同一 tool 可以在不同环境启用策略不同（sandbox 开放，prod 保守）。

- [x] 工具调用审计与指标
  - [x] 每次调用记录：输入摘要、输出摘要、latency、错误类型、重试次数
  - [x] DoD：Observability 能统计 tool 成功率/失败率/耗时分布。

### P1.4 Memory Fabric：补齐 update_policy + safe forgetting

- [x] 扩展 Memory schema 支持 blueprint 的 `update_policy`
  - [x] `promotion_rule`、`decay_rule`、`consolidation_batch` 字段落地（schema 固定、不可自改）
  - [x] DoD：每条 MemoryRecord 可追踪其晋升/衰减策略与执行历史。

- [x] 实现 safe forgetting v1
  - [x] STS 定期清理（按时间/访问频次/重要性）
  - [x] MTS 压缩（合并/去重）并记录 `supersedes`/`crystallized_from`
  - [x] LTS 替换（supersedes）而非删除
  - [x] DoD：可运行一次“遗忘/衰减”作业并输出统计与审计记录。

### P1.5 Continual Memory：自动晋升/衰减与 consolidation_batch（补齐闭环）

> 目标：把 `promotion_rule/decay_rule/consolidation_batch` 从“schema 存在”升级到“可自动执行、可追溯、可预算”。

- [x] 增加 `MemoryConsolidationBatchRunner`（或等价组件）统一执行：promotion + decay + consolidation batch
  - [x] 输入：`MemoryFabric` + `MemoryPolicyEngine` + budget/config（max_records / max_duration / max_tokens_est）
  - [x] 输出：结构化报告（promoted/decayed/consolidated 数量 + 耗时 + budget 用量）并写入 trace/audit
  - [x] DoD：可在 sandbox 本地跑一次 batch（CLI），并看到 tier 变化与审计记录。

- [x] 将 batch runner 接入稳定调度入口（CLI）
  - [x] 触发策略：支持 `nightly/weekly/manual` batch name（调度策略后续可接 LoopScheduler/cron）
  - [x] DoD：默认不影响主路径；支持手动触发（`qctl memory-batch-run`）。

- [x] Promotion：STS→MTS 与 MTS→LTS 的自动决策（可 A/B）
  - [x] DoD：构造一批访问次数/年龄符合阈值的记录，batch 后 tier 自动提升，并记录 reason（rule 名 + 命中条件）。

- [x] Decay：STS/MTS 的 TTL/低价值衰减（可解释）
  - [x] DoD：过期记录被标记 decayed（或 archive），不会破坏 recall（能优雅跳过/过滤）。

- [x] 增加单测：promotion/decay/batch 的幂等性与预算上限
  - [x] DoD：重复跑 batch 不会重复晋升同一条；超预算时可中止并留下 partial 报告。

### P1.4A Memory 模块工程增强（参考 OpenClaw 思路）

> 目标：不改写 `blueprint.md` 主线，只把“值得落地的工程增强”拆成可执行任务，提升 **检索质量、稳定性、零配置可用性、研究可测性**。

#### M0：统一 Memory 主路径与 Schema（防碎片化）

- [x] 确认 canonical MemoryFabric 与 SleepLoop
  - [x] MemoryFabric：`quentin/memory/fabric.py:MemoryFabric`
  - [x] SleepLoop：稳定入口 `quentin/sleep/loop.py`（实现 `quentin/sleep/loop_impl.py`；旧路径仅 compat）
  - [x] DoD：runtime/CLI 引用 canonical；旧实现明确 deprecated/compat。

- [x] 统一 MemoryRecord/MemoryTier schema（避免两套语义漂移）
  - [x] 存储/检索层：`quentin/memory/models.py`（dataclass）
  - [x] DoD：MemoryPolicy/MemoryFabric 不再依赖不匹配的 schema（例如 `quentin/memory/policies.py` 只 import `quentin/memory/models.py`）。

- [x] 修正/核对文档中不存在的模块引用（防误导）
  - [x] DoD：TODO/文档中引用的模块路径在仓库中真实存在（如遇重命名则写清迁移关系）。

#### M1：Hybrid Recall 融合检索（Text + Vector）

- [x] 为 `MemoryQuery` 增加检索模式与融合参数
  - [x] 落点：`quentin/memory/models.py:MemoryQuery`（`mode/alpha/k_text/k_vec/min_*`）
  - [x] DoD：同一 query 可强制 `text_only`，不会被自动 embedding 覆盖。

- [x] 在 `MemoryFabric.recall` 实现“两路召回 → union → 归一化重排”
  - [x] 落点：`quentin/memory/fabric.py:MemoryFabric.recall`
  - [x] text 路：SQLite 支持 LIKE/FTS（FTS 走带分数召回）
  - [x] vector 路：embedding 成功时走向量召回；失败优雅降级
  - [x] DoD：`pytest tests/unit/test_memory_hybrid_recall.py -q` 通过。

- [x] Trace/Debug：把融合召回候选与打分写入 trace（可开关）
  - [x] 落点：`quentin/memory/fabric.py`（`query.debug` / `QUENTIN_MEMORY_DEBUG`）
  - [x] DoD：开启 debug 时 trace 里能看到 `text_score/vector_score/combined/alpha`。

- [x] 增加微型 benchmark（可选）：1000/10000 条记忆下 recall 延迟 + hit@k
  - [x] 文件：`scripts/bench_memory_recall.py`
  - [x] DoD：输出到 `data/bench/`（不提交产物）；脚本可在无外部 provider 下运行。

#### M2：SQLite 向量索引“开箱即用”后端（sqlite-vec 方向）

- [x] 新增可选 store：`SqliteVecMemoryStore`（默认关闭，缺扩展自动回退）
  - [x] 文件：`quentin/memory/store_sqlite_vec.py`
  - [x] 选择：`QUENTIN_MEMORY_STORE=sqlite|sqlite_vec|postgres`
  - [x] DoD：未安装扩展时回退到普通 SQLite store（并 warning）。

#### M3：稳定性增强：Embedding Provider Fallback（三级回退）

- [x] 增加 `FallbackEmbeddingClient`（按 env 配置顺序回退）
  - [x] 文件：`quentin/infra/llm/embeddings.py`
  - [x] DoD：任一 provider 挂掉不会阻塞系统，至少可回退到 `text_only`/hybrid 的 text 部分。

- [x] 增加 embedding 健康度与失败率指标（基础结构化快照）
  - [x] 文件：`quentin/infra/llm/embeddings.py:get_embedding_health_snapshot`
  - [x] DoD：Observability 可读取并展示 embedding 健康状态（允许先简化）。

#### M4：sessionDeltas / 增量写入（执行中刷新索引）

- [x] 增量写入机制 v1（受 budget/guard 控制）
  - [x] 文件：`quentin/memory/session_deltas.py` + `quentin/cognitive/loop_impl.py`
  - [x] DoD：`pytest tests/unit/test_session_deltas.py -q` 通过。

#### M5：索引一致性：原子化 reindex / swap

- [x] 向量索引支持“构建临时索引 → 秒级切换”
  - [x] 文件：`quentin/memory/store_sqlite_vec.py:reindex_indexes`
  - [x] DoD：reindex 失败可回滚；召回不 crash。

#### M6：研究可用：A/B 实验与可观测性

- [x] 将 hybrid recall 关键参数做成 Variant（可实验）
  - [x] DoD：离线评测 runner/脚本可对比不同 `alpha/k_text/k_vec/text_mode`。

- [x] Observability：补齐 memory retrieval 维度指标（schema 固定）
  - [x] DoD：`quentin/observability/service.py:get_overview` 包含 memory 相关指标字段（允许先为 0/None，但 schema 稳定）。


### P1.5 Sleep Loop：补齐 blueprint 三类输出

- [x] 语义总结（Semantic Memory）— 已有，但需要标准化产物与指标
  - [x] DoD：每次 sleep 输出 `SleepLoopReport`，包含 tokens/耗时/处理条数/产物条数。

- [x] 程序性记忆（Procedural Memory / Skills）产出 v1
  - [x] 从 clusters/lessons 提取可执行 SOP（结构化步骤）
  - [x] 写入 MemoryFabric（kind=`procedural`）并可被 Skill 系统消费
  - [x] DoD：至少能生成 1 条可复用 procedural memory 并在任务中被引用/调用。

- [x] 训练/对齐数据对（失败→成功、坏计划→好计划）产出 v1
  - [x] 定义数据对 schema（输入、输出、标签、来源 trace）
  - [x] 存储到 `data/training_pairs/`（或 DB）
  - [x] DoD：能导出一个小数据集供离线研究使用。

### P1.6 Knowledge Graph：可用性 + 可视化/导出

- [x] GraphStore 可用性策略
  - [x] 明确：是否要求 Postgres？如果不要求，提供 SQLite/文件型 GraphStore
  - [x] DoD：默认环境下 KG 不应静默退化为 Null（除非明确配置）。

- [x] 增加导出与可视化接口
  - [x] export_subgraph JSON 格式固定（nodes/edges schema）
  - [x] 提供简单 UI/HTML 或 notebook 例子展示图
  - [x] DoD：可从任意 memory_id 导出 2-hop 子图并可视化。

### P1.7 上下文预算与在线压缩（OpenClaw 对标）：ContextWindowGuard + Compaction + History pruning

> 目标：避免“prompt 越跑越长 → 上下文溢出 → 反复失败”；把它变成可自愈事件。

- [x] ContextWindowInfo / ContextWindowGuard v1
  - [x] 落点：`quentin/llm/context_budget.py`
  - [x] 支持从多来源解析窗口：model 自带 / 配置 / agent cap / default
  - [x] 阈值：warn_below 与 hard_min（硬门槛直接 block）
  - [x] DoD：选择窗口过小的模型会被前置拒绝并给出可解释原因。

- [x] Token 估算与 prompt 预算（先粗估，后可替换为精确 tokenizer）
  - [x] 落点：`quentin/llm/context_budget.py:estimate_tokens`
  - [x] DoD：每次 LLM 调用 trace 中记录 `prompt_tokens_est`、`budget_tokens`、`reserve_tokens`。

- [x] 在线 History pruning v1（先裁剪，后压缩）
  - [x] 策略：按 turn 数/recency/重要性裁剪；保证 system + 当前任务 + 关键 memory 不丢
  - [x] DoD：在固定上下文窗口下，长会话仍能继续对话且不会频繁溢出。

- [x] 在线 Compaction v1（溢出前/溢出后触发）
  - [x] 复用现有总结能力：`quentin/memory/processors/summarizer.py`
  - [x] 产物：`running_summary`（结构化/可追溯）写入 STS/MTS，并回填到 prompt
  - [x] DoD：模拟一次 context_overflow 错误后，系统能自动压缩并成功重试一次请求（以单测或 e2e 演示）。

- [x] Compaction reserve tokens（为工具调用/长输出预留）
  - [x] DoD：在工具密集任务中，不会因为没有输出空间导致“工具调用一半失败”。

- [x] Markdown/code fence 安全分块（如有流式输出到聊天渠道）
  - [x] DoD：长输出不会把 fenced code block 拦腰截断；必要时 close+reopen 保持格式正确。

---

## P2（演化闭环）：Skill & Code Evolution + Self-Programming 变成“可验证流水线”

### P2.1 Skill Evolution：补齐 “miner → candidate → test → eval → register/supersedes”

- [x] 统一 SkillCandidate JSON/模型输出格式（建议 JSON schema，避免前缀解析脆弱性）
- [x] Candidate 生成必须包含：代码、测试、适用范围、失败模式、风险说明
- [x] Candidate 自动落地为可运行的模块（写入 `quentin/skills/generated/` 或 `/mutable/skills/`）
  - [x] DoD：候选技能可以被 import 并在 sandbox 运行。

- [x] Candidate 测试流水线 v1
  - [x] 在 sandbox 执行 pytest（隔离环境/临时目录）
  - [x] DoD：每个 candidate 有测试通过/失败报告（结构化）。

- [x] Candidate 评测对比（EvalHarness）
  - [x] 评测维度：成功率、延迟、成本、稳定性（失败率）、安全风险（静态检查）
  - [x] DoD：可在同一 eval suite 中比较 “旧技能 vs 新技能”。

- [x] 晋升与替换治理（supersedes）
  - [x] 定义 supersedes 记录（old_skill_id → new_skill_id，原因、指标对比、审批记录）
  - [x] DoD：一条技能升级能被追溯（谁批准、为何批准、改进了哪些指标）。

### P2.2 Self-Programming：统一入口 + 边界约束 + Patch Report 标准化

- [x] 选择并固化 canonical Self-Programming Engine（写入架构文档）
  - [x] DoD：所有自编程入口只剩一个“主入口”（其余只做兼容层/或废弃）。

- [x] 强制 `/mutable/` + `auto_updatable` 边界（按 blueprint）
  - [x] 在 patch 生成/应用前做路径校验（`PathGuard`）
  - [x] 引入 `auto_updatable` 标记机制（文件头标记/manifest 文件/registry）
  - [x] DoD：不带标记的文件不能被自编程修改。

- [x] Patch 评测流水线补齐（按 blueprint）
  - [x] 单元测试（pytest）
  - [x] 回归测试（至少对相关 suite）
  - [x] 性能测试（可先 stub：记录基准耗时）
  - [x] 静态分析（flake8/bandit；可扩展 ruff/mypy）
  - [x] fuzzing（先把接口留出来，允许后续替换实现）
  - [x] DoD：Patch Report 包含固定字段：tests、static_checks、perf_delta、risk_assessment、coverage（可选）。

- [x] Patch Report 结构化落盘 + 可检索
  - [x] 写入 `data/patch_reports/`（或 DB）并能被 Observability 聚合
  - [x] DoD：仪表盘可统计 patch 通过率/回滚率/平均收益（先 stub 也行）。

- [x] PatchGate / GovernanceCouncil 统一
  - [x] 统一审批 schema（approve/revise/reject + reason + required_modifications）
  - [x] DoD：高风险域（legal/trading）默认 require human gate（哪怕是配置级开关）。

### P2.2A Release Protocol：Patch 的 Shadow/Canary 联动（从“接口存在”到“可用流水线”）

> 目标：把蓝皮书要求的 “Sandbox → Staging/Shadow → Canary → (可选) Prod” 变成可执行链路。

- [x] 将 `SelfProgrammingEngineV2` 的 patch 候选接入 `shadow_request/canary_request`（默认关闭；通过 env 显式开启）
  - [x] 仅当 policy 允许（require_canary / require_human_gate）才可进入 shadow/canary
  - [x] DoD：一次 patch 评估通过后，能产生一个 shadow/canary 记录（带 trace_id + patch_id + fraction）。

- [x] Canary/Shadow 生命周期可观测（先 stub，但 schema 固定）
  - [x] DoD：Observability 能读到 `variant_lifecycle.json` 的 by_status/by_environment 汇总。

- [x] 决策门禁：canary 失败自动 rollback/冻结该 candidate
  - [x] DoD：失败时会生成 ImmuneCase 或 Research 任务，且 candidate 自动进入 cooldown/disabled（需要 policy 允许）。

### P2.3 Blueprint-driven 改进闭环（BlueprintGap Loop）

- [x] 明确 blueprint 单一事实来源（`blueprint.md` vs `blueprints/meta_agent_v3.yaml`）
  - [x] 方案 A：以 YAML 为准，`blueprint.md` 作为说明文
  - [x] 方案 B：以 `blueprint.md` 为准，自动生成 YAML（推荐做一个生成脚本）
  - [x] DoD：CapabilityScanner/GapTracker 不再引用错误的 module/symbol（当前 YAML 多处与真实代码不一致）。

- [x] Gap → ImprovementTask 的标准流程
  - [x] 为每个 gap 生成 task（目标文件、验收测试、风险级别、预算）
  - [x] DoD：SelfImprovementManager 能列出“下一步该改什么（可执行）”。

- [x] Gap 自动验证（至少静态证据 + 最小运行证明）
  - [x] 静态证据：类/函数存在、关键方法存在
  - [x] 运行证据：最小 demo 或 pytest case
  - [x] DoD：capability 状态从 unknown/partial → done 必须附带 evidence。

---

## P3（研究平台化）：实验接口、模型路由策略学习、多领域与可观测性

### P3.1 Research API：create/run/compare/export 统一与稳定

- [x] 统一 Research API 入口（建议：`quentin/research/interface.py:ResearchInterface`）
  - [x] `create_experiment(config)`
  - [x] `run_experiment(experiment_id)`
  - [x] `compare_variants(variant_a, variant_b)`
  - [x] `export_results(experiment_id)`
  - [x] DoD：上述接口在文档中有示例调用，且返回 schema 固定。

- [x] 在线 A/B（小流量）框架雏形
  - [x] routing key（按 domain/task_type/user_id）
  - [x] metrics 收集（success/latency/cost）
  - [x] DoD：能对某个组件（planner/router）进行在线对比（可先模拟）。

### P3.1A Research 闭环：A/B → 决策 → 变更生效（补齐“最后一公里”）

> 目标：从“能跑实验”到“能把实验结果转成可控变更（配置/策略/版本）”，并在安全边界内生效。

- [x] 增加 `decide_and_promote_variant(...)`（或等价 API）
  - [x] 输入：experiment_id + promote_policy（置信区间/最小提升/风险阈值/域限制）
  - [x] 输出：PromotionDecision（winner/loser/reasons/metrics_delta/required_gates）
  - [x] DoD：对一个离线 experiment 能产出稳定决策 JSON，并写 trace/audit。

- [x] 将决策落地到“在线可生效”的配置（但默认只写到 sandbox/staging）
  - [x] ModelRouter：写入/更新 rules
  - [x] Planner/Memory recall：写入 variant 参数（alpha/k/text_mode 等）（先落盘为在线 overrides，后续由组件消费）
  - [x] DoD：同一任务在 promote 后，在线选择策略发生变化（可用单测或 smoke 演示）。

- [x] 动态治理：Promotion 必须经过 SafetyKernel + DomainPolicy
  - [x] DoD：legal/trading 默认 require human gate；desktop 可配置 auto-promote（小流量）。

### P3.2 ModelRouter：数据驱动策略闭环

- [x] 统一 router stats schema（写入 JSONL）
- [x] `ModelRouterOptimizer` 产出的规则能被在线 router 消费
  - [x] DoD：同一 (mode, task_type) 的路由选择会随优化规则变化（可在测试中断言）。

- [x] 引入 bandit/学习策略占位实现（接口优先）
  - [x] DoD：ResearchLayer 可以替换优化算法而不改主系统。

### P3.3 Multi-Agent：固定角色 + 可实验组合（落地到关键决策点）

- [x] 让 `Speed/Safety/Cost/Expert` 角色真正调用 LLM（替换 placeholder 输出）
  - [x] DoD：同一问题能产出 4 个视角输出并被聚合/记录。

- [x] 把 multi-agent 接入 3 个关键点（至少）
  - [x] policy borderline 决策（已部分存在于 `quentin/kernel/policy.py`）
  - [x] patch gate 审批（统一 schema）
  - [x] planner 策略选择（baseline vs candidate）
  - [x] DoD：每次决策都能在 trace 中看到 multi-agent 参与记录。

### P3.4 多领域（Desktop/Legal/Trading）与跨域复用

- [x] 建立 `quentin/domain/legal` 与 `quentin/domain/trading` 的最小骨架
  - [x] domain config：模型白名单、风险上限、允许的自编程范围
  - [x] DoD：domain 目录结构存在且能跑一个 toy task（不要求业务完备）。

- [x] Cross-domain memory/skill 复用机制
  - [x] Memory 的 domain=`cross` 写入与召回策略
  - [x] Skill registry 支持多域引用（desktop→legal 的复用必须可控）
  - [x] DoD：至少 1 条 cross memory/skill 能在两个域任务中命中。

### P3.5 Observability：蓝皮书要求的 dashboard 指标补齐

- [x] 定义指标清单与采集点（代码落点 + schema 固定）
  - [x] 域成功率/错误率/延迟/成本
  - [x] Memory 规模/命中率/晋升与衰减速度
  - [x] Patch 数量/通过率/回滚率
  - [x] 实验数量/通过率/影响区间
  - [x] DoD：`quentin/observability/service.py:get_overview` 返回包含上述字段（允许先为 null/0，但 schema 固定）。

- [x] 把 TODO 指标实现掉（例如 `quentin/observability/dashboard.py` 内的 TODO）
  - [x] DoD：dashboard 输出随真实数据变化（不是全 0）。

---

## P4（后续增强）：证据协议 + 自编程离线化 + 闭环常态化

> 这些是“能跑”之后的关键增强，目标是把系统从 demo 拉到可长期自演化（可审计、可回归、可控）。

- [x] 标准化 blueprint evidence 协议 v1（trace 信号可判定）
  - [x] 为关键 capability 增加 `hints.trace_signals` 并在 tracker 中优先严格匹配（无信号才降级到 heuristic）
  - [x] `Tracer.span` 镜像写入 `data/traces/events.jsonl`（与 JsonlTraceRecorder 统一）
  - [x] DoD：至少 L0/L1/L3 的关键条目可以通过 `trace_signals` 严格判定（不依赖 substring）。

- [x] SelfProgrammingEngineV2 “离线/无 LLM” deterministic coder backend（用于 CI 与本地回归）
  - [x] 后端：`meta_agent/tools/coder/deterministic_backend.py`
  - [x] Engine 保护：deterministic 模式强制写入 `mutable/` 目标文件（避免触碰 core modules）
  - [x] DoD：`pytest tests/unit/test_deterministic_coder_backend.py -q` 通过。

- [x] 把 L3→L2→L1 闭环从脚本提升为集成测试 + 可观测信号
  - [x] 集成测试：`tests/integration/test_evolution_feedback_loop_runs.py`（无外部 provider）
  - [x] promotion 证据：`Tracer.span` → JSONL events（含 `event=promotion_decision`）
  - [x] DoD：`pytest tests/integration/test_evolution_feedback_loop_runs.py -q` 通过。

- [x] Real external LLM 调用（可选启用，默认不影响离线路径）
  - [x] 远程 chat provider：`openai|gemini|deepseek|openrouter`（OpenAI-compatible + Gemini generateContent）
  - [x] 落点：`quentin/llm/client.py`（保持 SafetyKernel guard + ContextBudget + AuthProfile 轮询/冷却 + failover 分类）
  - [x] Smoke script：`scripts/run_real_llm_smoke.py`（按 env 选择 provider/model）
  - [x] Unit tests（无外网依赖）：`tests/unit/test_llm_remote_providers.py`
  - [x] Env-gated integration smoke：`tests/integration/test_real_llm_smoke_env_gated.py`（`REAL_LLM_SMOKE=1` 才会真实外呼）
  - [x] DoD：设置 `LLM_PROVIDER` 与对应 API key 后，`python -m quentin.cli.qctl run-task --input-text "hello"` 可真实调外部 LLM（手动验证）。

## 附录 A：建议的验收测试（可逐项打勾）

- [x] `pytest tests/unit -q` 通过（每完成一个 P0/P1 子模块至少补 1 个 unit test）
- [x] `pytest -q` 全套通过（阶段性 gate）
- [x] `python -m quentin.cli.qctl --help` 可用
- [x] `python -m quentin.cli.qctl run-task --input-text \"hello\"`（或等价命令）能产出 trace + memory 写入
- [x] 执行一次 sleep loop（手动脚本/命令）能产出 consolidation 报告
- [x] 创建并运行一个 experiment（offline）能得到 compare_variants 输出
- [x] 触发一次 immune case（用模拟指标）能生成 ImmuneCase 并写入 research 接口
- [x] 触发一次 self-programming patch（sandbox）能生成 patch report，并在 policy/budget 中留痕

---

## 附录 B：本轮验收记录（2026-02-07）

- （更新 TODO 时请同步更新本段）本段用于记录“真实跑过的验收命令”，避免文档与代码现状脱节。
- `pytest tests/unit/test_memory_hybrid_recall.py -q` ✅
- `pytest tests/unit/test_embedding_fallback.py -q` ✅
- `pytest tests/unit/test_session_deltas.py -q` ✅
- `pytest tests/unit/test_memory_recall_variant.py -q` ✅
- `pytest tests/unit/test_observability_memory_metrics.py -q` ✅
- `pytest tests/unit/test_self_programming_quality.py -q` ✅
- `pytest -q` ✅
- `python -m quentin.cli.qctl blueprint-scan --emit-evidence` ✅
- `python scripts/run_evolution_feedback_loop.py` ✅
- `python scripts/run_memory_recall_feedback_loop.py` ✅
- `python scripts/bench_memory_recall.py --n 50 --db-dir /tmp/quentin_bench_mem_recall --mode hybrid` ✅（输出到 `data/bench/recall_bench.jsonl`，不提交产物）
- `python scripts/run_evidence_audit.py --no-council` ✅
- `python -m quentin.cli.qctl blueprint-scan --blueprint-path blueprint/spec_v3.json` ✅
- `python -m quentin.cli.qctl blueprint-autopatch --blueprint-path blueprint/spec_v3.json --json` ✅
- （手动/可选）`LLM_PROVIDER=openai LLM_MODEL=gpt-4o-mini OPENAI_API_KEY=... python scripts/run_real_llm_smoke.py --prompt "ping"` ✅
