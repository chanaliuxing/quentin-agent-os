# Blueprint v3.1 大脑升级落地 TODO（Project Quentin）

来源：`blueprint.md`（Meta-Agent 工程落地蓝皮书 v3.1 / v3.1+ 认知入口层补强）

日期：2026-02-10

> 目标：给出“升级计划 + 可执行 TODO”，并持续跟踪落地进度。本文件是可执行的落地清单。
>
> 更新：2026-02-11（已开始落地；勾选项反映仓库当前实现状态）
>
> 更新：2026-03-28（补充正式测试计划、分层验收标准，以及“记忆迁移到向量数据库”的当前状态）

---

## 0. 升级目标（v3.1 + v3.1+）

### 0.1 v3.1 三大新增（系统能力面）
1. **双轨能力获取（Dual-Track）**：能用 MCP 工具优先用工具；工具不存在/不适合才走自编程。
2. **MCP 工具学习层（Tool Learning & Integration）**：发现工具、学习 schema、生成例子、写入 TOOL_KNOWLEDGE、统一注册/生命周期/统计。
3. **AI Council 治理**：工具接入/能力变更由多 Agent 投票（Risk/Capability/Cost），人类只提供宪法级规则与总开关。

### 0.2 v3.1+ 认知架构补强（“人脑缺失件”）
4. **认知入口标准化**：Planner 前先做情境判定 + 注意力裁剪（Attention Gating）。
5. **预测驱动执行**：执行前先生成 expected_state，执行后只处理 prediction_error。
6. **情境→技能直连**：高频场景命中高置信 procedural skill 时可反射式执行，失败回退 Planner。
7. **要点记忆（Gist Memory）**：长 Trace 压缩为可复用规律，避免细节污染与记忆膨胀。

---

## 1. 当前代码现状（以仓库 2026-02-10 为准）

### 1.1 已有能力（可复用）
- `quentin/cognitive/loop_impl.py`：CognitiveLoop（Planner Council + Executor + Done + Reflection + ImmuneLoop + Trace/Memory 写入）。
- `quentin/tools/manager.py` + `quentin/tools/plugin_loader.py`：ToolManager + 工具插件化（`extensions/tools/*`）。
- `quentin/council/manager.py` + `config/councils.yaml`：Planner/Done/Reflection Council（多成员 + 仲裁）。
- `quentin/governance/patch_council.py`：Patch 治理（只允许 sandbox + mutable/ 自动 apply）。
- `quentin/memory/fabric.py` + `quentin/sleep/loop_impl.py`：STS/MTS/LTS + SleepLoop consolidation + procedural memory。
- `quentin/immune/loop.py`：ImmuneLoop（失败率/成本/延迟等异常检测）。
- `config/mcp_registry.sample.json` + `meta_agent/self_programming/mcp_integration/*`：已有 MCP registry 元数据加载、discover、invoker（stdio/websocket）、ToolRegistry(另一路) 的雏形。

### 1.2 关键缺口（必须补齐）
**认知入口层缺口**
- 无 `situation_id / attention_pack / expected_state / prediction_error` 的数据结构、管线与指标。
- CognitiveLoop 直接把“原始上下文”喂给 Planner（缺少 attention gating 标准入口）。
- Executor 无 step 级 expected_state 生成与 prediction_error 分类/修复协议。
- SleepLoop 无 gist/situation_profile/expected_state_template 的生成与更新。
- ImmuneLoop 无 prediction_error_rate、context_misclass_rate 等异常维度与降级策略（禁用直连/回退 Planner）。

**工具学习层缺口（对 Quentin 运行时而言）**
- Quentin 主运行时用 `quentin.tools.ToolManager`，但 MCP 工具目前只在 `meta_agent/tools/registry.py` 体系内可用，未接入 ToolManager。
- 无 ToolKnowledge（TOOL_KNOWLEDGE）在 `quentin.memory` 中的统一 schema/写回。
- AI Council 对工具治理（接入/升级 trusted/退役）缺完整闭环（Risk veto 规则缺失）。
- 双轨路由（工具优先/自编程兜底）缺“统一触发点”和“决策树落点”。

### 1.3 记忆迁移到向量数据库的当前状态（2026-03-28）
- 已落地：
  - 主运行时路径已具备 Champion 栈：`quentin/memory/store_champion.py`（`Qdrant + Postgres`）。
  - Container 已支持 `QUENTIN_MEMORY_STORE=champion`。
  - `quentin/memory/store_sqlite_vec.py` 仍保留为本地/备选 indexed backend，不应再被表述成主迁移路径。
  - `quentin/memory/fabric.py` 已支持 `text_only` / `vector_only` / `hybrid` recall、加权重排和 fallback-safe 降级。
  - Champion 相关文档已存在：`docs/memory_champion_stack.md`。
  - Champion readiness 检查已补：`scripts/check_champion_env.py`
  - benchmark / pipeline 工具已具备：`scripts/bench_memory_recall.py`、`scripts/run_memory_slo_pipeline.py`、`scripts/rebaseline_memory_slo.py`。
  - `sqlite-vec` 相关 precheck / 测试存在，但它们描述的是本地备选后端，不等于当前主运行时架构。
- 当前判断：
  - 记忆层不是“尚未迁移”，而是已经进入 Champion rollout 阶段。
  - 当前主线应描述为：`Qdrant` 承担 dense vector search，`Postgres` 承担 text / metadata / source-of-truth。
  - 当前环境快照：`Qdrant` 已 ready，但 `Postgres` 连接信息未配置，因此 Champion 尚未 fully ready。
  - 当前缺口集中在：Qdrant/Champion runtime rollout、SLO 重基线、1M 在线延迟收敛，以及必要时的 cold fallback 策略。
  - 因此本 TODO 中与 Memory 相关的项，必须从“方案设计”改成“rollout / hardening / benchmark / acceptance”视角。

---

## 2. 目标架构（落地视角）

### 2.1 运行时主链路（新增 Perception 子循环）
```
Task -> Perception & Context Layer
     -> (optional) Situation->Skill Router (reflex)
     -> Planner (consumes attention_pack)
     -> Executor (Predictive First per step)
     -> Done/Reflection/Immune
     -> Trace + Memory (gist/tool_knowledge/situation_profile/templates)
```

### 2.2 新增核心对象（建议落地为 JSON-friendly dataclass/Pydantic）
- `SituationAssessment`: `situation_id`, `confidence`, `features`
- `AttentionPack`: `selected_context`, `reduction_ratio`, `debug_refs`
- `ExpectedState`: `markers`, `template_id`, `fallback_skills`
- `PredictionError`: `error_type`, `missing_markers`, `observed_markers`, `severity`
- `SituationSkillRule`: `situation_id -> skill_id`, `min_confidence`, `domain_guard`

### 2.3 新增 Memory kinds（在 `quentin.memory` 里实现）
- `tool_knowledge`
- `situation_profile`
- `gist_memory`
- `expected_state_template`

### 2.4 配置面（建议新增）
- `config/cognitive_policies.yaml`：认知入口层开关与阈值
- `config/mcp_registry.json`：实际 MCP registry（从 sample 拷贝+扩展）
- `config/mcp_security.yaml` 或 `governance.yaml` 新增 `mcp_security`：allow_auto_tool_install、whitelist、dangerous_categories 等
- `config/councils.yaml`：新增 `tool_governance`（Risk/Capability/Cost）与可选 `cognitive_policy_governance`

---

## 3. 分阶段落地 TODO（强建议按顺序做）

> 说明：每个阶段都要求“可开关、可回退、可观测、可测”。高风险域（`legal`/`trading`）默认禁用反射直连与自动工具接入。

### Phase A（P0）: 数据结构 + Trace Plumbing（不改变主行为）
- [x] 定义 Perception & Context Layer 的 schema/类型：
  - 文件：`quentin/cognitive/perception/schemas.py`
  - DoD：可序列化为 dict；能写入 trace；不引入运行时依赖（UI/桌面/浏览器可选）。
- [x] 扩展 Trace 事件/字段：
  - 触点：`quentin/traces/core.py`（如需新增 event_type）或沿用现有 `TraceEventType` 并在 payload 里加字段
  - 触点：`quentin/cognitive/loop_impl.py`（Planner 前记录 perception snapshot）
  - DoD：每次任务至少写一次 perception 事件（即使是空/unknown）。
- [x] 在 `quentin/memory` 增加新 kind 常量与最小读写 helper（先不做自动生成）：
  - 文件：`quentin/memory/kinds.py`、`quentin/memory/tool_knowledge.py`
  - DoD：可 `remember_atomic(..., kind=...)` 写入；可 `MemoryQuery(kind=...)` recall。
- [x] 新增配置骨架：
  - `config/cognitive_policies.yaml`（默认仅最小启用/可回退）
  - `config/mcp_security.yaml`（默认 `enabled: false` / `allow_auto_tool_install: false`）

测试建议：
- `pytest tests/unit -q`（新增 schema/helper 的 unit tests）

### Phase B（P0）: Situation Classifier v0 + Attention Filter v0（Planner 输入标准化）
- [x] 实现 `SituationClassifier`（规则优先）：
  - 输入：`task.metadata` 里的 `ui_tree` / `window_title` / `url` / `logs_excerpt`（可为空）
  - 输出：`situation_id + confidence + features`
  - 文件：`quentin/cognitive/perception/situation_classifier.py`
  - DoD：没有 UI 信息时返回 `unknown_text_only`（或类似），confidence 低但稳定。
- [x] 实现 `AttentionFilter`（启发式裁剪）：
  - 目标：把“可供 Planner 使用的上下文”压到 5%-20%（由 `attention_target_ratio` 控制）
  - 文件：`quentin/cognitive/perception/attention_filter.py`
  - DoD：输出 `attention_pack` + `attention_reduction_ratio`；并把原始上下文仅留在 trace，不直接喂 Planner。
- [x] 接入 CognitiveLoop：
  - 文件：`quentin/cognitive/loop_impl.py`
  - 逻辑：Planner ctx 用 `attention_pack` 替换/包裹原 context；保留 Debug 开关可回放原始信息。
  - DoD：Planner prompt 中明确标注“这是 attention_pack，不是全量原始上下文”。

测试建议：
- 当前落地文件：`tests/unit/test_perception_layer_v0.py`
- 当前落地文件：`tests/unit/test_perception_layer_v0.py`（已补空 metadata、异常输入容错、超大上下文裁剪边界）

### Phase C（P1）: Situation → Skill Router v0（反射执行 + 失败回退）
- [x] 定义 `SITUATION_PROFILE` memory 协议（payload 约定，不强改 DB schema）：
  - kind：`situation_profile`
  - metadata：`situation_id`, `signals`, `recommended_skills`, `stats`
- [x] 实现 `SituationSkillRouter`：
  - 输入：`SituationAssessment` + `SkillManager` + `MemoryFabric`
  - 输出：命中时返回 `skill_id` 与理由；否则 None
  - 安全规则：
    - `legal`/`trading` 默认禁用直连（即使命中）
    - 低置信不直连（`min_confidence`）
  - 文件：`quentin/cognitive/perception/situation_skill_router.py`
- [x] 接入 CognitiveLoop：
  - 在 Planner 前：若命中直连，则生成一个最小 plan（单步 skill），直接交给 Executor
  - 失败时：记录 trace（hit + fail），回退到 Planner 深思
  - DoD：`situation_to_skill_hit_rate` / `success_rate` 可从 trace 统计。

测试建议：
- 当前落地文件：`tests/unit/test_situation_skill_router.py`（domain guard、置信阈值、回退路径）

### Phase D（P1）: Predictive First v0（expected_state + prediction_error 框架）
- [x] 定义 `EXPECTED_STATE_TEMPLATE` memory 协议：
  - kind：`expected_state_template`
  - fields：`situation_id`, `expected_markers`, `fallback_paths`
- [x] 实现 `ExpectationEngine`（v0：模板优先 + 规则兜底）：
  - `build_expected_state(step, situation_id, templates)` -> ExpectedState
  - `compute_prediction_error(expected, observed)` -> PredictionError
  - 文件：`quentin/cognitive/perception/expectation_engine.py`
- [x] Executor 接入（step 级 hooks，v0 proxy）：
  - 文件：`quentin/execution/skill_executor.py`
  - 每步执行前：记录 expected_state（若不可得也要记录 “none”）
  - 每步执行后：采集 observed_markers（v0 可先用“工具结果/错误码”作为 proxy），分类 prediction_error
  - 修复协议（v0）：`error_type -> recovery_skill` 映射表（可配置），执行一次修复再继续/或回退 Planner
- [x] Trace/指标（v0）：
  - `prediction_error_rate`
  - `fallback_to_planner_rate`

测试建议：
- 当前落地文件：`tests/unit/test_expectation_engine_v0.py`（模板命中、误差分类、fallback 策略）

### Phase E（P1）: SleepLoop 产物扩展（Gist + Situation + Templates）
- [x] Gist Memory 生成（v0 规则/启发式）：
  - 从长 Trace/失败->成功样本中抽取 3-10 条 gist 规则
  - kind：`gist_memory`
  - evidence_refs：trace_id 列表
  - 文件：`quentin/memory/processors/gist_extractor.py`、`quentin/sleep/loop_impl.py`
- [x] Situation → Skill Mapping 更新（v0：从 session_delta metadata 提炼）：
  - 从高成功率的 procedural skill 轨迹更新 `situation_profile.recommended_skills`
  - hit_count/success_rate/avg_latency 回写
- [x] Expected State Template 提炼（v0：保守模板，等待真实 observed markers）：
  - 从成功轨迹中提炼 expected_markers（v0 可先由 LLM/规则从 step 结果归纳）
  - 写回 `expected_state_template`
- [x] Planner 注入 gist：
  - 触点：`quentin/cognitive/loop_impl.py` 的 planner ctx 构造
  - DoD：planner ctx 新增 `gist_memories`（top_k=3-5），并记录命中率（可用 trace 统计）。
  - 现状：已在 Planner ctx 注入（开关：`config/cognitive_policies.yaml:enable_gist_injection`）

测试建议：
- 当前落地文件：`tests/unit/test_gist_extractor_v0.py`
- 当前落地文件：`tests/unit/test_sleep_loop_gist_outputs.py`（覆盖 sleep loop 级别写回，不只测 extractor）

### Phase F（P1）: ImmuneLoop 新维度（预测误差一等公民）
- [x] 扩展 `MetricSnapshot`（或 metrics dict）：
  - 新增：`prediction_error_rate`, `unexpected_ui_rate`, `context_misclass_rate`
  - 文件：`quentin/immune/anomaly.py`
- [x] 新增异常检测规则（v0）：
  - prediction_error_rate（prediction_error_spike）升高：优先禁用 `situation_to_skill`，回退 Planner 深思
  - context_misclass_rate 升高：降低 classifier 影响（或进入 degrade_mode）
- [x] CognitiveLoop 响应 ImmuneAction（v0）：
  - 触点：`quentin/cognitive/loop_impl.py`（已有 degrade/self_programming flags）
  - 新增：可关 `enable_situation_to_skill` / `enable_expectation_engine`

测试建议：
- 当前落地文件：`tests/unit/test_immune_loop_prediction_errors.py`

### Phase G（P0/P1）: MCP 工具接入 Quentin ToolManager（Tool Provider v0）
> 目标：让 Quentin 主 Executor 能直接调用 MCP 工具（先实验态），并可被 tool summaries 展示。

- [x] 实现 `MCPToolProvider`（把 registry index -> ToolSpec+handler，默认禁用）：
  - registry index：优先读 `config/mcp_registry.json`（不存在则空）
  - handler：复用 `meta_agent/self_programming/mcp_integration/invoker.py:MCPToolInvoker`
  - 工具命名建议：`mcp.<server_id>.<tool_name>`（保证 ToolManager 规范化兼容）
  - 文件：`quentin/tools/providers/mcp.py`
- [x] Container 启动期注册 MCP 工具（受 `config/mcp_security.yaml` 控制）：
  - 触点：`quentin/bootstrap/container.py`
  - DoD：sandbox 环境可看到 MCP 工具出现在 tool summary block（`Executor._build_tool_summary_block`）。
- [x] 调用统计落 trace（先不入 Memory）：
  - 触点：`quentin/tools/manager.py`
  - DoD：每次 MCP tool call 都能看到 `TraceEventType.TOOL_CALL` 记录。

测试建议：
- 当前落地文件：`tests/unit/test_mcp_tool_provider_disabled.py`
- 当前落地文件：`tests/unit/test_mcp_tool_provider_whitelist_and_backend_injection.py`
- 当前落地文件：`tests/unit/test_mcp_tool_invocation_stub.py`（invoker 不可用降级 + 调用失败映射）

### Phase H（P1）: TOOL_KNOWLEDGE（统一写入 quentin.memory）
- [x] 定义 `tool_knowledge` record 协议：
  - metadata：`tool_id/server/signature/examples/stats/risk_level/tags`
  - kind：`tool_knowledge`
- [x] ToolUsageStats 写回（ToolManager usage sink v0）：
  - 方案 A：在 ToolManager 的 call_tool 成功/失败路径注入一个可选 `usage_sink` 回调
  - 方案 B：Executor 在收到 tool_result 后写回（更简单但不覆盖所有调用）
  - DoD：`tool_knowledge` 记录里 `call_count/success_rate/avg_latency/last_used_at` 会递增。
- [x] ToolLearningModule（示例生成，v0 schema-based）：
  - v0：`quentin/tools/learning/schema_examples.py:synthesize_examples_from_schema`
  - 接入：MCPToolProvider 注册时可选生成 examples（默认关闭），并可被 ToolKnowledge sink 作为初始 examples 写入
  - v1：后续可用 LLM 补齐 examples（input+description+expected_output_type）

测试建议：
- 当前落地文件：`tests/unit/test_tool_knowledge_sink.py`
- 当前相邻验证：`tests/unit/test_executor_tool_knowledge_prompt.py`
- 当前落地文件：`tests/unit/test_tool_knowledge_sink.py`（已补失败调用写回与 stats 退化路径）

### Phase I（P1）: AI Council 工具治理（Risk veto + allow_auto_tool_install）
- [x] 新增 `tool_governance` council：
  - 配置：`config/councils.yaml` 增加 `tool_governance`（roles：RiskAgent/CapabilityAgent/CostAgent）
  - 实现：`quentin/governance/tool_council.py`
- [x] 聚合规则（必须包含 Risk veto，v0 为纯函数 + gate 可插拔）：
  - RiskAgent == REJECT -> 总体 REJECT
  - 否则按多数 APPROVE / SANDBOX_ONLY / REJECT
  - DoD：符合 `blueprint.md 5.3.2` 的简化流程。
- [x] 静态初筛（Safety Kernel / mcp_security，v0）：
  - `official_scopes` / `whitelist` / `dangerous_categories`（filesystem/shell/browser）
  - allow_auto_tool_install 默认 false（避免工具爆炸）
- [x] 工具生命周期管理（v0：meta.governance_state + lifecycle=candidate，后续可升级映射）：
  - experimental/trusted/deprecated（与 Quentin `ToolSpec.lifecycle` 做最小映射或单独字段）
  - trusted 工具才允许在 staging/prod 暴露给 Planner/Executor（策略可配）

测试建议：
- 当前落地文件：`tests/unit/test_tool_governance_aggregate_veto.py`
- 当前落地文件：`tests/unit/test_tool_governance_gate.py`（已补 council manager / gate 接线层测试）

### Phase J（P1/P2）: 双轨能力获取（Tool-first, selfprog fallback）
- [x] 统一“Gap”结构（给路由器/治理层用，v0）：
  - 包含：gap_text、domain、risk、evidence（失败 trace/tool_not_found 等）
  - 文件：建议 `quentin/meta/capability_gap.py`
- [x] 实现 Dual-Track Router（v0 rule-based，可插拔）：
  - 规则：标准外部服务 -> MCP；否则 -> self_programming
  - 触发点：
    - ToolManager tool_not_found（可选）
    - Reflection/Immune 标记 “missing capability”
    - BlueprintGapAutoPatcher（选做：当 gap 与外部工具强相关时先走 MCP）
  - 现状：在 CognitiveLoop attempt 后从 executor step_records 提取 tool_not_found/tool_blocked gap 并写入 kind=capability_gap（不做自动接入/自动 patch）
- [x] “工具接入”与“自编程 patch”都必须走治理（v0：先做 governed request queue，不直接执行）：
  - 工具：Tool Council
  - Patch：Patch Council（已有）
  - 现状：新增 `config/dual_track.yaml`（默认关闭）；开启后在检测到 gap 时写入 `kind=capability_acquisition_request`（工具路径走 ToolGovernanceGate，patch 路径标记 requires_patch_governance）

测试建议：
- 当前落地文件：`tests/unit/test_dual_track_router_v0.py`
- 当前落地文件：`tests/unit/test_dual_track_acquirer_v0.py`（已补 `tool_blocked` / governed queue / `requires_patch_governance` 分支）

### Phase K（P2）: Dashboard & 指标（认知入口层观测）
- [x] 指标汇总（trace -> metrics，v0）：
  - situation_confidence 分布、context_misclass_rate
  - attention_reduction_ratio、attention_hit_rate
  - prediction_error_rate、top_error_types、fallback_to_planner_rate
  - situation_to_skill_hit_rate/success_rate
  - gist_count/gist_hit_rate
- [x] 在现有 dashboard/脚本里暴露（最小可用即可，v0）：
  - 触点候选：`scripts/metrics_summary.py`、`scripts/render_overview_dashboard.py`、`quentin/dashboard/*`
  - 现状：新增 `scripts/cognitive_metrics_summary.py`（从 `data/traces/events.jsonl` 汇总 perception/reflex/gap + prediction_error_rate）

### Phase L（P0/P1）: Blueprint Spec 同步到 v3.1（让 gap 扫描可观测）
> 目标：`blueprint.md` 已升级到 v3.1，但结构化 spec 仍偏 v3；需要把新增能力项落到 spec，才能被 `qctl blueprint-scan`、auto-patch、evidence audit 消费。

- [x] 新增或升级 spec：
  - 方案 A：新增 `blueprint/spec_v3_1.json`（推荐，避免破坏既有 v3 指标）
  - 方案 B：直接扩展 `blueprint/spec_v3.json`
- [x] 将 v3.1 新能力项写入 spec（至少包括）：
  - Perception & Context Layer（situation/attention/expectation/router）
  - TOOL_KNOWLEDGE / SITUATION_PROFILE / GIST_MEMORY / EXPECTED_STATE_TEMPLATE
  - MCP Tool Learning & Integration Layer（discovery/learning/adapter/registry/stats）
  - AI Council（工具治理流程与 veto 规则的 evidence）
- [x] 为新增 spec item 补齐 hints（modules/targets/trace_signals）：
  - 触点：`quentin/blueprint/spec.py`、`quentin/blueprint/llm_probes.py`（如果需要 probe）
  - DoD：`scripts/blueprint_coverage_report.py` 能显示这些项的状态；缺口能被 auto-patcher 识别。
  - 备注：`qctl blueprint-scan --blueprint-path blueprint/spec_v3_1.json`

### Phase M（P1/P2）: Memory 向量数据库迁移 rollout（Champion / Qdrant 主线）
> 目标：把 Memory 从“代码层已具备多后端”推进到“Champion 栈（Qdrant + Postgres）真正成为运行时基座，并有 SLO/验收闭环”。

- [x] Memory API 与数据模型支持向量化：
  - `MemoryQuery.mode`: `auto | text_only | vector_only | hybrid`
  - `MemoryRecord.vector`、hybrid rerank、trace debug 已落地
- [x] Champion 运行时后端已实现：
  - `quentin/memory/store_champion.py`
  - `quentin/memory/champion/qdrant_rest.py`
  - 环境选择：`QUENTIN_MEMORY_STORE=champion`
- [x] 备选 indexed backend 已实现：
  - `quentin/memory/store_sqlite_vec.py`
  - `sqlite-vec` 仅作为本地/备选路径，不是当前主迁移叙事
- [x] benchmark / SLO pipeline 已落地：
  - `scripts/check_champion_env.py`
  - `scripts/bench_memory_recall.py`
  - `scripts/run_memory_slo_pipeline.py`
  - `scripts/rebaseline_memory_slo.py`
- [x] Runtime 环境启用 Champion：
  - DoD：目标环境显式启用 `QUENTIN_MEMORY_STORE=champion`
  - DoD：Qdrant ready，且 `ChampionMemoryStore` 不是降级到纯 Postgres / client fallback
  - DoD：observability 能看见当前 vector backend 为 `qdrant`
  - 当前落地文件：`scripts/check_champion_runtime.py`（严格校验 store=ChampionMemoryStore + vector.backend=qdrant + ready）
  - 当前落地文件：`tests/integration/test_check_champion_runtime_runs.py`
- [x] 新增 memory kinds 的迁移回归验证：
  - `gist_memory` / `tool_knowledge` / `situation_profile` / `expected_state_template` 在 vector recall 与 hybrid recall 下都能命中
  - 不接受“迁移后只有 text-only 能找回”
  - 当前落地文件：`tests/integration/test_memory_kind_recall_regression_large.py`
- [x] 1M 在线延迟差距收敛：
  - 当前目标应以 Champion/Qdrant 路径为准，不再以 `sqlite-vec` 作为主 benchmark 解释
  - DoD：明确在线档 / 离线档边界，或完成热/冷分层与索引策略升级后再收敛目标
  - 当前落地文件：`config/memory_runtime_tiers.json`（在线/离线边界）
  - 当前落地文件：`scripts/check_memory_runtime_tiers.py`、`tests/integration/test_check_memory_runtime_tiers_runs.py`
- [x] SLO 重基线与门禁接入：
  - Champion rollout 后，重跑 benchmark 并更新 `config/memory_recall_slo*.json`
  - 在 pipeline / verify / canary 中纳入“Qdrant/Champion 未生效则失败”的 guard
  - 当前落地文件：`config/memory_recall_slo_champion.json`
  - 当前落地文件：`scripts/run_memory_slo_pipeline.py`（新增 `backend=champion` + `--fail-on-slo`）
  - 当前落地文件：`tests/integration/test_run_memory_slo_pipeline_champion_runs.py`
  - 当前落地文件：`scripts/qa/preflight_verify_system.sh`（`QUENTIN_REQUIRE_CHAMPION=1` 时强制 guard）
  - 当前落地文件：`scripts/qa/run_verify_system_test_suite.sh`（Champion 模式联动）
  - 当前落地文件：`scripts/run_canary_brain_once.py`（Champion guard）

测试建议：
- 单元：
  - `tests/unit/test_memory_hybrid_recall.py`
  - `tests/unit/test_memory_recall_variant.py`
  - `tests/unit/test_embedding_fallback.py`
- 集成：
  - `tests/integration/test_check_champion_env_runs.py`
  - `scripts/run_memory_champion_smoke.py`
  - `tests/integration/test_bench_memory_recall_runs.py`
  - `tests/integration/test_bench_memory_recall_slo_runs.py`
  - `tests/integration/test_run_memory_slo_pipeline_runs.py`
- 验收重点：
  - `vector_only` / `hybrid` 都要测
  - “Champion/Qdrant 生效”与“fallback 还能跑”必须分开判定

---

## 4. 验收口径（必须写清楚，避免“做了但不可用”）

### 4.1 最小验收（MVP）
- CognitiveLoop 每次任务都有 perception 记录（situation + attention_pack + ratio）。
- Planner 明确只消费 attention_pack；原始上下文只在 trace 中可回放。
- situation->skill 直连在 sandbox 可跑通 1-2 个场景，失败自动回退 Planner。
- Executor 每步都有 expected_state/prediction_error 字段（哪怕 v0 是 proxy）。
- SleepLoop 至少能生成 gist_memory，并能被 planner recall 注入。

### 4.2 安全验收（必须）
- `legal`/`trading` 默认禁用直连与自动接入新 MCP 工具。
- MCP 高危类别工具默认 sandbox_only 或拒绝，必须经 Tool Council 才能升 trusted。
- 任意新能力开关都可通过配置关闭（fail safe）。

### 4.3 记忆向量库迁移验收（必须单列）
- 功能验收：
  - `tool_knowledge` / `gist_memory` / `situation_profile` / `expected_state_template` 可正常写入并可 recall。
  - recall 在 `text_only` / `vector_only` / `hybrid` 三种模式下行为清晰、可解释、可调试。
- 运行时验收：
  - 当要求 Champion 时，Qdrant / Postgres 任一关键依赖未准备好必须显式暴露，不允许静默伪通过。
  - observability 必须能区分当前是 `qdrant`、Postgres fallback、还是本地备选后端。
- 性能验收：
  - benchmark 与 SLO 文件存在，且与当前 backend 对齐。
  - 1M 档位如果仍未达在线目标，文档和 pipeline 必须明确标注为 offline evaluation tier。
- 回归验收：
  - 认知入口层新增 memory kinds 的召回质量不能因向量库迁移而退化到只能依赖关键词命中。

### 4.4 分层验收矩阵（从大骨架到小骨架）
- L0 基座：
  - 配置可开关、trace 可回放、memory store 可切换、失败可降级。
- L1 认知入口层：
  - perception snapshot 稳定产出；Planner 默认消费 `attention_pack`；prediction_error 可观测。
- L2 技能/工具层：
  - reflex 命中可执行，失败能回退；MCP 工具可注册、可调用、可审计。
- L3 记忆学习层：
  - gist / tool_knowledge / expected_state_template / situation_profile 可写回、可召回、可统计。
- L4 治理层：
  - Tool Council / Patch Council 的 veto、生效范围、降级动作可验证。
- L5 运行环境层：
  - Champion readiness、benchmark、SLO pipeline、backend guard 可重复运行。

---

## 5. 已确认的关键决策（模块化/可插拔）
1. **命名与归属**：Perception & Context Layer 落在 `quentin/cognitive/perception/*`。
2. **MCP 体系归一**：对外以 Quentin 的 ToolProvider 方式接入（可插拔），短期复用 `meta_agent/self_programming/mcp_integration/*` 作为后端实现；后期可替换为 `quentin/tools/mcp/*`，但不改上层调用接口。
3. **工具生命周期语义**：治理状态与 `ToolSpec.lifecycle` 解耦（可插拔策略层）。治理状态使用 `experimental/trusted/deprecated`（存到 `ToolSpec.meta` 或独立 store）；`ToolSpec.lifecycle` 继续保持现有集合（`active/candidate/deprecated/disabled`），通过映射兼容旧逻辑。

### 5.1 模块化与可插拔硬约束（落地必须遵守）
- **所有 v3.1 新增模块必须有稳定接口**（Protocol/ABC），并支持通过配置切换实现（rules/light-llm/heavy-llm）。
- **组合优于继承**：Perception 子循环由一个 `PerceptionContextLayer` 组合多个子模块（classifier/filter/expectation/router），每个子模块都可为空或替换。
- **后端可替换**：MCP 接入必须有 `MCPBackend` 抽象，默认实现可以包一层 `meta_agent/.../invoker.py`，但不允许上层直接 import meta_agent。
- **策略可替换**：Tool governance / situation->skill / prediction_error->recovery 映射必须走策略对象或配置文件，不允许散落 hardcode。
- **记忆后端可替换但验收不可降级**：允许 `champion` / `sqlite_vec` / `postgres` / `sqlite` 切换，但新增 memory kinds 与 hybrid recall 的验收口径必须一致。

建议接口草案（用于后续实现）：
- `SituationClassifier.classify(ctx) -> SituationAssessment`
- `AttentionFilter.build_attention(ctx, situation) -> AttentionPack`
- `ExpectationEngine.build_expected(step, situation, ctx) -> ExpectedState`
- `ExpectationEngine.compute_error(expected, observed, ctx) -> PredictionError`
- `SituationSkillRouter.route(situation, ctx) -> Optional[SkillInvocation]`
- `ToolProvider.register(tool_manager, cfg) -> list[str]`
- `ToolUsageSink.record(call, result) -> None`
- `ToolGovernanceGate.decide(candidate, context) -> GovernanceDecision`

---

## 6. 正式测试计划（2026-03-28 补齐）

### 6.1 测试目标
- 证明 v3.1 不是“模块存在”，而是“主链路、记忆、治理、运行环境”四条线同时可用。
- 证明记忆向量化迁移没有破坏认知入口层新增 memory kinds 的召回与写回。
- 证明高风险开关、fallback、governance veto 在失败路径上同样成立。

### 6.2 测试分层
- 单元测试：
  - 覆盖 schema、router、expectation、tool knowledge sink、memory recall scoring、governance 聚合纯逻辑。
- 集成测试：
  - 覆盖 CognitiveLoop 主链路、MCP provider 注册、Champion/Qdrant readiness、benchmark pipeline、SLO pipeline。
- 端到端/验收测试：
  - 覆盖 1-2 个 sandbox 场景中的 perception -> reflex/planner -> executor -> memory writeback -> metrics 汇总闭环。

### 6.3 按模块测试清单
- A/B 认知入口层：
  - 现有：`tests/unit/test_perception_layer_v0.py`
  - 现有：`tests/unit/test_situation_skill_router.py`
  - 现有：`tests/unit/test_expectation_engine_v0.py`
- E/H 记忆学习层：
  - 现有：`tests/unit/test_gist_extractor_v0.py`
  - 现有：`tests/unit/test_tool_knowledge_sink.py`
  - 现有：`tests/unit/test_executor_tool_knowledge_prompt.py`
  - 现有：`tests/unit/test_sleep_loop_gist_outputs.py`
- J 双轨路由：
  - 现有：`tests/unit/test_dual_track_router_v0.py`
  - 现有：`tests/unit/test_dual_track_acquirer_v0.py`
- M Memory 向量库：
  - 现有：`tests/unit/test_memory_hybrid_recall.py`
  - 现有：`tests/unit/test_memory_recall_variant.py`
  - 现有：`tests/unit/test_embedding_fallback.py`
  - 现有：`tests/integration/test_check_champion_env_runs.py`
  - 现有：`scripts/run_memory_champion_smoke.py`
  - 现有：`tests/unit/test_champion_store_policies.py`
  - 现有：`tests/integration/test_bench_memory_recall_runs.py`
  - 现有：`tests/integration/test_bench_memory_recall_slo_runs.py`
  - 现有：`tests/integration/test_run_memory_slo_pipeline_runs.py`
  - 现有：`tests/integration/test_check_champion_env_runs.py`（严格失败路径 + ready 成功路径）
  - 现有：`tests/integration/test_champion_store_end_to_end.py`（Champion store 级向量召回与回退路径）
  - 当前落地文件：`scripts/run_memory_champion_scale.py`（可配置生产参数：`--n-records/--queries/--workers` + 命中率/延迟门禁）
  - 当前落地文件：`tests/integration/test_champion_store_scale_e2e.py`（ready 路径 + fallback 路径）

### 6.4 执行顺序
1. 先跑单元：认知入口层、memory recall、tool knowledge、dual-track。
2. 再跑集成：`check_champion_env.py`、Champion/Qdrant smoke、benchmark、SLO pipeline、MCP provider 注册。
3. 最后跑 sandbox 验收：最小闭环场景和 fail-safe 场景。

### 6.5 通过门禁
- 单元测试必须全绿。
- 集成测试中：
  - backend guard 必须能在 Champion 环境不满足时失败；
  - readiness 检查必须能在环境满足时通过；
  - benchmark / SLO pipeline 至少完成一次无错误执行。
- 验收场景中：
  - perception 记录、attention_pack、prediction_error、memory writeback、metrics 汇总缺一不可。
- 任何新增模块如果只有 happy path 测试，没有 fallback / veto / degrade 测试，不算完成。

### 6.6 推荐执行命令
- `pytest tests/unit/test_perception_layer_v0.py -q`
- `pytest tests/unit/test_gist_extractor_v0.py tests/unit/test_tool_knowledge_sink.py tests/unit/test_dual_track_router_v0.py -q`
- `pytest tests/unit/test_memory_hybrid_recall.py tests/unit/test_memory_recall_variant.py tests/unit/test_embedding_fallback.py -q`
- `pytest tests/integration/test_check_champion_env_runs.py -q`
- `pytest tests/integration/test_champion_store_end_to_end.py -q`
- `pytest tests/integration/test_bench_memory_recall_runs.py tests/integration/test_bench_memory_recall_slo_runs.py tests/integration/test_run_memory_slo_pipeline_runs.py -q`
- `python scripts/run_blueprint_v3_1_landing.py`（正式落地入口，含 strict env check + 关键链路测试 + Champion scale 验收）

### 6.7 已补齐测试项
- 当前落地文件：`tests/unit/test_cognitive_immune_action_linkage.py`（覆盖 prediction_error_spike 下感知层开关被免疫动作实际关闭）
- 当前落地文件：`tests/unit/test_sleep_loop_gist_outputs.py`（已补 situation_profile / expected_state_template 写回深断言）
- 当前落地文件：`tests/integration/test_memory_kind_recall_regression_large.py`（新 memory kinds 大样本召回质量回归）
- 当前落地文件：`tests/integration/test_champion_store_scale_e2e.py` + `scripts/run_memory_champion_scale.py`（高并发/大规模 ready+fallback 压测）

### 6.8 正式落地执行记录（2026-03-28）
- 执行命令：`python scripts/run_blueprint_v3_1_landing.py`
- 结果：`ok=true`
- 报告文件：`data/landing/blueprint_v3_1_landing_report.json`

### 6.9 P0 检索调优记录（2026-03-28）
- 问题：Champion benchmark 出现 `hybrid_keyword_starvation`（hybrid_text_hit 偏低）
- 调优项：
  - `quentin/memory/fabric.py`：
    - 结构化查询 token（如 `[CODE:E00123]`）识别
    - hybrid fast path 在“无关键 token 命中”时强制 fallback 到 text-only 搜索
    - 结构化查询下提升 lexical 权重与 keyword anchor 下限
  - 回归测试：`tests/unit/test_memory_hybrid_recall.py`（新增 structured query starvation 用例）
- 验收基线（Champion, n=300, runs=1）：
  - `text_only hit@k=1.0`
  - `vector_only hit@k=1.0`
  - `hybrid hit@k=1.0`（`hit_text@k=1.0`, `hit_vec@k=1.0`）
- 结果：`scripts/bench_memory_recall.py --backend champion ...` SLO check PASS

### 6.10 P1/P2 一次性落地补充（2026-03-28）
- Sleep 学习质量去噪：
  - `quentin/memory/processors/situation_profile_builder.py` 新增 `min_observations/min_success_rate`
  - `quentin/memory/processors/expected_state_template_builder.py` 新增 `min_observations/min_success_rate`
  - `quentin/sleep/loop_impl.py` 接入阈值环境变量：
    - `QUENTIN_SLEEP_PROFILE_MIN_OBSERVATIONS`
    - `QUENTIN_SLEEP_PROFILE_MIN_SUCCESS_RATE`
    - `QUENTIN_SLEEP_TEMPLATE_MIN_OBSERVATIONS`
    - `QUENTIN_SLEEP_TEMPLATE_MIN_SUCCESS_RATE`
  - 测试：`tests/unit/test_situation_profile_builder_v0.py`、`tests/unit/test_expected_state_template_builder_v0.py`
- 认知策略调参建议器：
  - 新增脚本：`scripts/propose_cognitive_policy_tuning.py`（根据 trace 指标产出建议，支持 `--apply`）
  - 测试：`tests/integration/test_propose_cognitive_policy_tuning_runs.py`
- 正式落地入口增强：
  - `scripts/run_blueprint_v3_1_landing.py` 新增 steps：
    - `cognitive_policy_tuning_proposal`
    - `champion_runtime_strict_check`
    - `memory_runtime_tier_boundary_check`
    - `champion_slo_rebaseline_gate`
