# RFC-001: 主循环收敛 (CognitiveLoop Convergence)

Status: Draft (proposed)
Owner: Agent 0 (Architecture Integrator)
Date: 2026-02-22

## 1. 背景与问题

当前仓库存在两套“看起来都像主循环”的入口：

- Core CognitiveLoop v2（canonical candidate）：
  - `quentin/cognitive/loop_impl.py`
  - 稳定导入路径：`quentin/cognitive/loop.py`（re-export）
- Runtime/Legacy CognitiveLoop（compat / facade candidate）：
  - `quentin/runtime/cognitive_loop.py`
  - 以及以 `MetaAgentRuntime` 为中心的旧 runtime 入口：`quentin/runtime/system.py`

风险：

1. **碎片化**：不同入口各自实现“会话/上下文/压缩/事件/输出”逻辑，导致行为漂移。
2. **不可演化**：学习闭环（memory/skills/self-prog）很难找到唯一回流点，产物无法稳定提升主循环成功率。
3. **不可治理**：安全/预算/审批/工具策略被旁路绕过时无法统一审计。

目标是：把“主循环”收敛为**唯一 canonical pipeline**，其余入口全部降级为 facade/compat 层。

## 2. 决策摘要（本 RFC 的结论）

### 2.1 Canonical 主循环实现

**唯一 canonical 主循环实现：**

- `quentin.cognitive.loop_impl.CognitiveLoop`

**唯一 canonical 导入路径（对业务/产品代码）：**

- `from quentin.cognitive.loop import CognitiveLoop, CognitiveTask, CognitiveResult`

说明：

- `quentin.cognitive.loop_impl` 允许测试/内部工具直接 import，但业务代码默认禁止（见 CI gate）。
- `quentin.runtime.cognitive_loop` 与 `quentin.runtime.system.MetaAgentRuntime` 仅保留为兼容层，逐步迁移与退役。

### 2.2 Canonical 装配入口（Embedding / 生产装配）

**唯一 canonical 装配入口：**

- `quentin.bootstrap.container.Container`
  - `Container(...).cognitive_loop` 产出 canonical `CognitiveLoop`

原则：

- 不允许在脚本/服务里“手动拼装”另一套 loop（除非在 `tests/` 或明确的 bench/实验隔离区）。
- 所有 domain 工具注入、tool policy、middleware、auth rotation、schema dialect 等，统一通过 `Container.tool_manager` 及其 wiring。

## 3. 协议：为“稳定接入且不碎片化”设立硬边界

本节定义 3 个协议。任何新能力必须通过协议接入主循环，禁止复制主循环逻辑。

### 3.1 SessionProtocol v1

SessionProtocol 解决：会话生命周期、并发一致性、压缩状态、回放/分支的统一表示。

**SessionState（逻辑协议，不强制具体类名）：**

- `session_id: str`（必填，唯一标识；用于 memory tags、lane/lock key、事件聚合）
- `lane_key: str`（默认 `session:{session_id}`，用于并发 lanes）
- `domain: str`（例如 `core|desktop|web|legal|trading|...`）
- `environment: str`（`sandbox|staging|prod`）
- `parent_session_id: Optional[str]`（子会话/子 agent 继承）
- `branch_id: Optional[str]`（分支/回放）
- `metadata: dict[str, Any]`（保留字段见下）

**保留的 metadata keys（跨模块约定，不得滥用）：**

- `session_id`：必须与 SessionState 同步
- `is_subagent: bool`
- `provider_override: Optional[str]`
- `model_override: Optional[str]`
- `think_level: Optional[str]`
- `timeout: Optional[float]`

**并发一致性要求（必须满足）：**

- 同一 `session_id` 的主循环执行必须串行（lane/lock 生效），禁止并发写入导致上下文污染。

### 3.2 EventProtocol v1

EventProtocol 解决：OpenClaw 风格的细粒度订阅（turn/tool/message/compaction），为 UI/渠道网关/审计提供稳定接口。

**事件信封（BrainEvent）：**

- `event_id: str`
- `ts_utc: str`（UTC ISO）
- `session_id: str`
- `trace_id: Optional[str]`
- `turn_id: Optional[str]`
- `type: str`
- `payload: dict[str, Any]`

**必须支持的事件类型（最小集）：**

- `agent_start` / `agent_end`
- `turn_start` / `turn_end`
- `message_start` / `message_delta` / `message_end`
- `tool_execution_start` / `tool_execution_update` / `tool_execution_end`
- `compaction_start` / `compaction_end`
- `error`

约束：

- 事件必须通过统一 emitter 发出（底层可复用 `SystemEventQueue`），禁止用 `print` 充当事件协议。
- 上层 UI/渠道/网关只能消费事件，不得解析原始 stdout 拼协议。

### 3.3 StreamingProtocol v1

StreamingProtocol 解决：流式输出分块、标签/指令、silent reply 的唯一规范。

**StreamChunk（逻辑协议）：**

- `kind: str`（`text_delta|final_text|tool_call|tool_result|directive|...`）
- `text: str`（可选）
- `meta: dict[str, Any]`（可选）

**指令与标签：**

- canonical silent reply：`[[SILENT_REPLY]]`
  - 语义：当系统已通过其他通道推送/广播消息，当前回复应保持静默以避免重复。
  - 规则：必须是完整消息且无其他文本。

## 4. 弃用清单（Deprecations）

以下项在本 RFC 生效后进入弃用：

1. `quentin.runtime.cognitive_loop.CognitiveLoop`：仅允许作为 facade（把旧 TaskRequest/TaskResult 映射到 canonical CognitiveTask/CognitiveResult），禁止承载核心执行逻辑。
2. `quentin.runtime.system.MetaAgentRuntime`：逐步改为 facade/runtime 容器入口，最终迁移到 `Container` + canonical loop。
3. 业务代码直接 import `quentin.cognitive.loop_impl`：改用 `quentin.cognitive.loop`（测试/内部审计工具可例外）。
4. 多套 silent token：必须由 `quentin.runtime.silent_protocol.SILENT_REPLY_TOKEN` 单点定义。

## 5. 迁移顺序（严格按顺序合并，避免碎片化扩大）

### Phase 0（立即执行）

- 添加 `arch_ci_gate`：
  - 扫描 banned imports（例如 `MetaAgentRuntime` 入口的新增使用）
  - 禁止业务代码直接 import `quentin.runtime.cognitive_loop`（仅 `quentin/runtime/system.py` 可作为兼容 facade 使用）
  - silent token 一致性
  - canonical 入口唯一性（禁止非测试代码 import `loop_impl`）

### Phase 1（收敛导入路径）

- 将非测试代码的 `from quentin.cognitive.loop_impl import ...` 全部迁移到 `from quentin.cognitive.loop import ...`。

### Phase 2（Runtime 入口降级为 facade）

- 把 `quentin.runtime.cognitive_loop` 改为纯映射层：
  - 不自建 council/planner/executor
  - 只负责把旧结构映射为 canonical task/result，并调用 canonical loop
- 把脚本/服务入口逐步迁移到 `Container().cognitive_loop`。

### Phase 3（协议化接入点）

- SessionProtocol（session store / compaction policy）落地为唯一会话模型。
- EventProtocol + StreamingProtocol 落地为唯一事件/输出管道。

## 6. CI Gate（arch_ci_gate）准入规则

arch_ci_gate 的原则：

- 先“冻结”现状为 allowlist，只禁止新增碎片化入口。
- 每迁移一批 legacy 用法，就缩小 allowlist，直到 legacy 入口为 0。
