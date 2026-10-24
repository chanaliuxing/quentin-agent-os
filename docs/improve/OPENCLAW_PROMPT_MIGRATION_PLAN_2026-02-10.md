# OpenClaw Prompt 平移实施计划（Quentin）

> 日期：2026-02-10  
> 目标：按“同功能平移”原则，把 OpenClaw 已长期验证的 Prompt 迁移到 Quentin。  
> 范围：仅 Prompt 构建、Prompt 注入、Prompt 协议；不做架构重写。

---

## 1. 总体原则

1. 同功能平移：仅迁移与 Quentin 当前模块职责一致的 Prompt。
2. 先平移后优化：第一版优先“语义等价”，不做大规模 wording 创新。
3. 代码化 Prompt：统一从“字符串散落”收敛到可组合的 builder/factory。
4. 可灰度：每个模块必须有 feature flag，默认保守关闭或 shadow 模式。
5. 可回滚：每次只上线一个模块，失败可单独回退。

---

## 2. 模块分解与顺序

### M1 System Prompt 工厂化（优先级 P0）
- OpenClaw 来源：
  - `src/agents/system-prompt.ts`
- Quentin 落点：
  - `meta_agent/runtime/council_runtime.py`
  - `quentin/cognitive/loop_impl.py`
  - 新增 `quentin/cognitive/prompt_factory.py`
- 目标：
  - 统一 `full/minimal` 模式
  - 支持 `enabled_tools/runtime_info/skill_context` 条件注入

### M2 Executor 工具调用风格平移（优先级 P0）
- OpenClaw 来源：
  - `src/agents/system-prompt.ts`（Tool call style）
- Quentin 落点：
  - `quentin/execution/skill_executor.py`
- 目标：
  - 默认不叙述低风险例行调用
  - 多步骤/高风险场景才说明

### M3 System Event 异步回灌（优先级 P0）
- OpenClaw 来源：
  - `src/infra/system-events.ts`
  - `src/agents/pi-embedded-runner/run.ts`
- Quentin 落点：
  - `meta_agent/self_programming/engine_v2.py`
  - `quentin/cognitive/loop_impl.py`
  - 新增 `quentin/runtime/system_events.py`
- 目标：
  - 后台任务完成后，不只写 trace；在下一轮认知循环注入系统提示并一次性消费

### M4 Tool Summary Mapping（优先级 P1）
- OpenClaw 来源：
  - `src/tool-summaries.ts`
- Quentin 落点：
  - `quentin/tools/manager.py`
  - `quentin/execution/skill_executor.py`
  - 新增 `quentin/tools/summary_map.py`
- 目标：
  - Prompt 仅暴露“工具名 + 短摘要”
  - 详细 schema 通过 `help(tool=...)` 获取

### M5 Sub-agent minimal Prompt（优先级 P1）
- OpenClaw 来源：
  - `src/agents/system-prompt.ts`（minimal 模式）
- Quentin 落点：
  - `quentin/multi_agent/coordinator.py`
  - `quentin/tools/manager.py`（subagent policy 已有，补 prompt 侧）
- 目标：
  - 父代理 full，子代理 minimal（身份/安全/任务边界）

### M6 Skill/SOP Prompt 模块化（优先级 P1）
- OpenClaw 来源：
  - `.pi/prompts/*.md`（SOP 模板）
- Quentin 落点：
  - `quentin/mutable/skills/`（新增 `*.md` SOP）
  - `quentin/skills/manager.py`（装载与引用）
- 目标：
  - 复杂流程优先 SOP 模板化（输入、步骤、输出、边界）

### M7 Silent Token 与心跳静默协议（优先级 P2）
- OpenClaw 来源：
  - `SILENT_REPLY_TOKEN`
  - `HEARTBEAT_OK`
- Quentin 落点：
  - `quentin/cognitive/loop_impl.py`
  - `quentin/cli/qctl.py`
  - 新增 `quentin/runtime/silent_protocol.py`
- 目标：
  - 无重要信息时输出静默 token 并被拦截，避免噪声通知

### M8 Context Pruning 策略对齐（优先级 P2）
- OpenClaw 来源：
  - `src/agents/pi-extensions/context-pruning/pruner.ts`
- Quentin 落点：
  - `quentin/llm/compaction.py`
  - `quentin/llm/context_budget.py`
- 目标：
  - 继续确定性剪枝（recent N + head/tail + placeholder），避免把压缩核心交给 LLM

---

## 3. 执行节奏（建议）

### 周期 A（第 1 周）
1. M1
2. M2
3. M3
4. M4（先做摘要映射，不做复杂动态加载）

### 周期 B（第 2 周）
1. M5
2. M6
3. M7
4. M8

---

## 4. 每模块统一交付标准

1. Mapping 文档：OpenClaw 原 Prompt 片段 -> Quentin 新实现位置。
2. 代码改动：最小侵入、可开关。
3. 测试：
   - 单测：Prompt 组装结构/字段完整性
   - 集成：典型任务至少 1 条 happy path + 1 条 error path
4. 观测：
   - trace 里新增模块级事件（例如 `prompt_factory_used`、`system_event_injected`）
5. 回滚：
   - 关闭对应 flag 即恢复旧行为

---

## 5. 风险与控制

1. 风险：Prompt 平移后和现有工具名/参数不匹配  
   控制：先做术语映射层（tool alias、字段 rename）。
2. 风险：JSON 输出稳定性下降  
   控制：保留当前 JSON schema hint + parser fallback，先 shadow 对比。
3. 风险：上下文长度上升  
   控制：M4 先落地，严格 short summary + 按需展开。
4. 风险：子代理能力不足  
   控制：minimal 模式允许按任务白名单追加一段补充指令。

---

## 6. Definition of Done（整体验收）

1. 8 个模块完成代码与测试，且每个模块可独立开关。
2. 关键任务集（代码修改、工具调用、异步回灌）回归通过率不低于基线。
3. `docs/improve/` 下保留完整迁移记录（plan + todo + mapping + rollout notes）。

