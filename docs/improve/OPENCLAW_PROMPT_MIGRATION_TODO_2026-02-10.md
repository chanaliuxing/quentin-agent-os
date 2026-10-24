# OpenClaw Prompt 平移详细 TODO（可执行清单）

> 日期：2026-02-10  
> 对应计划：`docs/improve/OPENCLAW_PROMPT_MIGRATION_PLAN_2026-02-10.md`  
> 规则：每次只推进一个模块；模块内任务完成后再切下一个模块。

---

## 0. 全局准备（一次性）

- [x] 建立迁移映射模板文档 `docs/improve/openclaw_prompt_mapping_template.md`。
- [x] 新增统一 feature flag 配置项（建议放 `meta_agent/config/feature_flags.py`）：
  - [x] `PROMPT_MIGRATION_M1_SYSTEM_FACTORY`
  - [x] `PROMPT_MIGRATION_M2_EXEC_STYLE`
  - [x] `PROMPT_MIGRATION_M3_SYSTEM_EVENTS`
  - [x] `PROMPT_MIGRATION_M4_TOOL_SUMMARY`
  - [x] `PROMPT_MIGRATION_M5_SUBAGENT_MINIMAL`
  - [x] `PROMPT_MIGRATION_M6_SOP_SKILLS`
  - [x] `PROMPT_MIGRATION_M7_SILENT_PROTOCOL`
  - [x] `PROMPT_MIGRATION_M8_CONTEXT_PRUNING`
- [x] 在 trace 里约定 prompt 迁移事件名（统一前缀 `prompt_migration_*`）。

---

## M1 - System Prompt 工厂化（P0）

### 代码任务
- [x] 新增 `quentin/cognitive/prompt_factory.py`：
  - [x] `build_system_prompt(mode, enabled_tools, runtime_info, skill_context, memory_context, hints)`
  - [x] 支持 `mode in {"full","minimal"}`
  - [x] 章节固定顺序：Identity -> Tools -> Safety -> Skills -> Memory -> Runtime
- [x] 改造 `meta_agent/runtime/council_runtime.py`：
  - [x] `_build_planner_prompt/_build_critic_prompt/_build_judge_prompt` 改为调用 prompt factory（flag 控制）
- [x] 改造 `quentin/cognitive/loop_impl.py`：
  - [x] planner/executor 入口统一接入 factory 输出（flag 控制）
- [x] 保留旧 prompt 路径（flag 关闭时回退）。

### 测试任务
- [x] 新增 `tests/unit/test_prompt_factory.py`：
  - [x] `test_build_full_mode_includes_all_sections`
  - [x] `test_build_minimal_mode_omits_memory_and_docs`
  - [x] `test_prompt_section_order_is_stable`
- [x] 扩展 `tests/unit/test_council_runtime.py`：
  - [x] 验证 council prompt 来自 factory

### 验收标准
- [ ] full/minimal 两种模式输出稳定。
- [ ] 现有 council JSON 提取成功率不低于基线。

### 回滚点
- [ ] 关闭 `PROMPT_MIGRATION_M1_SYSTEM_FACTORY` 即回旧 prompt 逻辑。

---

## M2 - Executor 工具调用风格平移（P0）

### 代码任务
- [x] 改造 `quentin/execution/skill_executor.py` 的 executor system prompt：
  - [x] 平移 OpenClaw 风格：
    - [x] 默认不叙述低风险例行工具调用
    - [x] 复杂/高风险/多步骤时才说明
  - [x] 保留 JSON-only 输出契约
- [x] 在 `record.result` 中增加 `narration_mode` 便于观测。

### 测试任务
- [x] 新增 `tests/unit/test_executor_prompt_style.py`：
  - [x] `test_low_risk_tool_call_prefers_no_narration`
  - [x] `test_high_risk_tool_call_requires_explanation`

### 验收标准
- [ ] tool-only 任务平均回复长度下降。
- [ ] 工具调用成功率不下降。

### 回滚点
- [ ] 关闭 `PROMPT_MIGRATION_M2_EXEC_STYLE`。

---

## M3 - System Events 异步回灌（P0）

### 代码任务
- [x] 新增 `quentin/runtime/system_events.py`：
  - [x] `enqueue_event(session_id, type, payload)`
  - [x] `drain_events(session_id, limit)`
  - [x] 支持“一次性消费”
- [x] 改造 `meta_agent/self_programming/engine_v2.py`：
  - [x] gap 完成、测试通过、治理决策后写入 system event
- [x] 改造 `quentin/cognitive/loop_impl.py`：
  - [x] planner 前读取 pending events
  - [x] 注入系统提示（仅本轮）
- [ ] trace 增加事件：
  - [x] `prompt_migration_system_event_enqueued`
  - [x] `prompt_migration_system_event_injected`

### 测试任务
- [x] 新增 `tests/unit/test_system_events_pipeline.py`：
  - [x] `test_event_injected_next_iteration_and_drained`
  - [x] `test_no_duplicate_injection_after_drain`
- [x] 扩展 `tests/integration/test_run_self_programming_cycle_v2_smoke.py`：
  - [x] 自编程完成后，后续认知轮次出现一次回灌提示

### 验收标准
- [ ] 异步完成结果可在下轮会话稳定感知。
- [ ] 不重复通知。

### 回滚点
- [ ] 关闭 `PROMPT_MIGRATION_M3_SYSTEM_EVENTS`。

---

## M4 - Tool Summary Mapping（P1）

### 代码任务
- [x] 新增 `quentin/tools/summary_map.py`：
  - [x] 工具短摘要（10 词内）
  - [x] `build_tool_summary(tools)` 输出可注入段落
- [x] 改造 `quentin/execution/skill_executor.py`：
  - [x] system prompt 只注入短摘要，不注入完整 schema
- [x] 增加 `help(tool)` 入口：
  - [x] `quentin/tools/manager.py` 增加 schema 查询能力

### 测试任务
- [x] 新增 `tests/unit/test_tool_summary_mapping.py`：
  - [x] `test_summary_is_short_and_stable`
  - [x] `test_help_tool_returns_detailed_schema`

### 验收标准
- [ ] prompt token 占用下降（目标 >= 20%）。
- [ ] 工具参数错误率不升。

### 回滚点
- [ ] 关闭 `PROMPT_MIGRATION_M4_TOOL_SUMMARY`。

---

## M5 - Sub-agent minimal Prompt（P1）

### 代码任务
- [x] 改造 `quentin/multi_agent/coordinator.py`：
  - [x] 父代理 `full`，子代理默认 `minimal`
- [x] 改造 prompt factory：
  - [x] minimal 模式仅保留身份、安全、任务边界、必要工具摘要
- [x] 结合 `quentin/tools/manager.py` 的 `is_subagent` 策略堆叠（prompt 侧读取 `is_subagent`）。

### 测试任务
- [x] 新增 `tests/unit/test_subagent_prompt_mode.py`：
  - [x] `test_subagent_uses_minimal_mode`
  - [x] `test_parent_keeps_full_mode`

### 验收标准
- [ ] 子代理 prompt 明显缩短。
- [ ] 子任务完成率不下降。

### 回滚点
- [ ] 关闭 `PROMPT_MIGRATION_M5_SUBAGENT_MINIMAL`。

---

## M6 - Skill/SOP Prompt 模块化（P1）

### 代码任务
- [x] 在 `quentin/mutable/skills/` 新增 SOP Markdown 样例：
  - [x] `write_patch.md`
  - [x] `review_patch.md`
- [x] 改造 `quentin/skills/manager.py`：
  - [x] 支持按 task 类型挂载 SOP 文本
- [x] planner/executor prompt 中增加“可用 SOP 索引”段落（planner payload 增加 `available_sops`/`suggested_sop`）。

### 测试任务
- [x] 新增 `tests/unit/test_skill_sop_loading.py`：
  - [x] `test_sop_loaded_by_task_type`
  - [x] `test_missing_sop_fallback_to_default_prompt`

### 验收标准
- [ ] 自编程类复杂任务输出结构更稳定。
- [ ] SOP 可独立迭代，不影响主 prompt 框架。

### 回滚点
- [ ] 关闭 `PROMPT_MIGRATION_M6_SOP_SKILLS`。

---

## M7 - Silent Token 协议（P2）

### 代码任务
- [x] 新增 `quentin/runtime/silent_protocol.py`：
  - [x] `SILENT_REPLY_TOKEN`
  - [x] `is_silent_reply(text)`
- [x] 改造 `quentin/cognitive/loop_impl.py`：
  - [x] 对指定内部任务允许 silent token（执行结果拦截）
- [x] 改造 `quentin/cli/qctl.py`：
  - [x] silent token 不打印到用户终端

### 测试任务
- [x] 新增 `tests/unit/test_silent_protocol.py`：
  - [x] `test_silent_reply_is_intercepted`
  - [x] `test_non_silent_reply_not_intercepted`

### 验收标准
- [ ] 空转通知减少。
- [ ] 关键告警不被误吞。

### 回滚点
- [ ] 关闭 `PROMPT_MIGRATION_M7_SILENT_PROTOCOL`。

---

## M8 - Context Pruning 对齐（P2）

### 代码任务
- [x] 改造 `quentin/llm/compaction.py`：
  - [x] 增加 tool result 专项裁剪：head/tail + trimmed marker
  - [x] 保留最近 N 轮消息
- [x] 改造 `quentin/llm/context_budget.py`：
  - [x] 超限时优先 deterministic prune，再做 compact

### 测试任务
- [x] 新增 `tests/unit/test_context_pruning_strategy.py`：
  - [x] `test_keep_recent_turns`
  - [x] `test_tool_result_trim_head_tail`
  - [x] `test_trim_marker_contains_original_size`

### 验收标准
- [ ] 长上下文任务崩溃率下降。
- [ ] 错误关键信息（通常在头尾）保留。

### 回滚点
- [ ] 关闭 `PROMPT_MIGRATION_M8_CONTEXT_PRUNING`。

---

## 9. 逐模块落地流程（必须遵守）

1. 先写 mapping：OpenClaw 原文位置 + Quentin 对应位置 + 变量映射。
2. 再做代码：只改一个模块。
3. 跑该模块最小单测 + 1 条集成。
4. 开 shadow 观测（如适用），确认无明显回归再开默认。
5. 更新本文档状态与变更记录。

---

## 10. 状态追踪（执行中维护）

- M1: `DONE`（prompt_factory + council_runtime + loop_impl + unit tests）
- M2: `DONE`（executor prompt 风格平移 + narration_mode + unit tests）
- M3: `DONE`（队列 + engine 写入 + loop 注入 + unit/integration tests）
- M4: `DONE`（summary_map + help(tool) + unit tests）
- M5: `DONE`（loop + coordinator 子代理 minimal prompt mode + unit tests）
- M6: `DONE`（SOP markdown + manager loading + planner payload + unit tests）
- M7: `DONE`（silent protocol + loop/cli 拦截 + unit tests）
- M8: `DONE`（deterministic pruning + tool result trim + unit tests）
