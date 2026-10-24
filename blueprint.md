Meta-Agent 工程落地蓝皮书 v3.1代号：Project Quentin副标题：Dual-Track & MCP Edition（双轨进化 + MCP 工具生态版）

0. 定位 & 边界：v3.1 比 v3 多了什么？
   0.1 系统是什么（更新版）
   一个运行在本地（或云端）的 “自进化 AI 操作系统”，具备：

* 能接不同领域的任务（Desktop 自动化 / LegalBot / Trading / 以后更多）
* 能拆解、执行、记录、反思任务
* 能在受控范围内：

  * 更新自己的记忆（知识和技能）
  * 生成并测试新工具 / 新代码
  * 持续引入外部工具能力（MCP）
  * 决定下一步在哪里投入“自我改进的资源”
    与 v3 的关键差异：
    v3.1 正式引入三件大事：

1. 双轨能力获取（Dual-Track Acquisition）

   * 不再“所有 Gap 都去写代码”；
   * 而是：能用 MCP 工具，就用工具；工具没有 / 不合适，再启动自编程引擎。
2. MCP 工具学习层（Tool Learning & MCP Integration Layer）

   * 新增一个“工具学习层”，负责：

     * 在 MCP 生态里发现工具
     * 学习工具的使用方法
     * 把工具封装成内部 Skill
     * 管理工具全生命周期（启用 / 退役 / 统计）
3. AI Council 治理（AI 治理委员会，而非人类点 Y/N）

   * 工具接入与能力变更的关键决策，由多 Agent 组成的治理委员会（Council）投票完成；
   * 人类只负责制定“宪法级规则”和总开关，而不是天天在终端里按 Y/N。

0.2 v3.1 的新增目标 ✅
在 v3 的三大目标基础上，v3.1 新增：

1. 双轨能力供应链（工具优先 + 自编程兜底）

   * 建立明确的能力获取决策树：

     * 标准化外部能力 → MCP 采购（工具路径）
     * 内部逻辑 / 性能 / 算法 → 自编程（代码路径）
2. 工具知识记忆（Tool Knowledge Memory）

   * 每一个工具都有自己的“知识卡片”：

     * Signature / 使用示例 / 成功率 / 失败率 / 时延 / 风险等级；
   * 由 Memory Fabric 长期管理，支持：

     * 工具选择优化
     * AI Council 决策参考
     * 工具退役 / 替换
3. 轻量但真实可用的安全治理

   * 面向当前单机 / 单用户场景：

     * 不搞重型 RBAC 和合规系统；
     * 但坚持：来源过滤 + AI Council 决策 + 沙箱执行；
   * 将未来企业化的重治理，定义为“可升级层”，而不是一开始就背上所有复杂度。

【新增：v3.1+ 认知架构补强目标（不改变 v3.1 既有目标，仅补齐“人脑缺失件”）✅】
4. 认知入口标准化（Context Framing / Attention Gating）
* 在进入 Planner 前，先完成“情境判定 + 注意力裁剪”；
* 目标：减少 UI/日志噪音，提升决策稳定性与速度。
5. 预测驱动执行（Predictive Processing）
* 系统在执行前先建立“期望状态”，执行后只处理“预测误差”；
* 目标：把“看见再反应”升级为“先预测再校正”，显著降成本、提效率。
6. 情境→技能直连（Situation → Skill Mapping）
* 高频场景不再每次走完整 Planner；
* 由情境直接触发已验证的 Procedural Skill（反射式执行）。
7. 要点记忆（Gist Memory）
* 不把所有 Trace 细节长期保存；
* 仅保留可复用的“骨架规律”（gist），降低记忆膨胀和过拟合历史。

0.3 非目标（v3.1 重申） ❌

1. 不追求“完全无人类监督”的彻底自治系统。

   * 人类依然是：宪法制定者 & 总开关控制者。

2. 不允许 AI 改动：

   * 安全内核（权限 / 限流 / 回滚 / 宪法）
   * 核心数据协议（Memory / Trace / Patch / Tool-Knowledge 的 schema）

3. 不追求一次性解决所有研究问题：

   * 全面自治的架构重构
   * 完整的企业级 IAM / 合规系统
   * 极其复杂的多智能体博弈

4. 总体架构：四层控制 + 三环境 + 工具学习层
   1.1 四层智能结构（Logic Layers v3.1）
   延续 v3 的 4 层结构，但明确把“工具学习 / MCP 集成”视为 L1 的关键子系统，同时在 L3/L0 增强治理逻辑。
   L3 Research & Evolution Layer（研究与演化策略层）

* Experiment Orchestrator

  * 管理实验队列：新 Planner、不同工具组合、自编程策略等。
* Evolution Strategy Manager

  * 决策在哪些模块 / 能力上投入自我改进。
* Budget & Cost Controller

  * 控制算力 / Token / 资金消耗。
* Policy & Governance（宪法）

  * 规定：哪些模块可变、哪些模块永远只读；
  * 定义 AI Council 的角色 / 权限边界。
    L2 Meta Layer（评估 & 自改调度层）
* Log & Metrics Store

  * 所有域的日志 / Trace / 指标统一汇总。
* Eval Harness

  * 离线 / 在线评测框架，支持 A/B 测试。
* Self-Improvement Manager

  * 驱动自编程 / 工具演化的总控逻辑：

    * 发现表现差的模块 → 提出改进任务。
* Multi-Agent Coordinator

  * 管理多 Agent 协作（Speed / Safety / Cost / Domain 等）。
    AI Council 就是 Meta Layer 下的一个特殊多 Agent 组合，专职治理：工具接入、安全策略、自改范围。
    L1 Base Layer（执行 & 能力层）
* Orchestrator / Task Router

  * 接任务 / 拆任务 / 分配到各域。
* Planner (Hierarchical)

  * 生成长短期计划，选择使用的技能 / 工具 / 模型。
* Executor

  * 具体执行动作：API 调用 / shell / Desktop 自动化等。
* Memory Fabric

  * STS / MTS / LTS 分层记忆系统（见第 2 章）。
* Tool & Skill Manager（重点升级）

  * 不再是一个大杂烩，而是拆成：

    * Self-Programming Engine（内部代码演化）
    * Tool Learning & MCP Integration Layer（外部工具学习与挂载）
* Critic & Self-Correction

  * 任务内反思与重试。
* Model Router

  * 在 gpt / deepseek / llama / 本地模型间选路。

【新增：L1 认知入口层（Perception & Context Layer，插入在 Planner/Executor 之前；不替换、不删原模块）】

* Perception & Context Layer（认知入口层）

  * Situation Classifier（情境识别 / Context Framing）

    * 判定当前“处于哪个场景/页面/模式”（如：聊天页/帖子页/设置页/异常弹窗/登录态失效等）
    * 输出：situation_id + confidence + situation_features
  * Attention Filter（注意力裁剪 / Attention Gating）

    * 从 UI Tree / OCR / DOM / Logs 中裁剪“最相关 5%–20%”
    * 输出：attention_pack（供 Planner 使用的精简上下文）
    * 指标：attention_reduction_ratio（裁剪比例）与决策成功率关联分析
  * Expectation Engine（期望状态 / Predictive Processing）

    * 执行前生成 expected_state（期望 UI/系统状态）
    * 执行后计算 prediction_error（预测误差），只对误差进行诊断与修复
  * Situation → Skill Router（情境→技能直连）

    * 如果 situation_id 命中高置信“已验证 Procedural Skill”，可跳过 Planner 的深思，直接触发技能
    * 保留 Safety Kernel 约束：高风险域仍需策略 Gate（见 4.2 / 5.3）

【落地路线（1 -> 2 -> 3，模块化/可插拔）】
1. 认知入口层先落地（Perception & Context Layer）
   - 插拔点：`SituationClassifier` / `AttentionFilter` / `ExpectationEngine` / `SituationSkillRouter`
   - 接入点：CognitiveLoop 在 Planner 前产出 `perception_snapshot`，Planner 默认仅消费 `attention_pack`
   - 开关：`config/cognitive_policies.yaml`（可全局禁用或仅记录不生效）
2. Predictive Execution + 记忆压缩（Predictive First + Gist Memory）
   - 插拔点：ExpectedState 模板、PredictionError 分类、修复策略映射（可由配置/策略模块替换）
   - 接入点：Executor step 前后 hooks；SleepLoop 产出 gist 并回注 Planner
3. 工具生态接入与治理（MCP Tool Provider + ToolKnowledge + Council）
   - 插拔点：ToolProvider（MCP 后端可替换）、ToolUsageSink（写回策略可替换）、Tool Governance Gate（投票/策略可替换）
   - 默认：`config/mcp_security.yaml` 关闭 MCP（需显式开启，且高风险域默认禁用自动接入）
   - 详细落地清单（可执行 TODO）：`docs/improve/BLUEPRINT_V3_1_BRAIN_UPGRADE_TODO_2026-02-10.md`

L0 Infra & Kernel Layer（基础设施层）

* Safety Kernel

  * 权限 / 风控 / 回滚 / 宪法执行者；
  * 负责约束：AI Council 决议只能在“可变区”里生效。
* Storage

  * DB / 向量库 / 对象存储 / 本地文件。
* Runtime

  * Docker / K8s / 本地进程（uvx / npx 等）。

1.2 三环境（Execution Environments）
保持 v2/v3 的划分：Sandbox / Staging / Production，但和自编程 & MCP 更紧耦合：

* Sandbox

  * 所有新工具（MCP）、新技能、新 Patch 的唯一入口。
* Staging / Shadow

  * 少量真实流量试跑；
  * 用于对比新旧方案。
* Production

  * 只运行通过评估的稳定版本；
  * Safety Kernel 确保：任何变更必须来自 Sandbox → Staging 的流程。

2. Memory Fabric：三层记忆 + 工具知识
   2.1 三层记忆体系
   与 v3 相同，记忆分为：

* Short-Term Store (STS)

  * 会话级 / 任务级上下文（分钟 / 小时）
* Mid-Term Store (MTS)

  * 项目级 / 版本级记忆（天 / 周）
* Long-Term Store (LTS)

  * 跨项目 / 跨版本稳定知识（周 / 月 / 年）
    每条记忆在 v2 schema 基础上新增字段：
    {
    "memory_tier": "STS | MTS | LTS",
    "update_policy": {
    "promotion_rule": "...",
    "decay_rule": "...",
    "consolidation_batch": "nightly | weekly | manual"
    }
    }
    迁移规则简述：
* Episodic 先进入 STS；
* Sleep Loop 多次引用 / 多任务复用 → 升级到 MTS；
* 跨多个 domain 被稳定复用 → 升级到 LTS；
* STS 定期清理；MTS 可压缩；LTS 只通过 supersedes 替换，而不是直接删除。
  2.2 工具知识记忆（Tool Knowledge Memory）
  新增一个 Memory 类型：TOOL_KNOWLEDGE
  {
  "type": "TOOL_KNOWLEDGE",
  "tool_id": "server_name/tool_name",
  "signature": "create_issue(owner, repo, title, body)",
  "documentation": "...",
  "examples": [
  {
  "input": { "owner": "xx", "repo": "yy", ... },
  "description": "...",
  "expected_output_type": "Issue"
  }
  ],
  "stats": {
  "call_count": 17,
  "success_rate": 0.88,
  "avg_latency_ms": 210,
  "last_used_at": "2025-12-10T..."
  },
  "risk_level": "LOW | MEDIUM | HIGH",
  "tags": ["tool", "github", "mcp"],
  "memory_tier": "MTS | LTS"
  }
  用途：
* Planner / Tool Router 在选工具时，可以基于历史表现做决策；
* AI Council 在评估工具是否继续使用、是否迁移到高权限环境时，有数据参考；
* Immune Loop 可以发现“表现变差的工具”并触发替换 / 拉黑。
  2.3 记忆与技能的自演化边界
* Memory 内容可以自动创建 / 更新；
* Memory schema 不能自动修改，只能通过人工变更；
* Skill 的 performance_stats 可以自动更新；
* 高风险域（Legal / Trading）的安全策略类记忆，必须由人审核。

【新增：2.4 情境记忆 & 要点记忆（Situation Memory & Gist Memory，不改变 2.1/2.2/2.3，仅补类型与用途）】
2.4.1 情境记忆（SITUATION_PROFILE）

* 用途：为 Context Framing 提供“场景画像”，支持情境→技能直连与预测。
* 建议结构（不强制修改现有 schema，仅作为新 type 的 payload 约定）：
  {
  "type": "SITUATION_PROFILE",
  "situation_id": "wechat_chat_view | xhs_post_editor | login_expired_modal | ...",
  "signals": {
  "ui_tree_fingerprint": "...",
  "key_elements": ["..."],
  "url_or_app": "...",
  "window_title": "..."
  },
  "recommended_skills": ["skill_id_a", "skill_id_b"],
  "stats": {
  "hit_count": 0,
  "success_rate": 0.0,
  "avg_latency_ms": 0
  },
  "memory_tier": "MTS | LTS"
  }
  2.4.2 要点记忆（GIST_MEMORY）
* 用途：把长 Trace 压缩为“可复用骨架规律”，避免细节污染与记忆膨胀。
  {
  "type": "GIST_MEMORY",
  "domain": "Desktop | Legal | Trading | cross",
  "gist": [
  "When X happens, try Y first",
  "If prediction_error == login_expired, run reauth_skill"
  ],
  "evidence_refs": ["trace_id_1", "trace_id_2"],
  "applicability": {
  "situations": ["..."],
  "tools": ["..."],
  "constraints": ["..."]
  },
  "memory_tier": "MTS | LTS"
  }
  2.4.3 预测状态模板（EXPECTED_STATE_TEMPLATE）
* 用途：支持 Predictive Processing，用模板定义“我期望看到的状态是什么”。
  {
  "type": "EXPECTED_STATE_TEMPLATE",
  "situation_id": "...",
  "expected_markers": ["element_exists:SendButton", "text_contains:..."],
  "fallback_paths": ["skill:recover_modal", "skill:reauth"],
  "memory_tier": "MTS | LTS"
  }

3. 四个循环：执行、免疫、睡眠、能力进化
   3.1 认知循环（Cognitive Loop）
   与 v3 一致，强调三点：
4. 无 Trace 不运行

   * 所有任务必须产生结构化 Trace。
5. 任务结束后，必须生成：

   * execution_summary（机器可读 + 人类可读）
   * 可选 lessons_learned（由 Critic 撰写）
6. 有价值的结果写入 Memory Fabric（通常是 STS / MTS）。

【新增：3.1.1 认知入口子循环（Perception Sub-Loop：情境→注意力→预测，不替换 3.1，仅作为执行前置）】

* 每个任务在进入 Planner/Executor 前增加：

  1. Situation Classifier 输出 situation_id
  2. Attention Filter 生成 attention_pack
  3. Expectation Engine 生成 expected_state
* Trace 必须记录：

  * situation_id / confidence
  * attention_reduction_ratio
  * expected_state + prediction_error（执行后回填）

3.2 免疫循环（Immune Loop）

* 使用简单统计 / ML 对以下指标做异常检测：

  * error rate / latency / cost / reward / success_rate；
* 当异常：

  * 自动降级：

    * 关闭部分自改功能
    * 降低探索强度
    * 回滚到上一稳定版本
  * 同时：

    * 把该时间段 Trace 打包成 Immune Case，交给 Research Layer 分析。

【新增：3.2.1 免疫循环对“预测误差”的一等公民支持（不改变 3.2，仅新增监控维度）】

* 新增异常检测指标：

  * prediction_error_rate（预测失败率）
  * unexpected_ui_rate（界面与期望不一致比例）
  * context_misclass_rate（情境识别误判率）
* 当上述异常升高：

  * 优先降级：禁用情境→技能直连，回退到 Planner 深思模式
  * 标记 Immune Case：用于更新 SITUATION_PROFILE / EXPECTED_STATE_TEMPLATE

3.3 睡眠循环（Sleep / Consolidation Loop）

* 周期：每日 / 每周（可配置）；
* 主要输出：

  1. 新的 Semantic Memory（对话 / 任务知识总结）；
  2. 新的 Procedural Memory / Skills（步骤化流程）；
  3. 训练 / 对齐数据对（例如失败→成功、旧 Planner→新 Planner）。
* 限制：

  * 每次运行最多处理多少 Trace；
  * 最多使用多少 Token（由 Budget 控制）。

【新增：3.3.1 睡眠循环的“要点抽象 + 情境映射”（不改变 3.3，仅新增输出项）】

* 新增输出：
  4. Gist Memory 生成（长 Trace → gist 规则集合）
  5. Situation → Skill Mapping 更新（高置信场景绑定稳定技能）
  6. Expected State Template 提炼（成功轨迹提炼 expected_markers）
* 新增清理策略建议：

  * STS 清理以 “已生成 gist / 已沉淀 procedural” 为前提
  * MTS 压缩：保留 gist + procedural + 关键 evidence_refs

3.4 能力进化循环（Skill & Code Evolution Loop）
输入：

* 高成功率的 Trace（可抽象为通用技能的模式）
* Immune Loop 标记的 “表现差或不稳定模块”
  步骤：

1. Pattern Mining：从 Trace 中抽取可复用模式；
2. 由 LLM 生成技能代码 + 测试（Skill Candidate）；
3. 在 Sandbox 执行单测 / 回归 / 性能测试；
4. 使用 Eval Harness 对比旧技能；
5. 决策：

   * supersede 旧技能
   * 并存（A/B）
   * 放弃新技能
     输出：

* 新 Skill 定义（Skill Schema）
* supersedes 关系
* Patch / Skill 评估报告（供 Research Layer 和 AI Council 使用）

【新增：3.4.1 认知型技能的进化入口（不改变 3.4，仅补“情境/注意力/预测”类技能）】

* Pattern Mining 的新增来源：

  * situation_id 序列模式（哪些场景最常触发失败/重试）
  * attention_pack 命中模式（哪些信号最能预测成功）
  * prediction_error 分布（哪些误差类型最常见）
* 新技能候选类型扩展：

  * situation_classifier_update（情境识别提示/规则）
  * attention_policy_update（注意力裁剪策略）
  * expected_state_template_update（期望状态模板更新）
  * situation_to_skill_rule（情境→技能直连规则）

4. 自编程引擎（Self-Programming Engine）
   4.1 职责
5. 接收来自 Meta Layer / Immune Loop 的 “需要改进的模块列表”；
6. 为每个模块生成一个或多个 Patch 候选；
7. 如果缺测试，优先补测试，再改代码；
8. 在 Sandbox / Staging 跑：

   * 单元测试
   * 回归测试
   * 性能测试
   * 静态分析 / Fuzzing（按需要）
9. 生成结构化 Patch Report：

   * 覆盖率 / 性能变化 / 成本变化 / 风险评估；
10. 提交给：

    * Research Layer + AI Council 联合决策；
    * 低风险域可直接进入 Canary。
      4.2 自编程边界

* 自编程只允许改 /mutable/ 下的 auto_updatable 模块；
* 禁止改：

  * /kernel/
  * 交易 Execution / 风控模块
  * Schema 定义模块
* 对 Legal / Trading：

  * 可以改工具 / 辅助逻辑（如日志处理、报表格式）；
  * 核心推理 / 风控逻辑仍需人工 Gate。

【新增：4.3 自编程引擎对“认知入口层”的可演化范围声明（不改变 4.1/4.2，仅新增边界说明）】

* 允许自编程改进（在 /mutable/ 且 auto_updatable 前提下）：

  * Situation Classifier 的提示词/特征工程/轻量模型权重（若采用）
  * Attention Filter 的裁剪策略与阈值（数据驱动，受 Budget 约束）
  * Expectation Engine 的 expected_markers 生成逻辑（模板提炼逻辑）
* 禁止自编程改动：

  * Safety Kernel 对高危域的 Gate 规则
  * “情境→技能直连”的高风险域白名单（需人工/宪法级规则）

5. 工具与技能系统：MCP + 双轨能力获取
   这一章是 v3.1 的核心升级。
   5.1 双轨能力获取（Dual-Track Capability Acquisition）
   当系统发现 Capability Gap 时：
   Gap Detected
   ├─ 属于标准外部服务 / 工具？
   │    （如 GitHub/Slack/DB/FS/Web/API/...）
   │
   │    YES → 优先走 MCP Route（外源能力）
   │
   └─ NO → 走 Self-Programming Route（内源演化）
   路径 A：MCP Route（外源能力）

* 定位：

  * 操作 API / DB / 文件系统 / 浏览器 / DevTools 等；
* 手段：

  * 通过 MCP registry（mcp.so / smithery）发现工具；
  * Tool Learning 解析 schema + 生成示例 + 写入 TOOL_KNOWLEDGE；
  * 通过 Tool Adapter 暴露为内部 Tool/Skill。
    路径 B：Self-Programming Route（内源能力）
* 定位：

  * 核心业务逻辑 / 算法 / 性能优化 / 复杂控制流；
* 手段：

  * Architect → Programmer → Tester → Reviewer 流水线；
  * Git-native 分支管理；
  * Patch 报告与 Council / Research Layer 决策。
    原则：能买（MCP）就不造（自编工具）；但一旦进入“造”的阶段，就要走完整自编程流程。

5.2 MCP Tool Learning & Integration Layer
子模块：

1. ToolDiscoveryModule

   * 查询 MCP registry（mcp.so / smithery / 本地配置）；
   * 根据 Gap 描述做语义匹配，找候选工具。
2. ToolLearningModule

   * 解析 MCP server 提供的工具 schema：

     * 输入参数 / 返回值 / 描述；
   * 调用 LLM 生成：

     * 使用示例（input JSON + 解释 + 预期输出类型）；
   * 写入 Memory Fabric 的 TOOL_KNOWLEDGE。
3. ToolAdapter

   * 将 MCP 工具封装成内部“工具对象”（CodeTool / Action）：

     * 统一接口：invoke(params) → result or error；
   * 对 Planner / Executor 来说，工具来源是透明的。
4. ToolRegistry

   * 管理当前可用工具：

     * id / 类型 / 能力标签 / 风险等级 / 状态（experimental / trusted / deprecated）；
   * 提供查询接口给 Planner / Council / Meta Layer。
5. ToolUsageStats

   * 记录每次调用的：

     * 成败 / 时延 / 错误类型；
   * 周期性写回 TOOL_KNOWLEDGE。

5.3 AI Council 治理（替代 Human-in-the-Loop）
Gate 2 不再是人类点 Y/N，而是多个 AI 角色（Risk / Capability / Cost）共同讨论与投票。
5.3.1 Council 角色

* RiskAgent（安全官）

  * 看工具来源 / 权限 / 访问范围；
  * 对高危类别（filesystem / shell / browser / network-wide）有“一票否决权”。
* CapabilityAgent（能力官）

  * 评估工具对当前 Gap 的收益：

    * 是否唯一 / 是否比现有工具好；
  * 避免重复 / 冗余工具。
* CostAgent（资源官，可选）

  * 考虑维护复杂度 / 间接依赖 / 对整体系统成本的影响。
    未来可以增加更多角色（例如 ComplianceAgent），但 v3.1 版本以这三类为主。
    5.3.2 决策流程（简化版）

1. ToolDiscovery 找到候选工具；
2. Safety Kernel 做静态初筛（官方 scope / whitelist / dangerous_categories）；
3. 把 tool_metadata + gap_context + history_stats 提交给 AI Council；
4. 每个 Agent 给出意见：APPROVE / SANDBOX_ONLY / REJECT；

   * RiskAgent 有一票否决权；
5. 汇总结果：

   * 多数 APPROVE → 正常接入；
   * 多数 SANDBOX_ONLY → 仅限沙箱或只读；
   * 无正向票 / RiskAgent 否决 → 拒绝接入。
     你作为人类，只需通过配置决定：“是否允许自动接入新工具（allow_auto_tool_install）”而不是每次盯着终端敲 y/n。

5.4 轻量安全配置示意
mcp_security:

# 总开关：是否允许 Council 自动接入新工具

allow_auto_tool_install: true

# 官方 scope（Static Filter 使用）

official_scopes:
- "@modelcontextprotocol"
- "@smithery"

# 明确信任的常用工具

whitelist:
- "slack-mcp"
- "postgres-mcp"

# 高危类别：自动标记为 high_risk，RiskAgent 严审

dangerous_categories:
- "filesystem"
- "shell"
- "browser"

【新增：5.5 认知入口层与工具/技能系统的耦合点（不改变 5.1–5.4，仅补运行时规则）】
5.5.1 Planner 输入标准化

* Planner 只接收 attention_pack，而不是原始 UI Tree 全量；
* 原始数据保留在 Trace，但不直接喂给 Planner（除非 Debug 模式）。
  5.5.2 Situation → Skill 优先级（反射式执行）
* 若 situation_id 命中高置信 Procedural Skill：

  * 默认走 “Skill First”
  * 失败则回退到 Planner（深思）
    5.5.3 Predictive First 执行协议
* Executor 执行每一步前必须：

  * 生成 expected_state
* 执行后必须：

  * 计算 prediction_error
  * 优先用“误差类型→修复技能”映射表处理
    5.5.4 Cognitive Policies（认知策略可配置）
    cognitive_policies:
    enable_situation_classifier: true
    enable_attention_filter: true
    enable_expectation_engine: true
    enable_situation_to_skill: true
    attention_target_ratio: 0.15   # 目标保留 15% 上下文（数据驱动可调）
    prediction_error_fallback_to_planner: true

6. 多智能体与模型路由（加强版）
   6.1 多智能体角色固定 + 实验性
   基础常驻角色：

* Speed-Agent（优先响应速度）
* Safety-Agent（优先安全稳定）
* Cost-Agent（优先成本）
* Domain-Expert-Agent（领域专家：Legal / Trading / Desktop）
* Governance Council Agents（Risk / Capability / Cost for Tools & Patches）
  Research Layer 可以：
* 添加新角色做小流量实验；
* 调整权重，观察整体指标变化。
  6.2 模型路由的数据驱动
* 对每类任务记录：

  * 使用哪种模型
  * 效果（成功率 / 用户满意度 / 收益 / 回撤）
  * 成本（Token / 时间）
* 定期由 Sleep Loop / Research Layer 优化路由策略；
* 高风险域使用白名单模型 + 人工设定上限。

【新增：6.3 认知入口层的模型路由（不改变 6.1/6.2，仅补“轻模型/重模型”分层）】

* Situation Classifier / Attention Filter 倾向使用：

  * 轻量模型或规则优先（成本低、延迟低）
* Planner / Critic 使用：

  * 更强模型（深思、推理、生成）
* 路由优化目标：

  * 把“绝大多数步骤”压到轻层完成，只在必要时上重模型

7. 多领域接入与知识重用
   保持原有三个重点域：

* Desktop 自动化
* LegalBot
* Trading
  v3.1 强化 Cross-Domain 知识重用：
* Memory Fabric 的 domain 字段允许 "cross"；
* 一些通用模式（重试策略、错误诊断、日志分析）可以跨域复用；
* MCP 工具本身就是天然跨域资源（如 HTTP 客户端 / 数据库工具）。

【新增：7.1 Cross-Domain 的“情境库”与“要点库”（不改变第 7 章原文，仅补复用对象）】

* situation_id 与 gist 的跨域价值：

  * 例如：login_expired_modal / network_timeout / permission_denied
  * 在 Desktop / Legal / Trading 都可能出现
* 建议复用层级：

  * SITUATION_PROFILE：cross
  * GIST_MEMORY：cross
  * EXPECTED_STATE_TEMPLATE：domain 或 cross（视风险而定）

8. 可观测性与研究接口（实验平台视角）
   8.1 实验接口
   提供给 Research Layer：

* create_experiment(config)
* run_experiment(experiment_id)
* compare_variants(variant_a, variant_b)
* export_results(experiment_id)
  8.2 可视化要求
  Dashboard 至少展示：
* 各域成功率 / 错误率 / 延迟 / 成本；
* Memory Fabric 的规模 / 命中率 / 升级与衰减速度；
* 自编程引擎产生的 Patch 数量 / 通过率 / 回滚率；
* MCP 工具数量 / 调用统计 / 退役工具列表；
* 实验数量 / 成功率 / 对生产的影响区间。

【新增：8.3 认知入口层观测指标（不改变 8.1/8.2，仅补 Dashboard 指标）】

* 情境识别：

  * situation_confidence 分布
  * context_misclass_rate（误判率）
* 注意力裁剪：

  * attention_reduction_ratio（裁剪比例）
  * attention_hit_rate（裁剪后仍成功的比例）
* 预测机制：

  * prediction_error_rate
  * top_prediction_error_types
  * fallback_to_planner_rate（预测失败回退率）
* 反射执行：

  * situation_to_skill_hit_rate（直连命中率）
  * situation_to_skill_success_rate（直连成功率）
* 要点记忆：

  * gist_count / gist_hit_rate
  * memory_bloat_index（记忆膨胀指数：LTS/MTS 增长与成功率的关系）

9. v3.1 实施路线图（含 MCP & Council）
   在 v3 的 Phase 0–5 基础上，加入 MCP & Council 相关任务。
   只列关键新增点：

* Phase 1–2：

  * Memory Fabric v1
  * Cognitive + Immune Loop v1
  * 简单 MCP Client，对接 1–2 个官方工具（如 filesystem read-only / postgres）
* Phase 3：Tool Learning & MCP Layer v1

  * 实现 ToolDiscovery / ToolLearning / ToolRegistry 基础版；
  * 增加 TOOL_KNOWLEDGE 类型；
  * Planner 能够查询工具并调用。
* Phase 4：AI Council v1

  * 定义 RiskAgent / CapabilityAgent / CostAgent 的 Prompt 和决策规则；
  * 接入 MCP 工具接入流程；
  * allow_auto_tool_install 默认开 / 关由你决定。
* Phase 5：Self-Programming Engine v1

  * 针对 Desktop 域某个工具模块，跑通完整自编程流程；
  * Patch 必须通过单测 + 基本回归；
  * Patch 接入前需要 AI Council 的“低风险确认”。

【新增：9.1 认知入口层落地路线（不改变第 9 章原文，仅补 Phase 插入点）】

* Phase 1–2（插入 Perception & Context Layer v0）

  * Situation Classifier（规则/轻量）+ Attention Filter（基于关键元素/关键词）
  * Trace 记录 situation_id / attention_reduction_ratio
* Phase 3（插入 Expectation Engine v0）

  * expected_state_template 的提炼与回填
  * prediction_error 的分类统计
* Phase 4（Council 增补：认知变更治理）

  * 对“情境→技能直连规则”的变更，纳入 Council 审议（尤其高风险域）
* Phase 5（自编程增补：认知策略自改）

  * 允许自编程提出 attention_policy_update / expected_template_update
  * 必须走 Sandbox → Staging → Production

10. 关键挑战清单（v3.1 视角）
    保持 v3 的挑战，同时加入两点新内容：
11. 工具爆炸 vs 可控性

    * MCP 生态有上千工具；
    * 如何避免“工具太多 → Planner 乱用 → 维护困难”？
    * 工具治理 = 发现 + 试用 + 统计 + 退役。
12. AI Council 的质量与偏差

    * 多 Agent 虽然比一个人聪明，但：

      * Prompt 设计不好 → 会一起犯同一种错误；
      * 需要通过实验不断调整角色权重与决策规则。

【新增：10.3 认知入口层的挑战（不改变 10.1/10.2，仅补缺失项）】
3. 情境识别漂移（Context Drift）
* UI 改版、语言变化、A/B 实验会导致 situation_id 漂移
* 需要：SITUATION_PROFILE 的自动更新与回退策略
4. 注意力裁剪过度（Over-filtering Risk）
* 裁剪掉关键线索会导致 Planner 误判
* 需要：attention_policy 的数据驱动校准 + Debug 回放模式
5. 预测模板不准（Expectation Misalignment）
* expected_state 不准会产生大量 prediction_error
* 需要：失败样本驱动模板更新（Sleep Loop/Immune Loop 联动）

11. Architect’s Note（给未来的你看的话）
    从 v2 → v3 → v3.1，这套系统已经不再是：
    “一个会写代码的 LLM 包装器”
    而是在变成：
    “一个会自己找工具 / 学工具 / 用工具，还会在必要时自己改自己的操作系统。”
    你作为人类，不再是“苦力 coder”或“审批小秘书”，而是：

* 制定宪法（哪些东西永远不能动）；
* 定义边界（MCP / 自编程的权限范围）；
* 点燃实验（告诉它：这里值得优化，那里可以做实验）；
* 在关键节点看报告、做少数关键决策。
  从今天起：
* 遇到新能力需求时，不要先想“我写个脚本”；
* 而是让 Meta-Agent 先问自己：
  “这件事有没有 MCP 工具可以做？没有的话，我能不能自己长出一块肌肉（Skill 或 Code）？”
  这，就是 v3.1 蓝皮书真正的精神。

【新增：11.1 Architect’s Note 补充：从“工程型”到“认知型”的那一步（不改变 11 章原文，仅补一句精神）】
而 v3.1+ 的关键跃迁是：
让系统像人脑一样——**先判断情境、再聚焦注意力、先预测、后校正、最后把细节压缩成要点**。
