# OpenClaw 对齐落地 TODO（不改架构，仅补实现细节）

> 日期：2026-02-10  
> 目标：严格遵循 Quentin 现有 Blueprint 架构，不重构层次，只做实现层增强。  
> 范围：`quentin/*`、`meta_agent/*`、`tests/*`。  
> 约束：先补“内环硬拦截”，再补“中环稳定性”，最后补“外环动态引导”。

---

## 0. 执行原则（必须遵守）

- [ ] 不新增新的顶层架构层，不改变 Runtime/CognitiveLoop/ToolManager 的主职责边界。
- [ ] 所有增强以“可插拔 + 默认安全”为前提（开关默认保守）。
- [ ] 每个任务必须包含：代码改动点、测试、验收标准、回滚点。
- [ ] 每个 PR 只覆盖同一优先级批次（P0/P1/P2），避免混改。

---

## P0（必须先做）内环硬化：安全与可控性

### P0-1 文件工具统一接入 PathGuard（封死路径绕过）

状态：`DONE`

改动文件：
- [x] `quentin/tools/filesystem.py`
- [x] `quentin/kernel/path_guard.py`（仅必要时补 helper，不改现有语义）
- [x] `tests/unit/tools/test_filesystem_guard.py`（新建）

实现步骤：
- [x] 删除 `filesystem.py` 里仅靠 `Path.resolve()` 和字符串 `startswith()` 的路径判定路径。
- [x] 在 `fs_read_file/fs_write_file/fs_search_replace` 中统一调用 `PathGuard.ensure_allowed_path(rel_path)`。
- [x] 对绝对路径输入保持拒绝（沿用 `PathGuard` 行为），错误信息标准化为 `path_denied:*`。
- [x] 对 `path` 参数为空、非字符串、非法路径统一返回结构：`{"status":"error","error":"..."}`。

测试：
- [x] 新增：`test_fs_write_rejects_escape_path()`。
- [x] 新增：`test_fs_read_rejects_absolute_path()`。
- [x] 新增：`test_fs_search_replace_rejects_outside_allowed_roots()`。
- [x] 新增：`test_fs_allows_mutable_and_quentin_skills_paths()`。

验收标准：
- [x] `../../`、绝对路径、repo 外路径全部被拒绝。
- [x] 允许目录严格等同 `PathGuard.allowed_roots`。
- [x] 不影响现有可写路径（`mutable/*`, `quentin/skills/*` 等）。

回滚点：
- [x] 保留旧逻辑于临时分支；主分支仅保留 PathGuard 版本。

---

### P0-2 Tool 调用风险语义上送（SafetyKernel 可看见“危险内容”）

状态：`DONE`

改动文件：
- [x] `quentin/tools/manager.py`
- [x] `quentin/kernel/policy.py`（若需要读取新增 metadata 字段）
- [x] `tests/unit/test_tool_manager_policy_and_ctx.py`

实现步骤：
- [x] 在 `_guard_tool_call_or_raise()` 的 `ActionRequest.metadata` 中新增风险摘要字段：
  - [x] `tool_name`
  - [x] `params_keys`
  - [x] `target_path`（若存在 path/file/target_path）
  - [x] `command_head`（若存在 command，只取首 token）
  - [x] `command_flags`（仅安全白名单提取）
  - [x] `is_destructive_candidate`（如匹配 `rm -rf`, `chmod -R 777`, `dd`, `mkfs`）
- [x] 禁止把完整敏感参数原文写入审计（仅摘要/脱敏）。
- [x] 在 audit trace 中补充上述摘要，便于复盘。

测试：
- [x] 新增：`test_tool_guard_includes_command_head_in_metadata()`。
- [x] 新增：`test_tool_guard_marks_destructive_candidate()`。
- [x] 新增：`test_tool_guard_does_not_log_full_command_payload()`。

验收标准：
- [x] Policy/Safety 决策日志可区分“普通 shell”与“高危 shell”。
- [x] 无敏感全文泄露。

---

### P0-3 统一工具策略，修复“执行提示依赖 shell 但全局 deny shell.*”冲突

状态：`DONE`

改动文件：
- [x] `quentin/runtime/system.py`
- [x] `quentin/bootstrap/container.py`
- [x] `tests/unit/test_tool_policy_resolution.py`
- [x] `tests/unit/tools/test_task_executor_integration.py`

实现步骤：
- [x] 去掉“一刀切 deny shell.*”默认策略，改为分层策略：
  - [x] `sandbox`: 允许 `shell.run_command`，但保留安全钩子/命令审计。
  - [x] `staging/prod`: 默认 deny shell 或仅 allow 安全子集。
- [x] 保持 `SafetyKernel + before_hook` 双重门禁。
- [x] 在 `ToolPolicy` 注释中明确策略优先级（global→role→env→tool）。

测试：
- [x] 新增：`test_shell_allowed_in_sandbox_with_guard()`。
- [x] 新增：`test_shell_denied_in_prod_by_default_policy()`。
- [x] 新增：`test_executor_tool_call_not_blocked_by_conflicting_defaults()`。

验收标准：
- [x] 执行器不会因为默认策略冲突导致无意义重试。
- [x] 高环境仍保持保守阻断。

---

## P1（高价值）动态引导与自愈

### P1-1 Progressive Pressure：多轮工具调用无用户产出时注入进度压力

状态：`DONE`

改动文件：
- [x] `quentin/execution/skill_executor.py`
- [x] `quentin/cognitive/loop_impl.py`
- [x] `tests/unit/test_cognitive_loop_metrics.py`（扩展）
- [x] `tests/unit/test_tool_cancellation.py`（确保不中断取消语义）

实现步骤：
- [x] 在 executor 增加 `tool_only_turn_count` 统计（可放入 context runtime state）。
- [x] 若连续 N（建议 3）次只发生工具调用且 `final_output` 无用户可见进展，下一轮 `system_prompt` 注入固定提醒：
  - [x] 要求先输出简短进展，再继续工具调用。
- [x] 当模型输出“进展摘要”后重置计数。
- [x] 将该事件写入 trace：`progressive_pressure_triggered=true`。

测试：
- [x] 新增：`test_progressive_pressure_injected_after_three_tool_only_turns()`。
- [x] 新增：`test_progressive_pressure_resets_after_user_visible_update()`。

验收标准：
- [x] 工具循环任务中，至少每 N 轮会产生一次可见进展文本。
- [x] 无额外死循环引入。

---

### P1-2 Self-Correction Prompt：工具错误返回启发式纠错建议

状态：`DONE`

改动文件：
- [x] `quentin/tools/filesystem.py`
- [x] `quentin/tools/shell.py`
- [x] `quentin/tools/schemas.py`（如需扩展 `ToolCallResult.meta` 约定）
- [x] `tests/unit/tools/test_context_extractor.py` 或新增 `tests/unit/tools/test_tool_error_hints.py`

实现步骤：
- [x] 为常见错误生成 `hint` 字段（保持 machine-readable）：
  - [x] `search string not found` -> 建议先 `fs.read_file` 或缩小/放宽匹配。
  - [x] `multiple occurrences` -> 建议加上下文片段或改用更精确定位。
  - [x] `timeout` -> 建议缩小命令范围或拆分命令。
  - [x] `path denied` -> 提示允许目录策略。
- [x] 错误结构统一：`{"status":"error","error":"...","hint":"...","next_actions":[...]}`。

测试：
- [x] 新增：`test_fs_search_replace_not_found_has_hint()`。
- [x] 新增：`test_shell_timeout_has_hint()`。
- [x] 新增：`test_path_denied_has_allowed_roots_hint()`。

验收标准：
- [x] 执行器收到错误时可以直接复用 `hint` 再尝试，而不是盲重试。

---

### P1-3 ModelDialect 适配层（按模型方言变换 Prompt 密度与格式）

状态：`DONE`

改动文件：
- [x] 新建 `quentin/llm/model_dialect.py`
- [x] `quentin/llm/client.py`
- [x] `quentin/routing/model_router.py`（只加透传字段，不改路由决策主干）
- [x] `tests/unit/test_llm_remote_providers.py`
- [x] 新增 `tests/unit/test_model_dialect.py`

实现步骤：
- [x] 定义 `ModelDialect.transform(system_prompt, user_prompt, *, provider, model_name, metadata)`。
- [x] 最小规则集：
  - [x] `gemini`: 严格 system 时，将部分动态运行态前置到 user 前缀。
  - [x] `anthropic/claude`: 保留 system，控制 JSON 指令简洁度。
  - [x] `ollama/small local`: 自动压缩冗长协议，保留核心约束。
- [x] 在 `call_llm()` 进入 provider 调用前统一执行 transform。
- [x] 记录 trace 字段：`dialect_profile`, `prompt_compaction_ratio`。

测试：
- [x] 新增：`test_gemini_dialect_moves_runtime_prefix_to_user()`。
- [x] 新增：`test_local_small_model_dialect_reduces_prompt_density()`。
- [x] 新增：`test_dialect_transform_is_noop_when_disabled()`。

验收标准：
- [x] 同一任务在不同 provider 下输入结构可控且可观测。
- [x] 不改变现有 `ModelRouter` 决策接口。

---

### P1-4 Prompt 权重分层（SOUL > SKILL > PROJECT_CONTEXT > HINT）

状态：`DONE`

改动文件：
- [x] `quentin/cognitive/loop_impl.py`
- [x] `quentin/council/manager.py`
- [x] 新建 `quentin/cognitive/prompt_layers.py`
- [x] 新增 `tests/unit/test_runtime_bootstrap.py`（扩展）
- [x] 新增 `tests/unit/test_planner_hierarchical_planner.py`（扩展）

实现步骤：
- [x] 新增 `PromptLayers` 组装器（不替换现有 council，只做文本拼装 helper）。
- [x] 固定拼装顺序：
  1. [x] SOUL（人格/语气）
  2. [x] SKILL（当前任务 SOP）
  3. [x] PROJECT CONTEXT（记忆/环境）
  4. [x] HINT（临时运行态提示）
- [x] 让 planner/executor/council 三处统一复用该 helper。

测试：
- [x] 新增：`test_prompt_layers_priority_order()`。
- [x] 新增：`test_hint_cannot_override_soul_constraints()`。

验收标准：
- [x] prompt 结构顺序稳定、可单测。
- [x] 不改既有 CouncilManager 外部 API。

---

### P1-5 Self-Awareness 自身感知闭环（运行时可感知“我在出错”）

状态：`DONE`

改动文件：
- [x] 新建 `quentin/cognitive/self_awareness.py`
- [x] `quentin/cognitive/loop_impl.py`
- [x] `quentin/execution/skill_executor.py`
- [x] 新增 `tests/unit/test_self_awareness_engine.py`
- [x] `tests/unit/test_progressive_pressure_executor.py`（扩展）
- [x] `tests/unit/test_cognitive_loop_metrics.py`（扩展）

实现步骤：
- [x] 新增 `SelfAwarenessEngine`：聚合每轮 `exec_result + metrics`，产出 `SelfAwarenessSnapshot`。
- [x] 快速失败分类：复用 `quentin/llm/failover.py` 将错误归类为 `timeout/context_overflow/rate_limit/...`。
- [x] 状态分级：`healthy | warning | critical`，并给出 `suggested_actions`（如 `trigger_compaction_and_trim_context`）。
- [x] 将 snapshot 注入 Planner 上下文（`context.self_awareness` + `self_awareness_note`）。
- [x] 将 snapshot 注入 Executor prompt hints（`SELF AWARENESS` 区块）。
- [x] Trace 记录追加 `self_awareness_status/failure_rate/failover_reason`，便于观测与回放。
- [x] 自感知控制信号落地：`context_overflow` 触发即时 flush，`warning/critical` 强制 reflection，连续 critical 系统错误自动中断。

测试：
- [x] 新增：`test_self_awareness_detects_context_overflow_reason()`。
- [x] 新增：`test_self_awareness_tracks_consecutive_system_errors()`。
- [x] 新增：`test_executor_injects_self_awareness_note()`。
- [x] 新增：`test_build_planner_hints_includes_self_awareness_note()`。

验收标准：
- [x] 当执行错误发生后，下一轮 planner/executor 都能看到结构化“自感知状态”。
- [x] 系统可区分“逻辑失败”与“系统级连续故障”，并给出可执行的处置建议。
- [x] 不改变原有架构边界（仅在 CognitiveLoop/Executor 细节层增强）。

---

### P1-6 Execution Fidelity：原生 Tool Calling 替代 JSON 字符串解析主路径

状态：`DONE`

改动文件：
- [x] `quentin/execution/skill_executor.py`
- [x] `quentin/llm/client.py`
- [x] `quentin/llm/ollama_client.py`
- [x] `quentin/tools/manager.py`
- [x] `tests/unit/test_executor_native_tool_calling.py`（新建）

实现步骤：
- [x] 为 Ollama 接入原生 tools/function-calling 模式（结构化 tool call，不经“文本 JSON”中转）。
- [x] 在 Executor 中优先消费结构化 tool_calls，仅在 provider 不支持时回退当前 JSON 文本解析。
- [x] 保留统一的 ToolPolicy/SafetyKernel 守门，不改变现有工具治理架构。
- [x] 记录 trace 字段：`tool_call_mode=native|json_fallback`、`tool_call_parse_error`。

测试：
- [x] 新增：`test_executor_prefers_native_tool_calls_over_json_parse()`。
- [x] 新增：`test_executor_falls_back_to_json_mode_when_provider_no_native_tools()`。
- [x] 新增：`test_native_tool_call_path_preserves_safety_guard()`。

验收标准：
- [x] 支持原生 tool-calling 的模型上，工具调用不再依赖正则/robust-json 解析。
- [x] 工具调用成功率提升，JSON 破损导致的失败显著下降。

---

### P1-7 Incremental Progress：执行器改为逐步反馈循环

状态：`DONE`

改动文件：
- [x] `quentin/execution/skill_executor.py`
- [x] `quentin/cognitive/loop_impl.py`
- [x] `quentin/tools/schemas.py`（如需扩展 step feedback 结构）
- [x] `tests/unit/test_executor_incremental_loop.py`（新建）

实现步骤：
- [x] 将单次“全量计划执行”升级为 step-by-step 回路：每执行一步工具，立刻把结果回注给模型决定下一步。
- [x] 引入 `max_step_iterations` 与 `no_progress_threshold`，防止局部死循环。
- [x] 每步产出 `step_delta`（做了什么、结果如何、下一步意图）并写 trace。
- [x] 与现有 `progressive_pressure` 和 `self_awareness` 联动：无进展时强制输出用户可见进展。

测试：
- [x] 新增：`test_executor_step_feedback_updates_next_action()`。
- [x] 新增：`test_executor_breaks_on_no_progress_threshold()`。
- [x] 新增：`test_incremental_loop_resumes_from_failed_step_not_from_step1()`。

验收标准：
- [x] 失败后重试能够从失败点附近继续，而不是总是从第一步重跑。
- [x] 大任务执行中间态可观测，死循环率下降。

---

### P1-8 Context Awareness：目录快照 + 语义检索前置注入

状态：`DONE`

改动文件：
- [x] `quentin/cognitive/loop_impl.py`
- [x] `quentin/retrieval/codebase_index.py`
- [x] `quentin/planning/memory_helpers.py`（或 planner context 组装点）
- [x] `tests/unit/test_cognitive_loop_context_awareness.py`（新建）

实现步骤：
- [x] 将 File Tree Snapshot 设为 planner 默认上下文（可配置裁剪深度和忽略目录）。
- [x] 引入任务相关文件候选检索（semantic grep / symbol search）并注入 `candidate_files`。
- [x] 为路径幻觉增加 pre-check：若目标文件不存在，先触发“目录/检索”而不是直接写错路径。
- [x] trace 增加 `context_injected.tree_lines`、`context_injected.candidate_files_count`。

测试：
- [x] 新增：`test_planner_receives_file_tree_snapshot_by_default()`。
- [x] 新增：`test_executor_avoids_nonexistent_path_by_triggering_lookup()`。
- [x] 新增：`test_context_injection_respects_budget_limits()`。

验收标准：
- [x] 常见任务中，路径幻觉率下降；模型更少出现“猜目录/猜文件名”。
- [x] 上下文注入不突破 budget，仍可稳定执行。

---

### P1-9 Model Intelligence：Council 混合模型路由

状态：`DONE`

改动文件：
- [x] `quentin/models/router.py`
- [x] `quentin/council/manager.py`
- [x] `quentin/llm/client.py`
- [x] `tests/unit/test_council_hybrid_routing.py`（新建）

实现步骤：
- [x] 在 CouncilManager 引入复杂度分级（simple/edit-heavy/reasoning-heavy）。
- [x] 路由策略：简单读写优先小模型；复杂重构/多约束决策自动路由高阶模型。
- [x] 增加失败升级策略：小模型连续失败 N 次后自动升级到高阶模型。
- [x] 记录路由决策 trace：`routing_tier`、`escalation_reason`、`fallback_chain`。

测试：
- [x] 新增：`test_simple_task_routes_to_small_model()`。
- [x] 新增：`test_complex_task_routes_to_high_tier_model()`。
- [x] 新增：`test_repeated_small_model_failures_trigger_escalation()`。

验收标准：
- [x] 复杂任务成功率提升且总成本可控。
- [x] 路由决策可解释、可回放。

---

### P1-10 Blueprint Tracker 统一状态模型（消除 scan/autopatch 语义分裂）

状态：`DONE`

改动文件：
- [x] `quentin/blueprint/tracker.py`
- [x] `quentin/blueprint/gaps.py`
- [x] `quentin/blueprint/auto_patcher.py`
- [x] `quentin/runtime/task_sources.py`
- [x] `quentin/cli/qctl.py`
- [x] `tests/unit/test_blueprint_tracker_status_unified.py`
- [x] `tests/unit/test_blueprint_gaps_status_unified.py`

实现步骤：
- [x] 在 `tracker.py` 引入 canonical status：`missing/partial/unknown/done`，并产出 `confidence/evidence`。
- [x] 将 trace/experiment 区分为 `expects_*` 与 `has_*`，对 blueprint 未声明的证据项不再误罚分。
- [x] `gaps.py` 同步 canonical status，并补 `legacy_status` 兼容旧消费方。
- [x] `auto_patcher` 优先消费 `item.status`，只在旧对象上回退到布尔组合判定。
- [x] `task_sources` 改为优先按 `status != done` 生成 backlog，保留 score 兜底逻辑。
- [x] `qctl blueprint-scan/blueprint-item` 输出统一状态与 expected/observed 证据信息。

测试：
- [x] 新增：`test_tracker_marks_done_when_optional_evidence_not_required()`。
- [x] 新增：`test_tracker_marks_missing_when_module_absent()`。
- [x] 新增：`test_gaps_tracker_uses_canonical_status_with_legacy_alias()`。
- [x] 回归：`test_blueprint_scan_can_be_made_fully_green()`。
- [x] 回归：`test_blueprint_autopatch_deterministic()`。
- [x] 回归：`test_task_sources_blueprint.py`。

验收标准：
- [x] `blueprint-scan` 与 `blueprint-autopatch` 对同一条目给出一致状态语义。
- [x] 未声明 trace/experiment 的条目不会被默认打成低分/缺口。
- [x] 旧链路仍可读取 `legacy_status`，不破坏已有消费代码。

---

### P1-11 Self-Awareness 防死循环强化（感知失败模式并强制转向）

状态：`DONE`

改动文件：
- [x] `quentin/cognitive/self_awareness.py`
- [x] `quentin/cognitive/loop_impl.py`
- [x] `quentin/execution/skill_executor.py`
- [x] `tests/unit/test_self_awareness_engine.py`
- [x] `tests/unit/test_cognitive_loop_metrics.py`

实现步骤：
- [x] 扩展 `SelfAwarenessSnapshot`：新增 `anti_pattern_reason`、`consecutive_no_progress`。
- [x] 自感知错误抽取覆盖 `steps.result.tool_result` 与 `feedback_tail`，不再只看顶层 `raw.error`。
- [x] 新增反模式识别：`interactive_editor_command`、`guessed_download_command`、`repeated_tool_call_loop`。
- [x] 新增无进展检测：连续工具调用但无用户可见产出时累积计数并上升健康等级。
- [x] CognitiveLoop 在自感知发现反模式时自动写入恢复计划覆写，避免回到空转规划。
- [x] Runtime control 强化：反模式或连续无进展时强制 reflection。
- [x] 修复 Executor 静态方法中的 `NameError`（`_resolve_narration_mode` 使用 `Executor._safe_json_dump`）。

测试：
- [x] 新增：`test_self_awareness_detects_antipattern_from_feedback_tail()`。
- [x] 新增：`test_self_awareness_counts_consecutive_no_progress()`。
- [x] 新增：`test_detect_execution_antipattern_from_feedback_tail()`。
- [x] 新增：`test_self_awareness_controls_force_reflection_on_antipattern()`。
- [x] 回归：`test_progressive_pressure_executor.py`。

验收标准：
- [x] `nano/vim` 被工具层拦截后，CognitiveLoop 能在下一轮自动切换到 `fs.read_file + fs.search_replace/fs.write_file` 恢复路径。
- [x] 连续无进展时，self-awareness 状态提升并推动反思，不再无意义重复同类工具调用。

---

### P1-12 Self-Awareness 上送 BrainDaemon（自动守护与恢复任务编排）

状态：`DONE`

改动文件：
- [x] `quentin/cognitive/loop_impl.py`
- [x] `quentin/runtime/brain_daemon.py`
- [x] `tests/unit/test_system_events_pipeline.py`
- [x] `tests/unit/test_brain_daemon_self_awareness_guardrails.py`

实现步骤：
- [x] `CognitiveResult` 新增 `self_awareness` 字段，回传最终快照给运行时守护层。
- [x] CognitiveLoop 在 `warning/critical` 时上送 `system_events`（`self_awareness_alert`）。
- [x] BrainDaemon 新增 guardrail 机制：critical/warning 告警触发冷却窗口，暂缓高风险后台动作（autopatch/patchflow）。
- [x] BrainDaemon 自动生成去重的恢复任务（`kind=self_awareness_recovery`）入队，驱动后续非交互恢复执行。
- [x] 事件消费兼容：daemon 消费 `self_awareness_alert` 时保留并回灌非相关事件，避免吞掉其它系统事件。

测试：
- [x] 新增：`test_cognitive_loop_emits_self_awareness_alert()`。
- [x] 新增：`test_brain_daemon_applies_guardrail_and_enqueues_recovery()`。
- [x] 新增：`test_brain_daemon_drain_keeps_non_awareness_events()`。
- [x] 回归：`test_self_awareness_engine.py` + `test_cognitive_loop_metrics.py` + `test_system_events_pipeline.py`。

验收标准：
- [x] 大脑出现连续系统异常或反模式时，守护层能自动降级并触发恢复任务，不依赖人工干预。
- [x] 自感知事件既可供 planner 消费，也可供 daemon 守护消费，且不破坏既有事件通道。

---

### P1-13 Guardrail 任务优先级重排（恢复任务抢占，高风险维护任务延后）

状态：`DONE`

改动文件：
- [x] `quentin/runtime/task_queue.py`
- [x] `quentin/runtime/brain_daemon.py`
- [x] `tests/unit/test_brain_daemon_self_awareness_guardrails.py`

实现步骤：
- [x] `TaskQueue` 新增 `claim_by_id(task_id, worker_id)`，用于守护层按策略原子领取指定任务。
- [x] BrainDaemon 新增 `_claim_next_item()` 策略入口，替代直接 `claim_next()`。
- [x] guardrail 激活时优先领取 `kind=self_awareness_recovery`，实现恢复任务抢占。
- [x] guardrail 激活时延后 `blueprint_gap`、`patchflow_backlog` 任务；仅领取安全普通任务。
- [x] 非 guardrail 状态保持原有优先级 + FIFO 领取语义不变。

测试：
- [x] 新增：`test_guardrail_claim_preempts_recovery_task()`。
- [x] 新增：`test_guardrail_claim_defers_blocked_and_claims_safe()`。
- [x] 新增：`test_no_guardrail_claims_highest_priority_normally()`。

验收标准：
- [x] 守护窗口内恢复任务优先被执行，风险维护任务不会继续加剧系统波动。
- [x] 守护窗口结束后恢复原有调度行为，不影响常态吞吐。

---

### P1-14 Guardrail 渐进恢复策略（分阶段恢复后台维护）

状态：`DONE`

改动文件：
- [x] `quentin/runtime/brain_daemon.py`
- [x] `tests/unit/test_brain_daemon_self_awareness_guardrails.py`

实现步骤：
- [x] 增加运行模式状态机：`guardrail` -> `recover_task_sources` -> `recover_patchflow` -> `normal`。
- [x] 增加阶段开关方法：`_can_run_task_sources`、`_can_run_patchflow`、`_can_run_blueprint_autopatch`。
- [x] 空闲调度改为按状态机执行，避免 guardrail 结束后一次性恢复全部高风险动作。
- [x] guardrail 激活时同步设置恢复窗口：`QUENTIN_BRAIN_RECOVER_TASK_SOURCES_SEC`、`QUENTIN_BRAIN_RECOVER_PATCHFLOW_SEC`。

测试：
- [x] 新增：`test_runtime_mode_staged_recovery_windows()`。
- [x] 新增：`test_apply_guardrail_sets_recovery_stages()`。
- [x] 回归：`test_guardrail_claim_preempts_recovery_task()` 等守护调度测试。

验收标准：
- [x] 系统从异常状态恢复时具备“先低风险、后高风险”的节奏，减少二次震荡。
- [x] 各恢复阶段可通过环境变量调参，便于线上迭代。

---

### P1-15 Guardrail 可观测化（模式与恢复窗口对外可见）

状态：`DONE`

改动文件：
- [x] `quentin/runtime/brain_daemon.py`
- [x] `quentin/runtime/system_events.py`
- [x] `tests/unit/test_brain_daemon_self_awareness_guardrails.py`
- [x] `tests/unit/test_system_events_pipeline.py`

实现步骤：
- [x] `BrainDaemon.run_once` 输出新增 `runtime_mode` 与 `guardrail_state`（剩余时间、可运行能力开关）。
- [x] 守护事件 `brain_guardrail_activated` 附带 `runtime_mode/guardrail_state`，统一上送系统事件通道。
- [x] `SystemEventQueue.format_events_for_prompt` 增加 `runtime_mode` 与 `guardrail_remaining_sec` 展示。
- [x] 保持兼容：旧字段不变，新字段增量追加。

测试：
- [x] 新增：`test_guardrail_state_exposes_remaining_windows()`。
- [x] 新增：`test_system_event_formatter_includes_runtime_mode_fields()`。
- [x] 回归：`test_brain_daemon_applies_guardrail_and_enqueues_recovery()`。

验收标准：
- [x] 运维/上层 agent 能实时看到当前守护阶段与恢复倒计时，便于判断“为什么某些维护任务被延后”。
- [x] 事件文本摘要具备可读状态信息，不需要解析原始 JSON 才能定位守护状态。

---

### P1-16 Guardrail 参数自调优（按恢复效果动态缩放窗口）

状态：`DONE`

改动文件：
- [x] `quentin/runtime/brain_daemon.py`
- [x] `tests/unit/test_brain_daemon_self_awareness_guardrails.py`

实现步骤：
- [x] 引入恢复结果历史窗口（`self_awareness_recovery` 成败）并建立调优反馈函数。
- [x] 失败趋势时放大 guardrail 参数，稳定成功时逐步缩小参数，避免固定阈值失配。
- [x] 调优目标覆盖 `cooldown`、`recover_task_sources`、`recover_patchflow` 三类窗口倍率。
- [x] 新增可配置项：`QUENTIN_BRAIN_GUARDRAIL_TUNE_UP/DOWN/MIN/MAX`。
- [x] `guardrail_state` 增加 `tuning` 与 `recovery_success_rate` 字段，支持观测与调参。

测试：
- [x] 新增：`test_guardrail_tuning_increases_after_recovery_failures()`。
- [x] 新增：`test_guardrail_tuning_decreases_after_stable_recovery()`。
- [x] 新增：`test_apply_guardrail_uses_tuned_multipliers()`。

验收标准：
- [x] 恢复失败后系统自动更保守（窗口变长），连续稳定后自动回收保守度（窗口缩短）。
- [x] 调优过程可观测、可限制，不会无限放大或缩小。

---

### P1-17 Guardrail 状态持久化（重启后保留自调优学习结果）

状态：`DONE`

改动文件：
- [x] `quentin/runtime/brain_daemon.py`
- [x] `tests/unit/test_brain_daemon_self_awareness_guardrails.py`

实现步骤：
- [x] 增加 guardrail 状态路径解析：默认 `data/runtime/brain_guardrail_state.json`，支持 `QUENTIN_BRAIN_GUARDRAIL_STATE_PATH` 覆盖。
- [x] daemon 初始化时自动加载历史 `tuning` 与 `recovery_outcomes`。
- [x] 在 guardrail 激活和调优更新后自动保存状态，采用 `.tmp` 原子替换写入。
- [x] `guardrail_state` 持续暴露当前调优状态与成功率，便于重启后比对。

测试：
- [x] 新增：`test_guardrail_tuning_persists_across_daemon_restart()`。
- [x] 新增：`test_guardrail_state_file_written_on_activation()`。
- [x] 回归：守护模式、渐进恢复、自调优全链路测试。

验收标准：
- [x] 进程重启后不丢失守护调优历史，守护参数延续上次学习结果。
- [x] 状态持久化对运行时无侵入，文件异常时自动降级为内存模式。

---

### P1-18 Guardrail 调优可解释日志（可追溯“为何调参”）

状态：`DONE`

改动文件：
- [x] `quentin/runtime/brain_daemon.py`
- [x] `tests/unit/test_brain_daemon_self_awareness_guardrails.py`

实现步骤：
- [x] 调优时生成结构化解释：`trigger_reason/factor/success_rate/fail_streak/before/after`。
- [x] 新增事件上送：`brain_guardrail_tuned`，将调参解释写入 `system_events`。
- [x] `guardrail_state` 增加 `last_tuning_adjustment` 与 `tuning_history_tail`，可直接观测最近调参轨迹。
- [x] 状态持久化扩展：保存/恢复 `tuning_history` 与 `last_tuning_adjustment`。

测试：
- [x] 新增：`test_guardrail_tuning_emits_event_with_explanation()`。
- [x] 扩展：`test_guardrail_tuning_increases_after_recovery_failures()` 校验触发原因与 factor。
- [x] 扩展：`test_guardrail_tuning_persists_across_daemon_restart()` 校验最后调参解释可恢复。

验收标准：
- [x] 每次 guardrail 调参都有可解释证据，支持线上问题复盘与调参审计。
- [x] 重启后仍能看到最近调参原因与变化轨迹，不再出现“参数突变不可解释”。

---

### P1-19 Guardrail 调优摘要聚合（降低高频调参事件噪音）

状态：`DONE`

改动文件：
- [x] `quentin/runtime/brain_daemon.py`
- [x] `tests/unit/test_brain_daemon_self_awareness_guardrails.py`

实现步骤：
- [x] 新增摘要阈值参数：`QUENTIN_BRAIN_GUARDRAIL_TUNE_SUMMARY_EVERY`（默认 5）。
- [x] 每 N 次调参触发一次 `brain_guardrail_tuning_summary` 事件，上送聚合结果。
- [x] 摘要 payload 含：`window_size`、`tuning_adjustment_count`、`avg_factor`、`reason_counts`、`current_tuning`。
- [x] 新增摘要计数状态：`tuning_adjustment_count`、`last_tuning_summary_at_count`，并持久化保存/恢复。
- [x] `guardrail_state` 同步暴露上述计数，便于观测 summary 是否按窗口触发。

测试：
- [x] 新增：`test_guardrail_tuning_emits_summary_every_n_adjustments()`。
- [x] 回归：guardrail 调优解释事件与持久化恢复测试。

验收标准：
- [x] 高频调参场景中可以通过摘要事件快速把握总体趋势，减少单条调参事件噪声。
- [x] 重启后不会因为计数丢失而重复生成同一窗口摘要。

---

### P1-20 调优摘要联动 Intelligence Strict

状态：`DONE`

改动文件：
- [x] `quentin/runtime/brain_daemon.py`
- [x] `tests/unit/test_brain_daemon_self_awareness_guardrails.py`

实现步骤：
- [x] 新增摘要恶化连续计数：`tuning_summary_worsening_streak`（可持久化）。
- [x] 在摘要聚合后判断恶化趋势（`avg_factor` + 失败触发原因分布），达到连续阈值时触发 strict 联动。
- [x] 自动延长 `intelligence_strict_until`，并注入原因 `guardrail_tuning_summary_worsening`。
- [x] 同步 `QUENTIN_DONE_COUNCIL_STRICT_REASONING`，保证执行层立即进入严格模式。
- [x] 上送 `brain_intelligence_strict_mode_changed` 扩展字段：`trigger`、`worsening_streak`、`already_active`。
- [x] `guardrail_state` 暴露 `tuning_summary_worsening_streak`，便于 runtime 自检。

测试：
- [x] 新增：`test_guardrail_tuning_summary_worsening_escalates_intelligence_strict()`。
- [x] 新增：`test_guardrail_tuning_summary_worsening_streak_resets_on_stable_summary()`。
- [x] 回归：`test_brain_daemon_self_awareness_guardrails.py` 相关集通过。

验收标准：
- [x] 调优连续恶化时，系统无需等待外部观测也会主动提升防御强度。
- [x] 调优恢复稳定后，恶化计数能自动清零，避免误触发 strict。

---

### P1-21 Strict 原因回注 Planner/Executor 提示

状态：`DONE`

改动文件：
- [x] `quentin/runtime/brain_daemon.py`
- [x] `quentin/cognitive/loop_impl.py`
- [x] `tests/unit/test_brain_daemon_self_awareness_guardrails.py`
- [x] `tests/unit/test_cognitive_loop_metrics.py`

实现步骤：
- [x] strict 激活时导出 `QUENTIN_DONE_COUNCIL_STRICT_REASONS`（逗号分隔）。
- [x] strict 结束时恢复 baseline 或清理 strict reason 环境变量。
- [x] planner hints 读取 strict reasons 并注入高优先级约束提示（优先 discovery + 低风险增量执行）。
- [x] executor prompt context 同步注入 strict reasons，确保执行层与规划层一致。

测试：
- [x] 扩展 `test_intelligence_strict_mode_enables_done_council_strict_env()` 校验 strict reasons env。
- [x] 扩展 `test_intelligence_strict_mode_clears_and_restores_env_after_expire()` 校验恢复基线。
- [x] 新增 `test_build_planner_hints_includes_intelligence_strict_reasons()`。
- [x] 新增 `test_build_executor_prompt_context_includes_intelligence_strict_reasons()`。
- [x] 目标回归测试集通过。

验收标准：
- [x] strict 模式下，planner/executor 都能感知“为什么严格”，降低重复无效尝试概率。
- [x] strict 结束后不会残留历史 reason 污染正常模式。

---

### P1-22 Strict 原因执行链路兜底（context 级透传）

状态：`DONE`

改动文件：
- [x] `quentin/cognitive/loop_impl.py`
- [x] `quentin/execution/skill_executor.py`
- [x] `tests/unit/test_cognitive_loop_metrics.py`
- [x] `tests/unit/test_executor_prompt_style.py`

实现步骤：
- [x] `CognitiveLoop` 新增 strict reason 列表解析方法，统一 env -> list 转换。
- [x] `CognitiveLoop._build_executor_prompt_context` 始终透传 `strict_reasons`（含 prompt factory disabled 分支）。
- [x] `SkillExecutor._fallback_llm_execute` 注入 `INTELLIGENCE STRICT REASONS` step 级提示，强调 discovery 与低风险增量执行。
- [x] 保持架构不变，仅增强 existing context/hints 数据通路。

测试：
- [x] 新增 `test_build_executor_prompt_context_exposes_strict_reasons_when_factory_disabled()`。
- [x] 新增 `test_strict_reasons_are_injected_into_executor_prompt()`。
- [x] 目标回归测试集通过。

验收标准：
- [x] 严格模式约束可稳定抵达执行层，即使 prompt factory 配置切换也不丢失。
- [x] 执行器在 step 级提示中显式感知 strict 原因，降低“继续撞同一墙”概率。

---

## P2（修复与一致性）

### P2-1 修复 CognitiveLoop 重复 circuit-breaker 逻辑

状态：`DONE`

改动文件：
- [x] `quentin/cognitive/loop_impl.py`
- [x] `tests/unit/test_immune_loop_windowed_error_rate.py`（必要时扩展）

实现步骤：
- [x] 将重复逻辑块合并为 `_update_circuit_breaker_state(...)`。
- [x] 确保每轮只计算一次错误计数与触发判定。

验收标准：
- [x] 行为与预期一致，无双重计数。

---

### P2-2 修复 SkillExecutor usage 统计“失败也记成功”

状态：`DONE`

改动文件：
- [x] `meta_agent/skills/executor.py`
- [x] `tests/unit/test_task_executor_skill_execution.py`

实现步骤：
- [x] `record_usage(skill_id, success=...)` 按真实执行结果写入。
- [x] 将 `finally: success=True` 改为显式结果分支更新。

验收标准：
- [x] 失败执行不会污染 success_rate。

---

### P2-3 时间字段统一为 timezone-aware

状态：`DONE`

改动文件：
- [x] `quentin/routing/model_router.py`
- [x] `quentin/council/manager.py`
- [x] `quentin/kernel/policy.py`
- [x] 其他 `utcnow()` 出现点（按 `rg "utcnow\("` 扫描）
- [x] `tests/unit/test_memory_store_sqlite.py`（如需）

实现步骤：
- [x] 使用统一时间 helper（建议 `quentin/utils/time.py`）。
- [x] 全量替换 `datetime.utcnow()` 为 aware 时间。

验收标准：
- [x] 关键日志/模型路由/审计时间戳格式一致。

---

## 交付节奏（建议）

### 批次 A（1-2 天）
- [x] P0-1
- [x] P0-2
- [x] P0-3

### 批次 B（2-4 天）
- [x] P1-1
- [x] P1-2

### 批次 C（2-4 天）
- [x] P1-3
- [x] P1-4

### 批次 D（1-2 天）
- [x] P2-1
- [x] P2-2
- [x] P2-3

---

## PR 模板（每个任务都要写）

- [ ] 变更摘要（改了什么函数/模块）
- [ ] 不变项声明（架构未改的边界）
- [ ] 风险与回滚策略
- [ ] 测试命令与结果：
  - [ ] `pytest tests/unit -q`
  - [ ] 受影响子集（按任务列出）

---

## 全局验收清单

- [ ] 工具路径越界被硬拦截（含相对路径逃逸与绝对路径）。
- [ ] Tool 调用审计能看见高危语义，不泄露敏感全文。
- [ ] 执行器不再因默认策略冲突陷入无效循环。
- [ ] 多轮工具调用具备“进度压力”反馈能力。
- [ ] 错误结果具备启发式纠错提示。
- [ ] Prompt 可按模型方言做轻量适配。
- [ ] Prompt 组装具备稳定的权重分层。
- [ ] 技能统计与时间戳一致性问题修复完成。
