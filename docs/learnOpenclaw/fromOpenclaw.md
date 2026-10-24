OpenClaw 的 Heartbeat 模块是一个非常有工程智慧的 “周期性觉醒与自我检查” 机制。它不仅仅是一个简单的定时器（Cron），而是专门为 AI
  Agent 设计的、带上下文感知的“后台巡检员”。


  1. 它是做什么的？
  Heartbeat 的核心逻辑是每隔一段时间（默认 30 分钟）给 Agent 发送一个内部指令，让它在主会话（Main Session）中执行一次“觉醒”。


   * 清单驱动 (`HEARTBEAT.md`)：它会要求 Agent 读取一个 checklist 文件。Agent
     会根据文件里的指令（如“检查邮件”、“看看后台任务是否完成”、“如果闲置太久就打个招呼”）执行任务。
   * 上下文关联：与孤立的 Cron 任务不同，Heartbeat 运行在主对话流中。这意味着 Agent
     记得你刚刚跟它说了什么，它的“觉醒”是基于当前工作状态的连贯行为。
   * 智能抑制 (`HEARTBEAT_OK`)：这是最聪明的一点。如果 Agent 检查完清单发现没什么需要用户关注的事，它会回复
     HEARTBEAT_OK。系统检测到这个 Token 后会拦截这条消息，不发送给用户。这既省钱（Token 消耗低）又不骚扰用户。
   * 异步事件中转：当后台的异步命令（Async Exec）执行完后，Heartbeat 会作为一个“中转站”，强制 Agent 把结果通过对话汇报给用户。


  2. 对 Project Taylor (Quentin) 的价值
  由于我们的项目定位是 “自进化的 AI 操作系统”，Heartbeat 机制对我们具有极高的适配性：


  A. 异步自进化结果的“自然汇报”
  目前我们的 SelfProgrammingEngine 在沙盒里跑任务，跑完后结果存在数据库或日志里。
   * 借鉴点：引入 Heartbeat 后，Agent 可以在用户空闲时主动汇报：“我刚刚在后台修复了 fabric.py 的检索
     bug，并通过了所有测试，需要我合入吗？”。


  B. 空闲时间的“碎片化进化”
  目前我们的 SleepLoop 是一个沉重的“夜间作业”。
   * 借鉴点：利用 Heartbeat，Agent 可以在白天发现系统闲置时，主动执行一些“小型睡眠”。例如：“现在没活干，我把过去一小时的
     STS（短期记忆）压缩成一条 MTS（中期记忆）吧”。


  C. 会话冲突的优雅避让
  Heartbeat 在代码中实现了 requests-in-flight 检测。
   * 借鉴点：这可以优化我们的 Lanes（车道并发控制）。当用户正在快速输入时，Heartbeat
     会自动退让，避免在用户思考时插嘴汇报后台任务，这提升了 UX 的高级感。


  D. 系统健康巡检 (配合 ImmuneLoop)
  ImmuneLoop 目前更像是一个后台监控。
   * 借鉴点：通过 Heartbeat，Agent 可以把监控发现的异常以“人格化”的方式说出来：“我注意到最近 API 的延迟增加了
     30%，我调整了模型路由策略，现在响应应该快些了”。

  3. 结论与建议
  非常有价值，建议集成。


  建议方案：
  我们不需要像 OpenClaw 那样写一个完整的 heartbeat-runner.ts，而是将它作为 CognitiveLoop 的一个 “闲置状态扩展”：
   1. 在 data/ 下增加一个 heartbeat_manifest.md 作为巡检指南。
   2. 在 CognitiveLoop 中增加一个 IdleObserver。
   3. 当计时器触发且当前 Lane 无活动时，注入一个带有 HEARTBEAT_OK 协议的内部 Task。
   4. 优先处理自编程完成、异常检测报告、内存压缩建议这三类事件。


  这能让 Quentin 从一个“被动响应的工具”真正变成一个“主动在线的系统”。

  OpenClaw 的 Pi 大脑模块（主要位于
  src/agents/pi-embedded-runner）是整个系统的核心认知执行引擎。它不是一个静态的知识库，而是一个处理 LLM
  交互、工具调用、上下文管理和错误恢复的动态调度器。


  1. 文件结构与功能分布
  该模块包含约 20-30 个核心文件，分为几个关键子目录：


   * `pi-embedded-runner/` (核心调度):
       * run.ts: 核心入口。负责整个认知周期的编排，包括 Lane 队列分配、模型选择、API 密钥轮转、尝试（Attempt）循环。
       * lanes.ts: 并发控制。实现“车道”机制，确保同一会话（Session）的指令串行执行，防止内存/Trace 状态竞争。
       * compact.ts: 上下文压缩。当上下文接近溢出时，自动触发压缩算法（类似于我们蓝皮书里的 Consolidation）。
       * session-manager-*.ts: 会话状态的初始化与缓存。
   * `run/` (单次尝试逻辑):
       * attempt.ts: 处理单次 LLM 调用、流式输出解析、多步工具调用循环（Tool Loop）。
       * payloads.ts: 将 LLM 的原始响应转换为系统可识别的 Payload。
   * `pi-extensions/` (增强扩展):
       * context-pruning/: 上下文剪枝。比简单压缩更高级，能智能识别并删除冗余的历史信息。
       * compaction-safeguard.ts: 防止压缩失败导致系统崩溃的安全护栏。
   * `pi-embedded-helpers/` (工具库):
       * failover-reason.ts: 错误分类器（限流、授权、超时、格式错误等）。
       * thinking.ts: 针对支持推理的模型（如 Claude Thinking）的参数适配。


  2. 值得借鉴的高级实现方式

  A. 预感知上下文护栏 (Pre-emptive Context Guard)
  在调用 LLM 之前，系统会先计算当前上下文大小。如果剩余空间不足，它会提前触发压缩，而不是等 API 报错。这极大提升了长对话的稳定性。


  B. 多级身份轮转 (Auth Profile Rotation)
  它实现了一套精细的 API Key 管理：
   * Cooldown 机制：如果某个 Key 触发了 429（限流），它会自动进入冷却时间，调度器选择下一个可用的 Profile。
   * 分级 Failover：先试同模型的不同 Key，再试同 Provider 的备用模型，最后跨 Provider 切换。


  C. 细粒度错误分类 (Failover Classification)
  它不只是捕获异常，而是会分析异常文本。例如，如果识别到
  cloud_code_assist_format_error，它会知道是工具调用格式坏了，从而在重试时注入一个 schema_transformer 来修正 LLM 的输出。


  D. 并发车道 (Lanes)
  它将任务分配到不同的 Lane（如 CommandLane.Main）。对于 Project Taylor 来说，这可以解决“用户连续发送三条消息，导致 Agent
  内部状态写乱”的问题。


  E. 拒绝词过滤 (Scrubbing)
  例如 scrubAnthropicRefusalMagic，专门处理特定模型厂商在测试或特定模式下的特殊 Token 注入，防止这些敏感字符串污染 Session 历史。

  结论
  Pi 模块是 Quentin 最完美的工程参考对象。
  它把一个简单的 while(true) { chat } 循环变成了一个具备自愈能力、并发安全、成本意识的工业级运行时。


  建议借鉴点：
   1. `lanes.ts` 的并发设计：引入到我们的 L0 Runtime。
   2. `failover` 异常分类逻辑：增强我们的 ImmuneLoop 对当下失败的即时反应能力。
   3. `context-pruning` 剪枝策略：作为 MemoryFabric STS 层向 MTS 迁移前的前置处理。


   OpenClaw 的 Prompt 构建方式体现了高度的 模块化、动态性 和
  分层治理。它不是一个单一的大文件，而是一套根据当前环境、工具、身份和任务动态生成的结构化指令系统。

  1. Prompt 的文件分布与组织


   * 核心构建逻辑 (`src/agents/system-prompt.ts`):
       * 这是“工厂”文件。它定义了 Prompt 的骨架，包括 Tooling (工具)、Safety (安全)、Memory (记忆)、Workspace (工作空间)、Runtime
         (运行时) 等标准章节。
       * 它通过不同的 PromptMode ("full", "minimal", "none") 来控制 Prompt 的精简程度。子智能体（Sub-agents）通常使用 minimal
         模式以节省 Token。
   * 任务专项指令 (`.pi/prompts/*.md`):
       * 这些是 Markdown 格式的 Skill 定义。
       * 例如 cl.md (Changelog 审计)、reviewpr.md (PR 评审)。这些文件包含了具体的 SOP（标准作业程序）、检查清单和 Git 命令示例。
       * 借鉴点：Agent 不会在 System Prompt 里塞满所有技能，而是在需要时通过 read_skill 工具动态读取这些 .md 文件。
   * 个性与灵魂 (`soul.md`):
       * 如果工作空间存在 soul.md，系统会自动注入指令，要求 Agent “具身化”该文件定义的语气和性格。

  2. Prompt 构建的高级特性

  A. 严格的思考/回复协议 (Thinking Tags)
  它通过 reasoningTagHint 强制要求 Agent 遵循特定的输出格式：


   <think> 内部推理过程 </think>
   <final> 最终呈现给用户的回答 </final>
  这对于 Quentin 这种需要执行复杂任务的 Agent 至关重要，因为它能将“计划/反思”与“执行/输出”在 Token 层面物理隔离。


  B. 动态工具摘要 (Tool Summaries)
  System Prompt 中的工具介绍不是硬编码的，而是根据 availableTools 集合动态生成的。
   * 工程细节：它会维护一个 coreToolSummaries 映射，只有当该工具被策略（Policy）允许时，才会出现在 System Prompt 里。这避免了 Agent
     尝试调用它“听过但没权限”的工具。


  C. 记忆检索引导 (Memory Recall Guidance)
  它在 buildMemorySection 中明确告诉 Agent：
  > “在回答关于过去决策、日期、人名或 todo 的任何问题前：必须先运行 memory_search 搜索 MEMORY.md。”
  这是一种 “强迫性 RAG” 策略，能有效减少 Agent 的幻觉。


  D. 抑制啰嗦 (Tool Call Style)
  它明确规定：
  > “默认情况下：不要解说常规、低风险的工具调用（直接调）。只有在多步骤工作、复杂问题或敏感操作（如删除）时才进行说明。”
  这极大提升了 Agent 的执行效率和用户体验。


  E. 运行时元数据 (Runtime Line)
  Prompt 的最后一行通常是 Runtime: agent=... | host=... | os=... | model=...。
  这让模型清晰地意识到自己当前所处的物理环境（如：我在 Linux 容器里，还是在用户的 MacOS 宿主机上）。

  3. Quentin 可以借鉴的实现方式


   1. 分层 System Prompt：
       * L0：身份、安全宪法（永不改变）。
       * L1：当前工具集、工作空间路径、运行时元数据（由 MemoryFabric 的 STS 动态提供）。
       * L2：任务专项 Skill（通过 quentin/mutable/skills/*.md 动态挂载）。

   2. 强制性思考协议：
       * 在 Quentin 的 CognitiveLoop 中引入 <think> 标签，并配合正则拦截，确保 Agent 的“内心独白”不被用户看到，但能被 Trace 记录。


   3. 技能动态加载：
       * 效仿 OpenClaw 的 buildSkillsSection。Quentin 应该在 Prompt 里列出可选技能的索引，告诉模型：“如果你要处理 Legal
         任务，请先读取 skills/legal_base.md”。


   4. Silent Reply (`HEARTBEAT_OK`)：
       * 引入 OpenClaw 的 SILENT_REPLY_TOKEN。当自进化任务在后台静默完成且没有异常时，允许 Agent 输出特定 Token 来完全抑制通知。


  一句话总结：OpenClaw 的 Prompt 设计不是在“写作文”，而是在“写配置”。 这种工程化的 Prompt 构建方式是 Quentin
  走向工业级稳定性的必经之路。


  我已经深入分析了 OpenClaw 的三个核心 Prompt 模块：System Prompt、技能/SOP 模块 (reviewpr.md 等) 和 上下文剪枝模块
  (pruner.ts)。


  这里是对每一个模块的 Prompt 构建方式、具体写法 以及 对 Quentin 的借鉴价值 的详细分析：

  1. 核心 System Prompt (src/agents/system-prompt.ts)


  这是 Agent 的“出厂设置”和“物理法则”。


   * 构建方式：
       * 动态拼装：它不是一个静态文件，而是一个 TypeScript 函数 buildAgentSystemPrompt。它接受 enabledTools、promptMode
         ("full"/"minimal")、runtimeInfo 等参数。
       * 条件渲染：
           * 如果有 message 工具，才显示 Messaging 章节。
           * 如果是 minimal 模式（子智能体），则跳过 Tool Summaries、Memory、Docs 等章节，只保留最核心的 Identity 和 Safety。
           * 如果有 reasoningTagHint，才插入关于 <think> 标签的强制指令。
       * 分层覆盖：Identity -> Tools -> Safety -> Skills -> Memory -> Context。


   * 具体写法 (Wording Highlights)：
       * 身份定义："You are a personal assistant running inside OpenClaw." —— 简洁，不废话。
       * 工具调用风格：
           * "Default: do not narrate routine, low-risk tool calls (just call the tool)." —— 极力抑制废话。
           * "Narrate only when it helps: multi-step work, complex/challenging problems..."
       * 安全宪法：
           * "You have no independent goals: do not pursue self-preservation..." —— 明确的“无我”声明，防止模型失控。
       * Silent Reply：
           * "When you have nothing to say, respond with ONLY: ${SILENT_REPLY_TOKEN}" ——
             这是工程上的神来之笔，彻底解决“空回复”骚扰。


   * 对 Quentin 的借鉴：
       * Action：在 quentin/core/prompts.py 中实现类似的 build_system_prompt 函数。
       * Action：引入 minimal 模式。当 MultiAICouncil 生成一个只负责做数学题的临时 Agent 时，不需要给它加载整个 MemoryFabric
         的说明书，省 Token。


  2. 技能/SOP 模块 (.pi/prompts/*.md)

  这是 Agent 的“岗位手册”。OpenClaw 把复杂的工程任务（如 CR、Land PR）写成了 Markdown 格式的 SOP。


   * 构建方式：
       * Markdown 结构：Input -> Do (Goal) -> Steps (1, 2, 3...) -> Output (Structured).
       * 参数注入：使用 $1 占位符（如 PR: $1 <number|url>），虽然简单，但足够有效。
       * CLI 模板：直接在 Prompt 里给出 gh pr view ... --jq ... 这种复杂的 CLI
         命令。模型只需要填参数，不需要自己“发明”命令。这极大提高了成功率。


   * 具体写法 (Wording Highlights)：
       * Review PR (`reviewpr.md`)：
           * "Goal: produce a thorough review... Do NOT merge, do NOT push..." —— 第一句话就设定边界。
           * "9. Output (structured)" —— 强制规定输出格式（A, B, C, D...），方便后续正则提取或人类快速阅读。
           * "Rules / Guardrails" —— 再次强调 Review only。


   * 对 Quentin 的借鉴：
       * Action：把 quentin/mutable/skills/ 下的 Python 代码技能，逐步迁移或补充为这种 Markdown SOP。对于 SelfProgramming
         这种复杂流程，写一个 write_patch.md 比让模型自己“空想”怎么写补丁要稳得多。
       * Action：在 Prompt 里直接贴“最佳实践代码片段”或“CLI 命令模板”。不要高估模型的记忆力，要低估它的创造力（在工具使用上）。

  3. 上下文剪枝模块 (src/agents/pi-extensions/context-pruning/pruner.ts)


  这是 Agent 的“大脑垃圾回收机制”。OpenClaw 没有用 Prompt 来做这件事！


   * 构建方式：
       * 纯算法实现：我原以为它会用一个 Prompt 说“请总结以下对话...”，但实际上它全是 TypeScript 逻辑代码。
       * Soft Trim (软修剪)：保留 toolResult 的头尾（Head & Tail），中间用 ... 替换。逻辑在 softTrimToolResultMessage 函数中。
       * Hard Clear (硬清除)：如果 Context 还是爆了，直接把中间的 toolResult 替换成 [placeholder]。
       * 保护机制：
           * keepLastAssistants: 永远不修剪最近 N 轮的对话。
           * hasImageBlocks: 包含图片的工具结果不修剪（怕丢失关键视觉信息）。


   * 具体写法 (Wording Highlights)：
       * 它生成的“压缩痕迹”是这样的：
           [Tool result trimmed: kept first 1000 chars and last 1000 chars of 50000 chars.]
       * 这种写法既告诉了模型“这里有东西被删了”，又保留了最重要的头尾（通常包含报错信息或结果摘要）。


   * 对 Quentin 的借鉴：
       * Action：不要用 LLM 去做“上下文压缩”！ OpenClaw 证明了用规则（保留最近 N 轮、保留 Head/Tail）更便宜、更稳定、更可控。
       * Action：在 MemoryFabric 的 STS 层实现类似的 prune_context() 方法。当 Token 超过 128k 时，优先把早期的 read_file 或 grep
         的长输出（tool_result）给“掐头去尾”。

  总结


  OpenClaw 的 Prompt 哲学是：
   1. System Prompt 是代码：它是动态生成的配置，不是静态文本。
   2. Skill Prompt 是说明书：包含具体的 CLI 命令和输出模板。
   3. Context Pruning 是算法：不用 LLM 做，用确定性规则做。


  Quentin 应该全盘照收这套哲学。

  我们将继续深度解剖 OpenClaw 的“大脑指令集”，重点关注那些隐藏在代码逻辑中、动态注入的 Prompt。这些 Prompt 决定了 Agent
  在面对突发状况（如工具报错、异步任务完成）时的反应。

  我们将深度分析以下四个进阶维度：


  1. 反应式注入：系统事件管道 (System Event Pipeline)
  在 OpenClaw 中，Prompt 不仅仅是对话开始时的那一段，它在对话过程中是“呼吸”的。


   * 实现位置：src/infra/system-events.ts 和 src/agents/pi-embedded-runner/run.ts。
   * 深度机制：
      当后台任务（如一个耗时 5 分钟的 exec）执行完毕时，OpenClaw 不会直接把结果塞给用户，而是将结果放入 SystemEvent 队列。在下一次
  Heartbeat 或用户说话时，它会动态地在 Prompt 中插入：
      > "An async command you ran earlier has completed. The result is shown in the system messages above. Please relay the command
  output to the user in a helpful way..."
   * 借鉴价值 (for Quentin)：
      目前 Quentin 的自进化任务（Patch 生成）是异步的。我们可以借鉴这种方式：当 SelfProgrammingEngine 跑完测试后，不要只是写个
  Log，而是在下一次 CognitiveLoop 迭代时，通过 “系统旁路 Prompt” 告诉 Agent：“嘿，你刚才提的那个补丁跑通了，现在去告诉用户吧。”

  ---


  2. 动态能力发现：工具摘要映射 (Tool Summary Mapping)
  OpenClaw 解决了一个经典难题：当你有 100 个工具时，如何不让 System Prompt 爆炸？


   * 实现位置：src/tool-summaries.ts。
   * 深度机制：
      它实现了一种 “渐进式提示”。System Prompt 里只显示工具的名称和极其简短的（10 个词以内）摘要。
       * 核心逻辑：它会根据 tools 对象动态生成一个 Map。只有当 Agent 表现出对某个工具的兴趣（或者已经加载了相关 Skill）时，才会通过
         docs 注入更详细的 Schema。
   * 对 Quentin 的启示：
      Quentin 的 ToolManager 应该避免在一次 Prompt 里塞入完整的 JSON Schema。
       * 策略建议：System Prompt 只写：- edit: 修改代码。如果模型想用 edit，它必须先通过一个 help(tool='edit')
         的动作来获取参数细节。这能节省 30% 以上的上下文空间。

  ---


  3. 多智能体握手协议：Sub-Agent Spawn
  OpenClaw 是如何让一个 Agent 派生出另一个 Agent 的？它的 Prompt 是如何“授权”的？


   * 实现位置：src/agents/system-prompt.ts 中的 minimal 模式。
   * 深度机制：
      当主 Agent 调用 sessions_spawn 时，它其实是在发送一个指令。主 Agent 的 Prompt 中有一句非常有力的引导：
      > "If a task is more complex or takes longer, spawn a sub-agent. It will do the work for you and ping you when it's done."
      而在 minimal 模式下，子 Agent 被告知：
      > "You are a personal assistant running inside OpenClaw... [Skipping high-level docs] ...focus on the specific task assigned
  by your parent session."
   * 借鉴价值：
      这是一种 “角色降级” 技术。父 Agent 拥有“全局观”和“记忆管理权”，子 Agent 只有“执行权”。这完美契合 Project Taylor 的 L1 (Base)
  与 L2 (Meta) 层的协作。

  ---


  4. 强制推理约束：<think> 标签的工程化处理
  这是 OpenClaw 维持逻辑严密性的核心。


   * 深度机制：
      它在 Prompt 中定义了严格的 “物理隔离”：
      > "Format every reply as <think>...</think> then <final>...</final>, with no other text."
      > "Only text inside <final> is shown to the user; everything else is discarded and never seen by the user."
   * 工程实现细节：
      在 attempt.ts 中，它使用了流式正则拦截器。如果模型在 <think> 标签外输出内容，系统会即时报错或在下一轮 Attempt
  中进行校准（Self-Correction）。
   * 对 Quentin 的价值：
      这是实现“全自动 Trace”的最佳路径。我们将 Agent 的 <think> 内容直接持久化到我们的 data/traces/ 中，而只给用户看
  <final>。这样，即使用户觉得 Agent 很简洁，我们的后台也能看到它极其复杂的思考过程。

  ---

  5. 总结：Quentin 的 Prompt 进化清单


  为了达到 OpenClaw 的工程水平，我建议我们对 Quentin 的 Prompt 进行以下“手术”：


   1. 从“文本文件”转向“模板函数”：彻底废弃 prompts.txt，改用 Python 的 PromptFactory 类，根据当前的 active_skills 和 lane_status
      动态组装。
   2. 引入“Silent Token”协议：允许 Agent 在执行内部任务（如 Memory Consolidation）时输出 [SILENT]，由 CognitiveLoop
      捕获并拦截，避免垃圾信息。
   3. 实施“强迫性 RAG”指令：在处理代码修改任务前，Prompt 必须包含：“你必须先 ls 目录，然后 read 关键文件，禁止凭空猜测。”
   4. 运行时元数据注入：在 Prompt 末尾永远附带：


       [Environment]
       AgentID: quentin-v3
       Workspace: /workspace/...
       OS: darwin
       Model: qwen2.5-vl (Local)
       Budget_Remaining: 85%


  深度分析结论：
  OpenClaw 的强大不在于它的模型，而在于它通过 Prompt 给模型套上了一层
  “数字外骨骼”。它让模型意识到自己的局限性，并强制它通过工具和协议来弥补。Quentin 的下一阶段，就是要把这套外骨骼穿上。