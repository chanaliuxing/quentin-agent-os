````markdown
# BLUEPRINT PATCH-2025-001: Dual-Track Learning & MCP Tool Layer with AI Council

- **Status**: Proposed  
- **Author**: Wei + Meta-Agent  
- **Date**: 2025-12-10  
- **Target Document**: Meta-Agent Blueprint v3 文件位置: meta_ai.md
- **Patch Type**: Architecture (Learning / Tools / Governance)  
- **Related Topics**:  
  - Git-Native Self-Programming  
  - Model Context Protocol (MCP)  
  - Memory Fabric / Skill Evolution  
  - AI Council（多智能体治理）

---

## 1. 背景与问题（Context & Problem）

在现有 **Meta-Agent 蓝皮书 v3** 中：

- “学习 / 进化” 能力主要集中在：
  - 记忆分层（Memory Fabric）
  - 自编程引擎（Self-Programming Engine）
- 对“技能 / 工具”获取的默认路径是：
  - 发现能力缺口（Capability Gap） → 启动自编程 → 写代码 → 测试 → 落地

随着 **MCP（Model Context Protocol）生态** 的成熟以及 Git-Native 自编程框架的成型，出现了几个明显问题：

1. **单轨自编程成本过高**

   - 任何新能力都通过“写代码”获取：
     - 开发慢、Token 消耗大、出错风险高；
     - 对本地 LLM 负担重（上下文 & 代码量不断膨胀）。
   - 已经存在大量开源 MCP Server（数据库、GitHub、Filesystem、Slack 等）可以复用，但 v3 没有把它们作为一等公民纳入蓝皮书。

2. **工具安全治理设计过重 / 过人类中心**

   - 早期设想：通过 Human-in-the-Loop 终端确认（Y/N）来审批新工具与高风险行为。
   - 对当前 **本地 / 个人 Agent** 场景而言：
     - 这种治理方式过于“企业化”（RBAC / Audit / Compliance 级别），会压制自演化节奏；
     - 与 “让 AI 自己开会、自己协商决策” 的长期方向不完全一致。

3. **蓝皮书中缺少对“外部工具 + 内部自编程”明确的职责边界**

   - 目前所有能力都被混在“自改代码”这个篮子里；
   - 没有清晰说明：
     - 哪些能力应该 **优先“买（挂载工具）”**，
     - 哪些能力才需要 **“造（自编程）”**。

---

## 2. 目标与非目标（Goals & Non-Goals）

### 2.1 Goals

本 Patch 旨在对蓝皮书 v3 做一次 **学习 / 工具 / 进化子系统的结构性升级**，具体目标：

- **G1：引入“双轨能力获取策略（Dual-Track Capability Acquisition）”**
  - 路径 A：内源进化（Endogenous Evolution / Self-Programming）
  - 路径 B：外源获取（Exogenous Acquisition / MCP Tools）
  - 在蓝皮书层面把这两个路径的触发条件、流程与边界写清楚。

- **G2：增加“工具学习与集成层（MCP Tool Learning & Integration Layer）”**
  - 把 MCP 工具生态纳入 L1 Base Layer 的一等公民模块；
  - 定义 ToolDiscovery / ToolLearning / ToolRegistry / ToolInvocation 的职责。

- **G3：用“AI Council”取代人类 Y/N 审批，作为治理核心**
  - RiskAgent / CapabilityAgent / CostAgent /（可扩展 DomainAgent）组成多智能体委员会；
  - 对于工具接入 / 能力升级 / Patch 合并等高影响变更进行自动化审议；
  - 人类只需设定少量“不能越过的红线”（Safety Kernel）。

- **G4：保持治理“轻量且可扩展”**
  - 当前场景以本地单用户为主，不引入复杂 RBAC / 合规系统；
  - 但蓝皮书设计允许将来扩展至多用户 / 企业环境。

### 2.2 Non-Goals

- 本 Patch **不**：
  - 引入企业级 IAM / RBAC / 全面审计流水线；
  - 改变 v3 中已经声明的 **Safety Kernel / Kernel 不可修改边界**；
  - 要求立即实现所有代码细节，仅更新蓝皮书架构与后续演进路线。

---

## 3. 高层设计（High-Level Design）

本 Patch 在原有 v3 架构上做三处关键增强：

1. **在能力获取层面，从「单轨自编程」升级为「双轨进化」**
   - 能力缺口出现时：
     - 优先尝试从 MCP 生态“采购”标准能力（如 DB、FS、GitHub、Web 搜索等）；
     - 只有当工具不可用 / 不适合时，才动用自编程引擎改代码。

2. **在 L1 Base Layer 增加“工具学习与集成层”**
   - 将 MCP Client + Tool Discovery + ToolLearning + ToolRegistry 组合为一个独立模块：
     - 为 Planner / Orchestrator 提供“工具目录”与“工具调用接口”；
     - 与 Memory Fabric 协作，长期积累工具使用经验。

3. **在 L2 Meta Layer 中显式引入“AI Council”组件**
   - 由多个具备不同偏好的 Agent 组成：
     - RiskAgent（安全 / 风险）
     - CapabilityAgent（能力 / 覆盖度）
     - CostAgent（成本 / 效率）
     - （可选）DomainAgent（领域相关性）
   - 针对高影响决策（工具接入、Patch 合并、技能升级）给出集体决议。

---

## 4. 具体文档改动（Concrete Blueprint Changes）

> 以下改动均针对现有 **Meta-Agent Blueprint v3 主文档**。

### 4.1 对「0. 定位 & 边界」章节的补充

在 `0.1 系统是什么（更新版）` 下新增一段说明：

> 系统获取新能力不再单纯依赖“自编程”，而是采用 **双轨能力获取策略**：
> - **外源能力（Exogenous Skills）**：通过 MCP 挂载现有工具与服务（如文件系统、数据库、GitHub、Web 搜索等），优先复用外部生态。
> - **内源能力（Endogenous Evolution）**：通过 Git-Native 自编程引擎，对系统内部逻辑、性能及特定领域策略进行演化优化。
> 这两条路径的选择由 Blueprint Loop 与 AI Council 协同决策。

在 `0.2 v3 的新增目标` 中追加一条：

> 4. 建立一套 **工具优先、自编程兜底** 的能力获取策略，显式利用 MCP 生态来减少重复造轮子。

---

### 4.2 对「1. 总体架构」章节的更新

在 `1.1 四层智能结构（Logic Layers v3）` 的 L1 Base Layer 中：

- 原来的：
  - `Tool & Skill Manager`（单一模块）

- 更新为两个并列模块：
  - `Self-Programming Engine`（自编程引擎，用于内源进化）
  - `MCP Tool Learning & Integration Layer`（MCP 工具学习与集成层，用于外源获取）

在 L2 Meta Layer 中新增：

- `AI Council` 组件，说明：
  - 负责针对高影响变更（工具接入、Patch 合并、权限升级）给出治理决议；
  - 与 Self-Improvement Manager / Immune Loop / Evolution Strategy Manager 协同工作。

---

### 4.3 新增「第 5 章：学习与进化系统 v3.1」

- 用本 Patch 第 6 节提供的 `5.x` 章节文本，替换或合并原文档中分散的“学习 / 自编程 / 工具”描述；
- 新第 5 章结构如下：
  - 5.1 核心战略：双轨进化（Dual-Track Evolution）
  - 5.2 路径 A：自编程引擎（Self-Programming Engine）
  - 5.3 路径 B：MCP 工具学习与集成层（MCP Tool Learning & Integration Layer）
  - 5.4 工具知识记忆（Tool Knowledge Memory, TOOL_KNOWLEDGE）
  - 5.5 AI Council 治理机制（AI-Only Governance）
  - （可选）5.6 与其它层的接口说明

---

## 5. 安全与治理更改（Governance & Safety Changes）

本 Patch 在治理设计上作如下调整：

1. **删除 / 弱化：Human-in-the-Loop 终端交互式确认**
   - 不再依赖用户在终端频繁输入 `y/n` 来审批每一个工具 / Patch；
   - 保留“人类可配置红线（Safety Kernel 不可改 / 交易上限 / 法律域关键约束）”的顶层设计。

2. **新增：AI Council 治理机制（多智能体开会决策）**

   - 对以下类型的变更，由 AI Council 自动开会表决：
     - 安装新的 MCP Server / 工具；
     - 将工具从 `experimental` 升级为 `trusted`；
     - 将自编程产生的 Patch 从 Sandbox 提升到 Staging / Production；
     - 对 Memory / Skill 的重要结构性变更。

   - Council 成员示例：
     - **RiskAgent**：安全与风险优先，有一票否决权；
     - **CapabilityAgent**：关注能力覆盖、是否解决问题；
     - **CostAgent**：关注算力 / Token / 维护成本；
     - **DomainAgent（可选）**：对 Trading / Legal / Desktop 各自独立。

   - 决策原则（示例）：
     - 若 RiskAgent 明确反对 → 直接拒绝；
     - 否则，若 CapabilityAgent + CostAgent 均通过 → 通过；
     - 否则 → 要求补充信息 / 重新生成方案。

3. **保留：Safety Kernel 的不可变红线**

   - 无论 Council 如何表决，以下内容仍不可由 AI 修改：
     - `kernel/` 目录下的安全 / 权限 / 回滚核心；
     - 关键 Schema（Memory / Trace / Patch 的结构定义）；
     - 法律域 / 交易域的某些硬性风控规则（如持仓上限、禁止绕过合规检查）。

---

## 6. 新文本草案（New Blueprint Text Draft）

> **说明：** 以下文本为蓝皮书 v3.1 的 **第 5 章“学习与进化系统”** 完整新版草案，  
> 可直接替换主蓝皮书中原有的第 5 章内容。

---

# 5. 学习与进化系统 v3.1

**Status:** Core | **Scope:** 全局（跨 Desktop / Legal / Trading 等域）  
**Key Idea:** 双轨进化（自编程 + MCP 工具），由 AI Council 治理。

---

## 5.1 核心战略：双轨进化（Dual-Track Evolution）

Meta-Agent 不再假设“所有能力都要自己写代码实现”，而是采用：

- **路径 A：内源进化（Endogenous Evolution / Self-Programming）**
  - 面向内部逻辑、算法、性能和特定领域策略；
  - 通过 Git-Native 自编程引擎生成、测试、评估 Patch；
  - 在受控范围内更新 `mutable/` 下被标记为可演化的模块。

- **路径 B：外源获取（Exogenous Acquisition / MCP Tools）**
  - 面向标准化的外部能力：
    - 文件系统操作、数据库访问、HTTP / API 请求、GitHub / Slack / Notion 等 SaaS；
  - 通过 MCP 生态“挂载”现有工具（MCP Server），而不是重复造轮子。

### 5.1.1 能力缺口分诊流程（Capability Triage）

当系统检测到一个 **能力缺口（Capability Gap）** 时，执行：

1. **能力分析（由 Planner + Self-Improvement Manager 完成）**
   - 抽象出缺口描述，例如：
     - “需要读取本地 PDF 并提取表格数据”
     - “需要访问 Postgres 数据库执行简单查询”
     - “需要对内部 Planner 策略进行性能优化”

2. **工具可用性检查（Tool-First）**
   - 调用 `MCP Tool Discovery`：
     - 查询本地配置 + MCP Registry（如 mcp.so / smithery）；
     - 查询 Memory Fabric 中已有的 TOOL_KNOWLEDGE；
   - 若发现一个或多个匹配度高的工具：
     - 构造 Tool Proposal（包括：候选 Server、工具列表、预估风险与成本）；
     - 提交给 AI Council 审议；
     - 审议通过后 → 进入路径 B。

3. **自编程兜底**
   - 若不存在合适工具，或 Council 认为“此处更适合内部实现”：
     - 构造 Self-Programming Proposal；
     - 启动自编程引擎，在 Git 沙盒中生成 Patch；
     - 审议通过后 → 合并到对应模块。

> **原则：能买就不造，能挂载工具就不写代码，自编程只为系统内功服务。**

---

## 5.2 路径 A：自编程引擎（Self-Programming Engine）

自编程引擎是 Meta-Agent 的内部演化中枢，对应工程目录 `meta_agent/self_programming/`。

### 5.2.1 角色与组件

- **Programming Team（多角色 Agent 流水线）**
  - **Architect Agent**
    - 读取 Gap / Proposal；
    - 理解现有代码结构与依赖；
    - 输出 JSON 格式的开发计划 `DevPlan`（文件级 / 函数级改动列表）。
  - **Programmer Agent**
    - 基于 `DevPlan` 在 Git 分支中生成代码；
    - 严格使用 `SEARCH / REPLACE` / `ANCHOR + INSERT` 形式的 Patch，而非整文件重写。
  - **Tester Agent**
    - 为改动生成 / 补全测试；
    - 运行 `pytest` / 集成测试 / 快速基准。
  - **Reviewer Agent**
    - 检查逻辑正确性、风格与一致性；
    - 输出结构化 Review 报告，附带审议建议。

- **基础设施（Infra）**
  - **GitSafetyLayer**
    - 每个自编程任务使用独立分支：`ai-dev/<task_id>`；
    - 所有改动必须在分支上完成；
    - 只有在测试与 Council 审议通过后，才允许合并到 `main` 或对应长期分支；
    - 测试失败或 Council 否决 → 回滚分支，主干不受影响。
  - **FilePatcher**
    - 提供稳健的模糊匹配 / 代码片段插入能力；
    - 保证 Patch 幂等，避免重复插入 / 重复修改同一段代码。

### 5.2.2 自编程工作流（简要）

1. `Gap` → 构造 `SelfProgrammingProposal`
2. `GitSafetyLayer` 创建 `ai-dev/<task_id>` 分支
3. Architect 生成 `DevPlan`
4. Programmer 根据计划生成 Patch
5. Tester 运行自动化测试（单测 / 回归 / 关键静态分析）
6. 汇总结果，生成 `PatchReport`
7. 提交给 AI Council 审议（特别是 RiskAgent）
8. 通过 → 合并；不通过 → 回滚或重试

---

## 5.3 路径 B：MCP 工具学习与集成层（MCP Tool Learning & Integration Layer）

MCP 工具学习与集成层是 Meta-Agent 的“机械外骨骼”，对应工程目录：

```text
meta_agent/
  self_programming/
    mcp_integration/
      client.py        # MCP Client：连接 server
      discovery.py     # 工具发现与检索
      tool_adapter.py  # MCP Tool -> 内部 CodeTool 适配
  tools/
    registry.py        # 全局工具注册表（统一暴露给 Planner / Executor）
````

### 5.3.1 核心职责

1. **工具发现（Tool Discovery）**

   * 对外：

     * 查询 MCP Registry（mcp.so / smithery 等）；
     * 构建候选 MCP Server 列表。
   * 对内：

     * 查询 Memory Fabric 中已有的 TOOL_KNOWLEDGE；
     * 查询本地配置中已经安装的工具。

2. **工具学习（Tool Learning）**

   * 基于 MCP 工具提供的 JSON Schema：

     * 解析参数、返回类型、错误类型；
     * 使用 LLM 自动生成使用示例（Examples）与调用模式；
     * 将这些信息写入 Memory Fabric 的 TOOL_KNOWLEDGE 区域。

3. **工具集成（Tool Integration）**

   * 将 MCP 工具包装为统一的 CodeTool 接口：

     * 供 Planner / Executor / Domain Agents 调用；
     * 对上层屏蔽传输细节（stdio / sse / WebSocket）。

4. **工具生命周期管理（Tool Lifecycle）**

   * 工具状态：

     * `experimental`：刚接入，需限制调用范围；
     * `trusted`：通过若干成功实验与 Council 审议后；
     * `deprecated`：不再推荐使用，但保留历史记录；
   * 统计信息：

     * 调用次数、成功率、平均延迟、错误模式；
   * 提供数据给 AI Council 和 Self-Improvement Manager。

### 5.3.2 示例：从 Gap 到 MCP 工具调用

以“需要读取 Notion 文档” 为例：

1. Gap：`"无法访问 Notion 笔记"`
2. Tool Discovery：

   * 在 Registry 中发现 `notion-mcp`；
   * 在 Memory 中没有现有工具。
3. Tool Learning：

   * 读取 `notion-mcp` 提供的工具列表：

     * `list_pages`, `get_page`, `search_blocks` 等；
   * 自动生成示例调用与使用说明；
   * 写入 TOOL_KNOWLEDGE。
4. AI Council 审议：

   * RiskAgent：检查权限需求与潜在数据泄露风险；
   * CapabilityAgent：确认其功能满足需求；
   * CostAgent：评估维护成本与调用代价；
   * 通过 → 工具状态设为 `experimental`。
5. Planner 使用：

   * 在具体任务中调用该工具；
   * 收集统计信息与错误日志；
   * 若表现稳定 → 通过 Council 再次审议后升级为 `trusted`。

---

## 5.4 工具知识记忆（Tool Knowledge Memory, TOOL_KNOWLEDGE）

TOOL_KNOWLEDGE 是 Memory Fabric 中专门面向工具 / 技能的子空间，用于存储工具的“元知识”。

### 5.4.1 典型 Schema（概念级）

```jsonc
{
  "type": "TOOL_KNOWLEDGE",
  "tool_id": "github/create_issue",
  "server": "server-github",
  "signature": "create_issue(owner: string, repo: string, title: string, body?: string)",
  "description": "Create a GitHub issue in the specified repository.",
  "examples": [
    {
      "input": {
        "owner": "meta-agent",
        "repo": "core",
        "title": "Bug: self-programming patch failure"
      },
      "usage_note": "Minimal example without body; used for quick bug filing."
    }
  ],
  "metrics": {
    "call_count": 17,
    "success_rate": 0.94,
    "avg_latency_ms": 220,
    "last_used_at": "2025-12-10T08:30:00Z"
  },
  "governance": {
    "state": "trusted",           // experimental | trusted | deprecated
    "risk_level": "medium",       // low | medium | high
    "domain_scope": ["devops"],   // 可选域标签
    "council_score": 0.87         // 上次审议的综合评分
  }
}
```

### 5.4.2 用途

* Planner / Executor：

  * 通过查询 TOOL_KNOWLEDGE 决定：

    * 用哪个工具最适合当前任务；
    * 需不需要 fallback 到其它工具或自编程。
* AI Council：

  * 审议时使用历史指标与治理字段作为参考；
  * 对高失败率 / 高风险工具发起降级或废弃提案。
* Self-Improvement Manager：

  * 识别哪些工具值得进一步优化；
  * 是否需要通过自编程包装工具成为更高层的技能（Skill）。

---

## 5.5 AI Council 治理机制（AI-Only Governance）

AI Council 是运行在 L2 Meta Layer 的多智能体治理组件，负责对 **高影响决策** 进行自动化审议与裁决。

### 5.5.1 何时触发 Council

以下操作必须提交给 Council：

1. 安装新的 MCP Server 或首次使用的高风险工具（如 Filesystem / Shell / DB 写操作）。
2. 将工具从 `experimental` 升级为 `trusted`。
3. 将自编程产生的 Patch 从 Sandbox / Staging 合并到 Production 分支。
4. 修改 Memory Fabric 的结构性配置（如某些 Memory Tier 的规则）。
5. 对 Trading / Legal 域的关键策略进行调整或替换。

### 5.5.2 典型成员与职责

* **RiskAgent**

  * 审视安全风险、权限范围、潜在数据泄露与合规问题；
  * 拥有对高风险决策的一票否决权。

* **CapabilityAgent**

  * 评估提案是否真正解决了目标能力缺口；
  * 检查是否存在更简单或已有替代方案。

* **CostAgent**

  * 评估算力 / Token / 人工维护成本；
  * 避免“为小收益引入巨大复杂度”的情况。

* **DomainAgent（可选，多实例）**

  * 针对不同域（Desktop / Legal / Trading）给予特定判断；
  * 例如：Trading 域必须更保守，Legal 域必须坚持合规与解释性。

### 5.5.3 审议流程（简要）

1. **Proposal 构建**

   * 由触发方（Self-Programming Engine / Tool Layer / Immune Loop）构建结构化 `Proposal`：

     * 变更描述（Text + Diff / 工具列表）；
     * 相关 Trace / Metrics 的摘要；
     * 预估收益与风险。

2. **多 Agent 审阅与投票**

   * 各 Agent 并行阅读 Proposal 与相关 Memory / Metrics；
   * 输出：

     * `vote`：approve / reject / revise
     * `rationale`：理由（结构化文本）
     * 可选：建议的修改方向或附加约束。

3. **决策聚合**

   * 规则示例：

     * 若 RiskAgent = reject → 总体决策 = reject；
     * 否则，若 CapabilityAgent + CostAgent 均 approve → 总体决策 = approve；
     * 其他情况 → 进入 revise 状态，由触发方调整方案后可再次提交。

4. **决策落地**

   * approve：

     * 对工具：更新 Tool Registry 状态（如从 experimental → trusted）；
     * 对 Patch：触发合并流程；
     * 对策略：写入相应配置或代码模块。
   * reject：

     * 将 Proposal 与 Council 意见写入 Memory，作为未来决策参考；
     * 如有必要，通知 Immune Loop 进行降级 / 回滚。
   * revise：

     * 由触发模块根据理由重写 Proposal 或 Patch，再次提交。

### 5.5.4 Safety Kernel 边界

* 无论 Council 决策如何，以下内容 **不可被修改**：

  * `kernel/` 下的安全 / 权限 / 回滚逻辑；
  * 核心数据结构的 Schema 定义（Memory / Trace / Patch）；
  * Trading / Legal 域指定的“硬风控 / 硬合规规则”。

> 换句话说：Council 负责“怎么更好地利用轮子 / 装新轮子”，
> 但不能“拆车架”——车架由人类作为系统设计者最终定义。

---

## 5.6 与其它层的接口（简要）

* 与 **L0 Safety Kernel**：

  * 自编程与工具层均必须通过 Kernel 提供的 API 来执行高危操作；
  * Kernel 强制执行权限限制与回滚策略。

* 与 **L1 Base Layer（Planner / Orchestrator / Memory Fabric）**：

  * Planner 在制定执行计划时，可以从 Tool Registry 与 TOOL_KNOWLEDGE 中选择工具；
  * Orchestrator 负责把实际调用路由到 MCP Tool / Local Skill / Self-Programming 改造后的模块。

* 与 **L2 Meta Layer（Self-Improvement Manager / Immune Loop / Eval Harness）**：

  * Immune Loop 在发现异常（高错误率 / 高延迟）时，可以对工具或模块发起“降级 / 替换” Proposal；
  * Self-Improvement Manager 根据长期数据，决定将资源投入在：

    * 增加新工具；
    * 优化旧技能；
    * 改进自编程策略。

* 与 **L3 Research & Evolution Layer**：

  * Experiment Orchestrator 可以将不同工具组合 / 不同补丁版本视为不同实验 Variant；
  * Evolution Strategy Manager 利用实验结果优化：

    * 工具选择策略；
    * 自编程修改优先级；
    * Council 里的各 Agent 权重（高级阶段可引入）。

---

## 7. 迁移与兼容性（Compatibility & Migration）

* 对现有 v3 蓝皮书：

  * 所有关于 Memory Fabric、自编程引擎的内容仍然有效；
  * 本 Patch 主要：

    * 增加 MCP 工具路径与 Tool Layer；
    * 引入双轨决策逻辑；
    * 引入 AI Council 治理框架。

* 对现有代码实现：

  * 本 Patch 处于架构与文档层面；
  * 实际实现可以分 Phase 逐步落地（例如：先实现 ToolRegistry + 简单 Council，再扩展 Discovery / Learning）。

---

## 8. 风险与开放问题（Risks & Open Questions）

* 工具与 Patch 数量增多后，Council 的决策复杂度是否会过高？
* Council 成员是否需要基于历史表现进行加权投票？
* 不同域（Trading vs Desktop）是否需要拥有独立的 Council 或不同的安全阈值？
* 怎样在不牺牲速度的前提下，让 Council 保持足够的保守性？

---

## 9. 决议（Decision & Status）

* 当前状态：`Proposed`
* 待：

  * 初始 AI Council v1 实装；
  * 对若干真实场景进行试运行（如 Desktop 工具接入、简单 Patch 审议）；
  * 根据运行结果微调 Council 规则。
* 通过后将状态更新为：`Approved`，并在主蓝皮书标注：

> “第 5 章《学习与进化系统》已由 `BLUEPRINT_PATCH-2025-001` 更新。”

```

::contentReference[oaicite:0]{index=0}
```
