# Roadmap & TODOs

## Phase 3: Skill Mining closed loop (reuse Self-Programming Engine) - [DONE/EXTENDED]
- [x] Implement DoneCouncil "Online Gateway".
- [x] Ensure MTS memory and Knowledge Graph relations pointing to source traces.

## Phase 4: Graph API + Query capability - [DONE]
- [x] Implement `get_neighbors(memory_id, depth)`.
- [x] Implement LLM-based `explain_link(a,b)`.
- [x] Minimal visualization/export (GraphML).

## Phase 5: Advanced Memory & Reliability (OpenClaw Integration) - [DONE]

### 5.1 Hybrid Retrieval Improvement

- [x] Implement **Hybrid Score Normalization**: Use RRF (Reciprocal Rank Fusion) algorithm in `MemoryFabric.recall`.

- [x] Add **Keyword-weighted Fusion**: Combine text and vector rankings for high-precision recall.



### 5.2 Context Resilience

- [x] Implement **Pre-compaction Flush**: (Implemented in core logic)

- [x] Add **Breakpoint Memory Summarization**: Refine long historical logs into concise actionable lessons.



### 5.3 Local-First Optimization

- [x] Support **Local Vector Acceleration**: Enhanced `MemoryFabric` with auto-detection for `sqlite-vec`.

- [x] Add **Markdown Memory Export**: Automatically export entries to human-readable `.md` files.



### 5.4 Reliability & Auth

- [x] Implement **Auth Profiles Rotation**: Added `AuthProfileManager` with cooldown and success-rate selection.

- [x] **Unified Abort Signal**: Propagate `AbortSignal` through `subprocess.Popen` for instant cleanup.



## Phase 6: Engineering Excellence (Engineering Maturity) - [DONE]

### 6.1 Spatial Awareness & Environment Protection

- [x] **Dynamic File-Tree Context**: Automatically inject `ls -R` results into planner context.

- [x] **Path Self-Correction Hook**: Added middleware to auto-fix hallucinated paths (e.g. `qentin` -> `quentin`).



### 6.2 Precision Editing & Tool Rationality

- [x] **Diff-based Code Editing**: Implemented `fs.search_replace` tool for surgical updates.

- [x] **Non-Interactive Guard**: Hard-block interactive commands (like `nano`, `vim`) in automation.



### 6.3 Deterministic Correction Loop

- [x] **Lint-on-Write (Fast Path)**: Automatically run syntax checks after write operations.

- [x] **System vs Logic Decoupling**: Separate low-level system errors from logic failures in the cognitive loop.



## Phase 7: Production-Ready Evolution Closure - [DONE]

- [x] **Automated Skill & Code Evolution**: Unified Miner -> Store -> Test -> Eval -> Promotion in `AutomatedSkillEvolution`.

- [x] **Non-bypassable Safety Gating**: Unified `SafetyKernel` singleton enforced in LLM and Tool managers.

- [x] **Research-to-Runtime Closure**: Verified `ModelRouter` consumes optimized rules via repo-relative paths.

- [x] **End-to-End Orchestration**: Validated full self-evolution cycle in `scripts/run_quentin_production_cycle.py`.











## Phase 8: OpenClaw 深度对齐（实现细节落地）- [DONE]

- [x] 执行详细任务清单：`docs/improve/OPENCLAW_BLUEPRINT_DETAIL_TODO_2026-02-10.md`
- [x] P0 内环硬化（PathGuard 接管 fs 工具、Tool 风险语义上送、策略冲突修复）
- [x] P1 动态引导（Progressive Pressure、Self-Correction Hints、ModelDialect、Prompt 分层）
- [x] P2 一致性修复（重复 circuit-breaker、skill 统计、timezone-aware 时间）

## Phase 9: Self-Awareness 自身感知闭环 - [DONE]

- [x] 新增 `SelfAwarenessEngine`，将每轮执行结果聚合成 `healthy/warning/critical` 状态
- [x] 接入错误快速分类（`failover_reason`）并生成即时处置建议
- [x] 将自感知状态注入 Planner 与 Executor prompt
- [x] 在 trace 里记录自感知字段，支持后续免疫环/观测消费
- [x] 增补单测覆盖（engine + planner hint + executor hint）

## Phase 10: Claude/Gemini 差距收敛（执行灵敏度）- [DONE]

- [x] `Execution Fidelity`：接入原生 Tool Calling（优先 Ollama tools 模式），移除“LLM 输出 JSON 字符串 + 正则解析”的主路径依赖
- [x] `Incremental Progress`：Executor 升级为 step-by-step 反馈循环（每步工具结果立刻回注到下一步决策）
- [x] `Context Awareness`：任务级目录树快照从“可选提示”升级为“默认上下文”，并补 semantic grep 索引入口
- [x] `Model Intelligence`：Council/Router 引入混合模型路由（小任务本地小模型，复杂重构自动上高阶模型）
- [x] 为上述四项补齐验收测试（tool-calling 成功率、循环中断率、路径幻觉率、复杂任务成功率）

## Phase 11: Blueprint 状态模型统一 - [DONE]

- [x] 统一 `blueprint/tracker.py` 与 `blueprint/gaps.py` 的状态语义为 `missing/partial/unknown/done`
- [x] `qctl blueprint-scan` 展示统一状态与置信度，`blueprint-item` 展示 expected/observed evidence
- [x] `blueprint-autopatch` 与 `task_sources` 复用统一状态，避免多套判定造成冲突
- [x] 增补并通过单测（tracker/gaps/task source/scan/autopatch 链路）

## Phase 12: Tool/Skill 插件化平台（可插拔扩展）- [DONE]

- [x] 工具插件基础设施：`quentin/tools/plugin_loader.py` + `quentin/tools/plugin_schema.py` + `quentin/tools/plugin_cache.py`
- [x] ToolManager 规范化 handler 注册：`quentin/tools/manager.py`（register_tool 同步注册 normalized key）
- [x] 启动期自动扫描与注册：`quentin/bootstrap/container.py`
- [x] 单测覆盖：`tests/unit/test_tool_plugin_loader.py`
- [x] 技能 SOP 插件（`extensions/skills/*/SKILL.md`）扫描与懒加载：`quentin/skills/sop_plugin_loader.py`
- [x] 单测覆盖：`tests/unit/test_sop_skill_plugins.py`
- [x] 技能可执行插件（`manifest.yaml` + `logic.py`）v1：`quentin/skills/exec_plugin_loader.py` + `quentin/execution/skill_executor.py`
- [x] 单测覆盖：`tests/unit/test_exec_skill_plugin.py`
- [x] 输出信任分级中间件化（不仅插件工具，内置工具也可声明 `output_trust`）：`quentin/tools/manager.py`
- [x] 缓存策略升级（按 manifest 声明 key_fields、max_bytes、stale-while-revalidate）

## Phase 12: Self-Awareness 防死循环强化 - [DONE]

- [x] 自感知引擎补充反模式识别（interactive editor / guessed download / repeated tool loop）
- [x] 新增连续无进展计数并注入 `self_awareness_note`
- [x] 运行时控制接入反模式与无进展信号，强制 reflection 与恢复计划覆写
- [x] 补齐并通过单测（self-awareness + cognitive loop antipattern + executor prompt path）

## Phase 13: BrainDaemon 自感知守护联动 - [DONE]

- [x] `CognitiveLoop` 将 warning/critical 自感知快照上送到 `system_events`
- [x] `CognitiveResult` 输出最终 `self_awareness` 快照供 daemon 直接消费
- [x] `BrainDaemon` 在自感知告警时自动开启 guardrail（暂停高风险后台动作 + 入队恢复任务）
- [x] 补齐并通过单测（event emission + daemon guardrail + event retention）

## Phase 14: Guardrail 任务优先级重排 - [DONE]

- [x] `TaskQueue` 增加按 `task_id` 原子领取接口，支持守护层精确调度
- [x] `BrainDaemon` 在 guardrail 期间实现恢复任务抢占（`self_awareness_recovery` 优先）
- [x] `BrainDaemon` 在 guardrail 期间延后高风险维护任务（`blueprint_gap` / `patchflow_backlog`）
- [x] 补齐并通过单测（抢占、延后、非 guardrail 正常领取）

## Phase 15: Guardrail 渐进恢复策略 - [DONE]

- [x] `BrainDaemon` 增加运行模式状态机（`guardrail`/`recover_task_sources`/`recover_patchflow`/`normal`）
- [x] 空闲调度按阶段恢复：先恢复 `task_sources`，再恢复 `patchflow`，最后恢复 `blueprint_autopatch`
- [x] guardrail 触发时自动设置恢复窗口（环境变量可配置恢复时长）
- [x] 补齐并通过单测（阶段切换、能力开关、恢复窗口计算）

## Phase 16: Guardrail 可观测化 - [DONE]

- [x] `BrainDaemon.run_once` 输出 `runtime_mode` 与结构化 `guardrail_state`
- [x] `brain_guardrail_activated` 事件补充模式与窗口状态（便于 planner/运维消费）
- [x] `SystemEventQueue` 格式化输出支持 `runtime_mode` 与剩余秒数字段
- [x] 补齐并通过单测（daemon 输出 + event formatter 展示）

## Phase 17: Guardrail 参数自调优 - [DONE]

- [x] 基于 `self_awareness_recovery` 任务结果引入 guardrail 调优反馈回路
- [x] 支持自动放大/缩小 `cooldown` 与恢复窗口倍率（环境变量可配边界与步长）
- [x] `guardrail_state` 暴露调优倍率与恢复成功率，便于观察调优行为
- [x] 补齐并通过单测（调大、调小、调优后窗口计算）

## Phase 18: Guardrail 状态持久化 - [DONE]

- [x] `BrainDaemon` 增加 guardrail 调优状态持久化文件（默认 `data/runtime/brain_guardrail_state.json`）
- [x] daemon 启动自动加载 `tuning + recovery_outcomes`，重启后保留学习结果
- [x] 在 guardrail 激活与调优更新后自动落盘（原子写）
- [x] 补齐并通过单测（重启恢复、激活落盘）

## Phase 19: Guardrail 调优可解释日志 - [DONE]

- [x] 每次调参记录 `trigger_reason/factor/success_rate/fail_streak/before/after`
- [x] 上送 `brain_guardrail_tuned` system event，供 runtime/planner 侧消费
- [x] `guardrail_state` 暴露 `last_tuning_adjustment` 与 `tuning_history_tail`
- [x] 持久化包含调参历史与最后一次调参信息，重启后可追溯

## Phase 20: Guardrail 调优摘要聚合 - [DONE]

- [x] 新增 `brain_guardrail_tuning_summary` 事件（每 N 次调参汇总一次）
- [x] 汇总字段覆盖窗口大小、平均倍率、触发原因分布、当前 tuning
- [x] `guardrail_state` 增加 `tuning_adjustment_count/last_tuning_summary_at_count`
- [x] 摘要计数状态持久化，避免重启后重复聚合同一窗口

## Phase 21: 调优摘要联动 Intelligence Strict - [DONE]

- [x] 在 `BrainDaemon` 中新增摘要恶化连续计数 `tuning_summary_worsening_streak`
- [x] 当调优摘要连续恶化时，自动触发或延长 `intelligence_strict` 窗口
- [x] 注入 strict 原因 `guardrail_tuning_summary_worsening` 并同步 done council 严格推理环境变量
- [x] 新增联动事件 payload 字段（`trigger/worsening_streak/already_active`）便于回放解释
- [x] 将摘要恶化计数纳入 `guardrail_state` 与持久化状态文件
- [x] 补齐并通过单测（联动触发 + 恶化计数重置）

## Phase 22: Strict 原因回注 Planner/Executor - [DONE]

- [x] `BrainDaemon` 在 strict 激活时同步导出 `QUENTIN_DONE_COUNCIL_STRICT_REASONS`
- [x] strict 结束时恢复/清理 strict reason 环境变量，避免脏状态污染后续轮次
- [x] `CognitiveLoop` 在 planner hints 自动注入 strict 原因提示
- [x] `CognitiveLoop` 在 executor system prompt 自动注入 strict 原因提示
- [x] 补齐并通过单测（env 同步、planner 注入、executor 注入）

## Phase 23: Strict 原因执行链路兜底 - [DONE]

- [x] `CognitiveLoop` 在 executor context 结构化透传 `strict_reasons`
- [x] 即使 prompt factory 关闭，也保留 strict reasons 传递能力
- [x] `SkillExecutor` 每步 fallback 提示注入 `INTELLIGENCE STRICT REASONS`
- [x] 补齐并通过单测（context 透传、executor prompt 注入）

## Phase 24: Blueprint v3.1 大脑升级（Dual-Track + MCP + 认知入口层）- [PLANNED]

- [ ] 执行详细任务清单：`docs/improve/BLUEPRINT_V3_1_BRAIN_UPGRADE_TODO_2026-02-10.md`
